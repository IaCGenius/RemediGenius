"""Preview and publish a selected knowledge view; never activate it or broaden IAM."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_view(directory):
    root = Path(directory).resolve()
    files = {}

    def read(name, limit):
        relative = PurePosixPath(name)
        if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                or ':' in name or relative.as_posix() != name):
            raise ValueError('Invalid view path')
        path = root.joinpath(*relative.parts)
        if any(p.is_symlink() for p in [path, *path.parents] if p != root):
            raise ValueError('View files must not use symlinks')
        if not path.resolve().is_relative_to(root) or path.stat().st_size > limit:
            raise ValueError('View file escapes its directory or exceeds its size limit')
        data = path.read_bytes()
        if len(data) > limit:
            raise ValueError('View file exceeds its size limit')
        files[name] = data
        if sum(map(len, files.values())) > 32_000_000:
            raise ValueError('Selected view exceeds 32 MB; select fewer collections')
        return data

    manifest = json.loads(read('manifest.json', 2_000_000))
    if manifest.get('schema') != 'rgce-knowledge-view/1':
        raise ValueError('Use a view exported by rgce.knowledge_library')
    documents = manifest.get('documents')
    collections = manifest.get('collections')
    if (not isinstance(documents, list) or not 1 <= len(documents) <= 1000
            or not isinstance(collections, list)):
        raise ValueError('Select between 1 and 1000 documents with explicit collections')
    for entry in documents:
        name = entry['path']
        if not re.fullmatch(r'[a-z0-9_-]+(?:/[a-z0-9_-]+)*/[a-f0-9]{24}/content\.md', name):
            raise ValueError('Invalid document path in manifest')
        if name in files:
            raise ValueError('Duplicate document in manifest')
        collection = str(PurePosixPath(name).parent.parent)
        if collection not in collections or entry.get('collection') != collection:
            raise ValueError('Document is outside the selected collections')
        content = read(name, 2_000_000)
        metadata = json.loads(read(str(PurePosixPath(name).with_name('metadata.json')), 32_000))
        if metadata != {k: v for k, v in entry.items() if k != 'path'}:
            raise ValueError('Manifest and document metadata differ; rebuild the view')
        if sha(content) != metadata.get('content_sha256'):
            raise ValueError('Content changed; re-import the source and rebuild the view')
    read('index.md', 2_000_000)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(files):
        raise ValueError('View contains unlisted files; publish only a clean exported view')
    hashes = {name: sha(data) for name, data in sorted(files.items())}
    view_hash = sha(json.dumps(hashes, sort_keys=True).encode())
    return manifest, files, hashes, view_hash


def prepare(directory, config):
    manifest, files, hashes, view_hash = read_view(directory)
    bucket = config.get('bucket_name', config.get('bucket', ''))
    prefix = config.get('workspace_prefix', config.get('prefix', ''))
    region = config.get('region', '')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
        raise ValueError('Configuration needs a valid bucket or bucket_name')
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', prefix):
        raise ValueError('Configuration needs a workspace prefix')
    if not re.fullmatch(r'[a-z0-9-]+', region):
        raise ValueError('Configuration needs an AWS region')
    name = 'view-'+view_hash
    plan = {'bucket': bucket, 'prefix': prefix+'/knowledge/'+name+'/',
            'region': region, 'aws_profile': config.get('aws_profile'),
            'knowledge_view': name, 'view_sha256': view_hash, 'files': hashes,
            'bytes': sum(map(len, files.values())),
            'documents': [{'path': d['path'], 'title': d['title'], 'scope': d['scope']}
                          for d in manifest['documents']]}
    token = sha(json.dumps(plan, sort_keys=True).encode())
    return plan, files, token


def publish(plan, files, client):
    # Bound writes to these exact prepared bytes. Never upload arbitrary directories.
    if {k: sha(v) for k, v in files.items()} != plan['files']:
        raise ValueError('Prepared content changed')
    bucket, prefix = plan['bucket'], plan['prefix']
    expected = {prefix+name for name in files}

    def check_keys():
        found = set()
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get('Contents', []):
                if item['Key'] not in expected:
                    raise ValueError('Unexpected object in destination; refusing to publish this view')
                found.add(item['Key'])
        return found

    def verify(name):
        response = client.get_object(Bucket=bucket, Key=prefix+name)
        body = response['Body']
        try:
            actual = body.read(len(files[name])+1)
        finally:
            body.close()
        if actual != files[name]:
            raise ValueError('Remote object differs; refusing overwrite. Keep this view inactive.')

    existing = check_keys()
    # Validate a resumed upload before writing any more objects.
    for name in files:
        if prefix+name in existing:
            verify(name)
    # Index last; runtime selection must still wait for the verified result.
    order = sorted(files, key=lambda name: (name in ('manifest.json', 'index.md'), name == 'index.md', name))
    for name in order:
        if prefix+name not in existing:
            try:
                client.put_object(Bucket=bucket, Key=prefix+name, Body=files[name], IfNoneMatch='*')
            except Exception as error:
                if getattr(error, 'response', {}).get('Error', {}).get('Code') not in ('412', 'PreconditionFailed'):
                    raise
            verify(name)
    if check_keys() != expected:
        raise ValueError('Publication incomplete; keep this view inactive and retry the same command')
    return {'status': 'PUBLISHED_VERIFIED_NOT_ACTIVATED', 'destination': 's3://'+bucket+'/'+prefix,
            'knowledge_view': plan['knowledge_view'], 'view_sha256': plan['view_sha256'],
            'verified_files': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--view', required=True, help='Exported local view directory')
    parser.add_argument('--config', required=True, help='CE AWS tfvars JSON or workstation config JSON')
    parser.add_argument('--publish', metavar='PREVIEW_TOKEN', help='Upload exactly the reviewed preview; default is offline preview')
    parser.add_argument('--json', action='store_true', help='Print structured preview or publication result')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    plan, files, token = prepare(args.view, config)
    if args.publish is None:
        if args.json:
            print(json.dumps({'status': 'PREVIEW_ONLY', **plan, 'preview_token': token}, indent=2))
        else:
            print('Preview only. No AWS calls or uploads performed.')
            print('Destination: s3://'+plan['bucket']+'/'+plan['prefix'])
            print(f"{len(plan['documents'])} documents; {len(files)} files; {plan['bytes']} bytes")
            for document in plan['documents']:
                print('- '+json.dumps(document['title'], ensure_ascii=False))
                print('  Scope: '+json.dumps(document['scope'], ensure_ascii=False))
            print('Exact selected files:')
            for name, digest in plan['files'].items():
                print('  '+name+'  sha256='+digest)
            print('Review these files, then repeat this command with --publish '+token)
            print('Uploading does not activate the view in Hermes.')
        return
    if args.publish != token:
        raise ValueError('Preview changed or token does not match; review a fresh preview before publishing')
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        client = boto3.Session(profile_name=plan['aws_profile'], region_name=plan['region']).client(
            's3', config=Config(retries={'mode': 'standard', 'total_max_attempts': 3}, connect_timeout=5, read_timeout=30))
        if 'IfNoneMatch' not in client.meta.service_model.operation_model('PutObject').input_shape.members:
            raise ValueError('Upgrade boto3: this command requires conditional PutObject support')
        result = publish(plan, files, client)
    except ClientError as error:
        raise ValueError('AWS '+error.response.get('Error', {}).get('Code', 'error')+
                         '; check operator access to the selected prefix. Nothing was activated; retry after resolving it.') from None
    except BotoCoreError:
        raise ValueError('AWS credentials or connection failed. Nothing was activated; retry after resolving it.') from None
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('Published and verified '+str(result['verified_files'])+' files at '+result['destination'])
        print('Not activated. AWS Spot: select knowledge_view='+result['knowledge_view']+' through your deployment workflow.')
        print('Workstation: set knowledge_dir to the reviewed local view and restart through the workstation launcher.')
        print('Then ask Hermes to read index.md and confirm the expected sources.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('Knowledge publication: '+str(error), file=sys.stderr)
        sys.exit(2)
    except ImportError:
        print('Knowledge publication: install the CE aws extra to publish; offline preview needs no AWS SDK.', file=sys.stderr)
        sys.exit(2)
