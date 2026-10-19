"""S3 checkpoints with online SQLite backup; restore only into an empty home."""
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile
import uuid
import boto3
from datetime import datetime, timezone

EXCLUDE={'cache','image_cache','audio_cache','node_modules','.git','backups','upgrade-backups','ce-upgrades','ce-default-backups','sandboxes','installs','.local'}


def backup(home):
    home=Path(home)
    with tempfile.TemporaryDirectory() as temp:
        stage=Path(temp)/'home';stage.mkdir()
        hashes={}
        for source in sorted(home.rglob('*')):
            relative=source.relative_to(home)
            if any(part in EXCLUDE for part in relative.parts) or source.is_symlink() or not source.is_file(): continue
            if source.name.endswith(('-wal','-shm','.sock','.pending')): continue
            dest=stage/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            if source.suffix in ('.db','.sqlite','.sqlite3'):
                with closing(sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True,timeout=5)) as src,closing(sqlite3.connect(dest)) as dst:
                    src.backup(dst)
            else: shutil.copyfile(source,dest)
            hashes[relative.as_posix()]=hashlib.sha256(dest.read_bytes()).hexdigest()
        if not hashes: raise ValueError('Refusing empty checkpoint')
        archive=Path(temp)/'checkpoint.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for path in hashes: tar.add(stage/path,arcname=path,recursive=False)
        s3=boto3.client('s3');bucket=os.environ['BUCKET'];prefix=os.environ['PREFIX']+'/state'
        key=prefix+'/snapshots/'+uuid.uuid4().hex+'.tar.gz'
        s3.upload_file(str(archive),bucket,key)
        manifest={'schema':'ce-state/1','key':key,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'files':hashes,'created_at':datetime.now(timezone.utc).isoformat(),
                  'notice':'Contains private session/configuration data and may contain model secrets; protect bucket access.'}
        # Commit pointer last; interrupted uploads cannot become the latest checkpoint.
        s3.put_object(Bucket=bucket,Key=prefix+'/latest.json',Body=json.dumps(manifest).encode(),ContentType='application/json')
        return {'status':'OK','files':len(hashes),'created_at':manifest['created_at']}


def restore(home):
    home=Path(home)
    if home.exists() and any(home.iterdir()): raise ValueError('Restore requires an empty home')
    s3=boto3.client('s3');bucket=os.environ['BUCKET'];prefix=os.environ['PREFIX']+'/state'
    try: response=s3.get_object(Bucket=bucket,Key=prefix+'/latest.json')
    except s3.exceptions.NoSuchKey: return {'status':'NO_CHECKPOINT'}
    manifest=json.loads(response['Body'].read(10000001))
    if not manifest['key'].startswith(prefix+'/snapshots/'): raise ValueError('Checkpoint key outside state prefix')
    with tempfile.TemporaryDirectory() as temp:
        archive=Path(temp)/'state.tar.gz';s3.download_file(bucket,manifest['key'],str(archive))
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['sha256']: raise ValueError('Checkpoint hash mismatch')
        stage=Path(temp)/'verified';stage.mkdir()
        with tarfile.open(archive) as tar:
            members=tar.getmembers()
            if len({m.name for m in members})!=len(members): raise ValueError('Duplicate checkpoint paths')
            for member in members:
                path=PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or '\\' in member.name or not member.isfile(): raise ValueError('Unsafe checkpoint entry')
                if member.name not in manifest['files']: raise ValueError('Unexpected checkpoint file')
                target=stage/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(member) as src, target.open('wb') as dst: shutil.copyfileobj(src,dst)
                if hashlib.sha256(target.read_bytes()).hexdigest()!=manifest['files'][member.name]: raise ValueError('File hash mismatch')
            if {m.name for m in members}!=set(manifest['files']): raise ValueError('Incomplete checkpoint')
        home.mkdir(parents=True,exist_ok=True)
        marker=home/'.restore-in-progress';marker.write_text(manifest['sha256'])
        shutil.copytree(stage,home,dirs_exist_ok=True)
        for p in home.rglob('*'):
            os.chmod(p,0o700 if p.is_dir() else 0o600)
        marker.unlink()
    return {'status':'RESTORED','created_at':manifest['created_at']}

if __name__=='__main__':
    import sys
    print(json.dumps(restore('/state') if sys.argv[1]=='restore' else backup('/state')))
