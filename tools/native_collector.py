"""Launch the same deterministic collector locally, separate from Hermes."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def run(*args):
    return subprocess.run(args,check=True,capture_output=True,text=True).stdout

def refresh(session, directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    credentials=session.get_credentials()
    if credentials is None: raise ValueError('Sign in to your AWS profile first')
    frozen=credentials.get_frozen_credentials()
    expiry=getattr(credentials,'_expiry_time',None) or datetime.now(timezone.utc)+timedelta(hours=1)
    value={'Version':1,'AccessKeyId':frozen.access_key,'SecretAccessKey':frozen.secret_key,
           'Expiration':expiry.isoformat()}
    if frozen.token:value['SessionToken']=frozen.token
    name=directory.parent.name
    image=subprocess.run(['docker','image','inspect','remedigenius-collector:local'],capture_output=True)
    if image.returncode:run('docker','build','-t','remedigenius-collector:local',str(ROOT/'deploy/collector'))
    # A named volume avoids uid/permission mismatches on Linux bind mounts.
    # Credentials travel over stdin and are never supplied as command arguments.
    writer="""import os,sys,pathlib
p=pathlib.Path('/run/operator');os.chown(p,10000,10000);os.chmod(p,0o700)
t=p/'credentials.pending';t.write_bytes(sys.stdin.buffer.read());os.chown(t,10000,10000);os.chmod(t,0o600);t.replace(p/'credentials.json')
c=p/'config';c.write_text('[default]\\ncredential_process = python /app/credentials.py\\n');os.chown(c,10000,10000);os.chmod(c,0o600)
"""
    subprocess.run(['docker','run','--rm','-i','--network','none','--user','0:0','-v',name+'-operator:/run/operator',
                    'remedigenius-collector:local','python','-c',writer],input=json.dumps(value),text=True,check=True,capture_output=True)
    return expiry.isoformat()

def prepare_state(name, config, directory, state_volume):
    """Restore lost local state before Hermes creates any new files."""
    env=Path(directory)/'state.env'
    values={'AWS_DEFAULT_REGION':config['region'],'AWS_CONFIG_FILE':'/run/operator/config',
            'AWS_EC2_METADATA_DISABLED':'true','BUCKET':config['bucket'],'PREFIX':config['prefix']}
    env.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    run('docker','run','--rm','--network','none','--user','0:0','-v',state_volume+':/state',
        'remedigenius-collector:local','chown','10000:10000','/state')
    script="from pathlib import Path; from state_store import restore; import json; p=Path('/state'); print(json.dumps(restore(p) if not any(p.iterdir()) else {'status':'EXISTING_STATE_RETAINED'}))"
    return run('docker','run','--rm','--env-file',str(env),'-v',name+'-operator:/run/operator:ro',
               '-v',state_volume+':/state','remedigenius-collector:local','python','-c',script)


def import_view(name, state_volume, source):
    """Copy an operator-selected view into checkpointed storage before launch."""
    source=Path(source).resolve()
    if not (source/'index.md').is_file() or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Knowledge view needs index.md and must not contain symbolic links')
    script="""from pathlib import Path
import shutil,uuid
root=Path('/state/shared');root.mkdir(parents=True,exist_ok=True)
stage=root/('knowledge.pending-'+uuid.uuid4().hex);shutil.copytree('/input',stage)
current=root/'knowledge'
if current.exists(): current.rename(root/('knowledge.previous-'+uuid.uuid4().hex))
stage.rename(current)
"""
    run('docker','run','--rm','--network','none','-v',state_volume+':/state',
        '--mount','type=bind,src='+str(source)+',dst=/input,readonly',
        'remedigenius-collector:local','python','-c',script)


def start(name, config, directory, state_volume):
    session_account=config['account_id'];region=config['region']
    env={'AWS_DEFAULT_REGION':region,'AWS_CONFIG_FILE':'/run/operator/config','AWS_EC2_METADATA_DISABLED':'true',
         'ACCOUNT_ID':session_account,'BUCKET':config['bucket'],'PREFIX':config['prefix'],'STATE_CHECKPOINT_SECONDS':'120',
         'TARGETS':json.dumps({'default':{'account_id':session_account,'regions':[region]}})}
    # No default collection of findings until the operator chooses a schedule.
    if config.get('checks'):
        env.update(CHECKS=json.dumps(config['checks']),INTERVAL_HOURS=str(config.get('interval_hours',24)))
    directory=Path(directory)
    (directory/'collector.env').write_text(''.join(k+'='+v+'\n' for k,v in env.items()))
    run('docker','build','-t','remedigenius-collector:local',str(ROOT/'deploy/collector'))
    socket_volume=name+'-reader'
    run('docker','run','--rm','--user','0:0','-v',socket_volume+':/run/ce-collector',
        'remedigenius-collector:local','chown','10000:10000','/run/ce-collector')
    run('docker','run','-d','--rm','--name',name+'-collector','--label','com.remedigenius.ce=collector',
        '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--memory','512m',
        '--tmpfs','/tmp:uid=10000,gid=10000','--env-file',str(directory/'collector.env'),
        '-v',name+'-operator:/run/operator:ro','-v',socket_volume+':/run/ce-collector',
        '-v',state_volume+':/state','remedigenius-collector:local')
    for _ in range(30):
        if subprocess.run(['docker','exec',name+'-collector','test','-S','/run/ce-collector/collector.sock'],capture_output=True).returncode==0:return socket_volume
        time.sleep(2)
    raise RuntimeError('Local collector did not start. Inspect its container logs; do not share credentials.')

def stop(name):
    result=subprocess.run(['docker','inspect',name+'-collector'],capture_output=True,text=True)
    if result.returncode:return
    if json.loads(result.stdout)[0]['Config'].get('Labels',{}).get('com.remedigenius.ce')!='collector':
        raise ValueError('Collector container is not owned by this launcher')
    run('docker','stop','-t','30',name+'-collector')
