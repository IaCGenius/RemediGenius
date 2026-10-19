"""Run the native CE profile locally; AWS credentials enter only the isolated collector, never Hermes."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import zipfile
import yaml

import boto3
from package_native_hermes import package
from native_session_limits import prepare as prepare_session_limits
import native_validator
import native_ui
import native_collector

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b'


def command(*args, capture=False, **kwargs):
    return subprocess.run(list(args), check=True, text=True, encoding='utf-8',
                          stdout=subprocess.PIPE if capture else None, **kwargs).stdout


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        user = command('whoami', capture=True).strip()
        command('icacls', str(path), '/inheritance:r', '/grant:r',
                user+':(OI)(CI)F', 'SYSTEM:(OI)(CI)F', capture=True)
    else:
        path.chmod(0o700)


def seed_config(text, key, name, base_url):
    """Fill CE's profile model from the launcher, or omit it when keyless so
    Hermes shows its native model onboarding instead of a ready-looking model."""
    if key:
        return text.replace('__MODEL_NAME__',json.dumps(name)).replace('__MODEL_BASE_URL__',json.dumps(base_url))
    return yaml.safe_dump({k:v for k,v in yaml.safe_load(text).items() if k!='model'},sort_keys=False)

class Workstation:
    def __init__(self, config):
        self.cfg = json.loads(Path(config).read_text(encoding='utf-8-sig'))
        self.name = self.cfg.get('name', 'rgce-workstation')
        if not re.fullmatch(r'rgce-[a-z0-9-]{1,40}', self.name):
            raise ValueError('Use a dedicated rgce- prefixed Docker name')
        self.port = int(self.cfg.get('port', 9125))
        if not 1024 <= self.port <= 65535: raise ValueError('Invalid loopback port')
        self.root = ROOT/'.rgce/workstation'/self.name
        self.volume = self.name+'-data'

    def session(self):
        return boto3.Session(profile_name=self.cfg.get('aws_profile'), region_name=self.cfg['region'])

    def refresh(self):
        private_directory(self.root)
        if self.cfg.get('reader_function'):
            raise ValueError('Legacy Lambda configuration: use a new local-collector config; keep old Terraform state for its separate teardown')
        session=self.session()
        account=session.client('sts').get_caller_identity()['Account']
        if account != self.cfg['account_id']:raise ValueError('AWS profile account does not match configuration')
        return native_collector.refresh(session,self.root/'operator')

    def owned(self):
        result=subprocess.run(['docker','inspect',self.name],capture_output=True,text=True,encoding='utf-8')
        if result.returncode:
            if 'no such object' in result.stderr.lower() or 'no such container' in result.stderr.lower():
                return False
            raise RuntimeError('Cannot inspect Docker; check that the daemon is running and accessible')
        record=json.loads(result.stdout)[0]
        if record['Config'].get('Labels',{}).get('com.remedigenius.ce')!='workstation':
            raise ValueError('Existing container is not owned by this workstation launcher')
        return True

    def stop(self):
        native_ui.stop(self.name)
        if self.owned(): command('docker','stop','-t','30',self.name)
        native_validator.stop(self.name)
        native_collector.stop(self.name)
        (self.root/'runtime.env').unlink(missing_ok=True)
        print('Stopped local compute. Named volume and S3 evidence retained. Local scheduled checks stop with compute.')

    def start(self, upgrade=False):
        if self.owned():
            raise ValueError('Container already exists. Use stop then restart; do not start a second writer.')
        expires=self.refresh()
        print(native_collector.prepare_state(self.name,self.cfg,self.root/'operator',self.volume))
        archive=self.root/'source.zip'; packaged=package(archive)
        pin=self.root/'source-pin.json'
        if pin.exists() and json.loads(pin.read_text())['sha256'] != packaged['sha256'] and not upgrade:
            raise ValueError('CE source changed. Review it, back up the volume, then pass --upgrade to apply it.')
        with zipfile.ZipFile(archive) as source:
            source.extractall(self.root/'source') # generated locally by the reviewed packager
        key=(self.session().client('secretsmanager').get_secret_value(SecretId=self.cfg['model_secret_arn'])['SecretString']
             if self.cfg.get('model_secret_arn') else os.environ.get(self.cfg.get('model_key_env','MODEL_API_KEY'),''))
        profile=self.root/'source/profiles/ce/desk'
        cfg=profile/'config.yaml'
        cfg.write_text(seed_config(cfg.read_text(encoding='utf-8'),key,self.cfg['model_name'],self.cfg['model_base_url']),encoding='utf-8')
        shared=self.root/'shared'; shared.mkdir(exist_ok=True)
        knowledge=self.cfg.get('knowledge_dir')
        if knowledge and not (Path(knowledge)/'index.md').is_file():
            raise ValueError('Select an exported knowledge view containing index.md')
        if knowledge:
            native_collector.import_view(self.name,self.volume,knowledge)
        login_path=self.root/'login.json'
        if not login_path.exists():
            login_path.write_text(json.dumps({'username':'ce','password':secrets.token_urlsafe(24),'secret':secrets.token_urlsafe(32)}))
        login=json.loads(login_path.read_text())
        values={'MODEL_API_KEY':key,'HERMES_DASHBOARD':'1','HERMES_DASHBOARD_PORT':'9120',
                'HERMES_DASHBOARD_BASIC_AUTH_USERNAME':login['username'],
                'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD':login['password'],
                'HERMES_DASHBOARD_BASIC_AUTH_SECRET':login['secret'],
                'AWS_EC2_METADATA_DISABLED':'true','HERMES_TUI_TOOLSETS':'skills,clarify,ce_runtime'}
        if not key:values.pop('MODEL_API_KEY')
        if any(not v or any(ord(c)<33 or ord(c)>126 for c in v) for v in values.values()):
            raise ValueError('Missing/invalid model credential or login value; no values logged')
        env=self.root/'runtime.env'; env.write_text(''.join(k+'='+v+'\n' for k,v in values.items()),encoding='utf-8')
        # Probe the retained Hermes configuration (seed only for a new profile).
        try:
            if not key:raise LookupError('MODEL_ONBOARDING_REQUIRED')
            command('docker','run','--rm','--entrypoint','/opt/hermes/.venv/bin/python',
                '--env-file',str(env),'--mount',f'type=volume,src={self.volume},dst=/opt/data,readonly',
                '--mount',f'type=bind,src={profile},dst=/opt/ce-package,readonly',
                '--mount',f'type=bind,src={ROOT / "tools/model_probe.py"},dst=/probe.py,readonly',
                IMAGE,'/probe.py','/opt/data/profiles/ce-desk/config.yaml','/opt/ce-package/config.yaml')
        except LookupError:
            print('Model key not supplied. Configure the ce-desk model in Hermes before your first investigation.')
        except Exception:
            env.unlink(missing_ok=True)
            raise
        overlay=prepare_session_limits(IMAGE,self.root/'web_server_chat.py')
        validation_network=native_validator.start(self.name)
        socket_volume=native_collector.start(self.name,self.cfg,self.root/'operator',self.volume)
        reader_mount=f'type=volume,src={socket_volume},dst=/opt/ce-reader,readonly'
        args=['docker','run','-d','--rm','--name',self.name,'--label','com.remedigenius.ce=workstation',
              '--memory','3072m','--pids-limit','1024','--env-file',str(env),'-p',f'127.0.0.1:{self.port}:9120',
              '--mount',f'type=volume,src={self.volume},dst=/opt/data',
              '--mount',f'type=bind,src={profile},dst=/opt/ce-package,readonly',
              '--mount',reader_mount,
              '--mount',f'type=bind,src={overlay},dst=/opt/hermes/hermes_cli/web_server_chat.py,readonly']
        try:
            command(*args,IMAGE,'gateway','run')
            command('docker','network','connect',validation_network,self.name)
            for _ in range(30):
                ready=subprocess.run(['docker','exec',self.name,'test','-f','/opt/data/config.yaml'],capture_output=True)
                if ready.returncode==0: break
                time.sleep(2)
            else: raise RuntimeError('Hermes data directory did not initialize')
            command('docker','exec','--user','10000:10000',self.name,'mkdir','-p','/opt/data/work')
            exists=subprocess.run(['docker','exec',self.name,'test','-d','/opt/data/profiles/ce-desk'],capture_output=True).returncode==0
            if not exists:
                command('docker','exec',self.name,'hermes','profile','install','/opt/ce-package','--name','ce-desk','--yes')
            if not exists or upgrade or not pin.exists():
                command('docker','exec','-i','--user','10000:10000',self.name,'/opt/hermes/.venv/bin/python','-',
                        '--home','/opt/data/profiles/ce-desk','--guard-default',
                        input=(ROOT/'tools/upgrade_native_profile.py').read_text(encoding='utf-8'))
            native_ui.seed_model(self.name)
            command('docker','restart',self.name)
            pin.write_text(json.dumps(packaged),encoding='utf-8')
        except Exception:
            self.stop()
            raise
        if self.cfg.get('hermes_ui', False):
            native_ui.start(self.name, int(self.cfg.get('ui_port', 9126)))
        print(f'Native CE: http://127.0.0.1:{self.port}/chat?profile=ce-desk')
        print('Temporary reader credentials expire at '+expires+'. Use run for automatic refresh, or refresh before expiry.')

    def login(self):
        value=json.loads((self.root/'login.json').read_text())
        print('Username: '+value['username']+'\nPassword: '+value['password'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','run','refresh','stop','login'])
    parser.add_argument('--config',required=True)
    parser.add_argument('--upgrade',action='store_true',help='Explicitly apply reviewed CE source changes, retaining profile backups')
    args=parser.parse_args(); ws=Workstation(args.config)
    if args.action in ('start','run'):
        ws.start(upgrade=args.upgrade)
        if args.action=='run':
            try:
                while True:
                    time.sleep(1200)
                    print('Reader credentials refreshed; expire at '+ws.refresh(),flush=True)
            except KeyboardInterrupt:
                ws.stop()
            except Exception:
                ws.stop()
                raise
    elif args.action=='refresh': print('Credentials refreshed; expire at '+ws.refresh())
    elif args.action=='stop': ws.stop()
    else: ws.login()
