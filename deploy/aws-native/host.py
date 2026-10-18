"""Native gateway bootstrap. Host only; model credentials remain in /run tmpfs."""
import json
import os
import shutil
import sys
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/opt/rgce-native')
CFG = json.loads((ROOT / 'config.json').read_text())
SOURCE = ROOT / 'source'


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None).stdout


def aws(*args):
    return json.loads(run('aws', *args, '--region', CFG['region'], '--output', 'json', capture=True))


def attach():
    request = urllib.request.Request('http://169.254.169.254/latest/api/token', method='PUT', headers={'X-aws-ec2-metadata-token-ttl-seconds': '300'})
    token = urllib.request.urlopen(request, timeout=5).read().decode()
    request = urllib.request.Request('http://169.254.169.254/latest/meta-data/instance-id', headers={'X-aws-ec2-metadata-token': token})
    instance = urllib.request.urlopen(request, timeout=5).read().decode()
    for _ in range(90):
        volume = aws('ec2', 'describe-volumes', '--volume-ids', CFG['volume_id'])['Volumes'][0]
        if any(item['InstanceId'] == instance and item['State'] == 'attached' for item in volume['Attachments']):
            break
        if volume['State'] == 'available':
            aws('ec2', 'attach-volume', '--volume-id', CFG['volume_id'], '--instance-id', instance, '--device', '/dev/sdf')
        time.sleep(10)
    else:
        raise SystemExit('Session volume unavailable; previous host must release it. Never force detach.')
    device = Path('/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_' + CFG['volume_id'].replace('-', ''))
    for _ in range(30):
        if device.exists():
            break
        time.sleep(2)
    if not device.exists():
        raise SystemExit('Session volume device not present')
    probe = subprocess.run(['blkid', str(device)], stdout=subprocess.DEVNULL).returncode
    if probe not in (0, 2):
        raise SystemExit('Cannot safely identify the session volume filesystem')
    if probe == 2:
        # Fresh encrypted EBS blocks need not read as all-zero bytes. Authorize
        # initialization from AWS volume identity/creation metadata, not contents.
        created = datetime.fromisoformat(volume['CreateTime'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if volume.get('SnapshotId') or not 0 <= age < 3600 or volume['Size'] != 20:
            raise SystemExit('Unrecognized session volume; fresh-volume initialization window closed')
        run('mkfs.ext4', '-q', '-L', 'rgce-native', str(device))
    Path('/data').mkdir(exist_ok=True)
    if subprocess.run(['mountpoint', '-q', '/data']).returncode:
        run('mount', str(device), '/data')
    for path in (Path('/data/hermes'), Path('/data/hermes/work')):
        path.mkdir(exist_ok=True)
        os.chown(path, 10000, 10000)
    Path('/data/shared').mkdir(exist_ok=True)


def secrets():
    model = aws('secretsmanager', 'get-secret-value', '--secret-id', CFG['model_secret'])['SecretString']
    login = json.loads(aws('secretsmanager', 'get-secret-value', '--secret-id', CFG['dashboard_secret'])['SecretString'])
    values = {'MODEL_API_KEY': model, 'HERMES_DASHBOARD': '1', 'HERMES_DASHBOARD_PORT': '9120',
              'HERMES_DASHBOARD_BASIC_AUTH_USERNAME': login['username'], 'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD': login['password'],
              'HERMES_DASHBOARD_BASIC_AUTH_SECRET': login['secret'], 'AWS_EC2_METADATA_DISABLED': 'true',
              'HERMES_TUI_TOOLSETS': CFG.get('toolsets', 'skills,clarify,ce_runtime')}
    if any(not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in value) for value in values.values()):
        raise SystemExit('Invalid secret shape; no values logged')
    target = Path('/run/rgce-native')
    target.mkdir(mode=0o700, exist_ok=True)
    with os.fdopen(os.open(target/'model.env', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
        stream.write(''.join(name+'='+value+'\n' for name,value in values.items()))


def reader_credentials():
    # Only InvokeFunction on the reviewed read executor; no cloud read/admin rights.
    if not CFG.get('reader_invoker_role'):
        return
    creds = aws('sts','assume-role','--role-arn',CFG['reader_invoker_role'],
                '--role-session-name','ce-reader-invoker','--duration-seconds','3600')['Credentials']
    directory=Path('/run/rgce-native-reader')
    directory.mkdir(mode=0o750,exist_ok=True)
    os.chown(directory, 0, 10000)
    os.chmod(directory, 0o750)
    value='[default]\naws_access_key_id='+creds['AccessKeyId']+'\naws_secret_access_key='+creds['SecretAccessKey']+'\naws_session_token='+creds['SessionToken']+'\n'
    pending=directory/'credentials.pending'
    pending.write_text(value); os.chown(pending,0,10000); os.chmod(pending,0o440); os.replace(pending,directory/'credentials')
    pending=directory/'config.pending'
    pending.write_text(json.dumps({'function':CFG['reader_function'],'region':CFG['region'],'expires':creds['Expiration'],'bucket':CFG['bucket'],'prefix':CFG['prefix']}))
    os.chown(pending,0,10000); os.chmod(pending,0o440); os.replace(pending,directory/'config.json')


def network():
    if subprocess.run(['docker', 'network', 'inspect', 'rgce-native'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('docker', 'network', 'create', '--subnet', '172.29.242.0/24', '--opt', 'com.docker.network.bridge.name=br-rgce-native', 'rgce-native')
    subprocess.run(['iptables', '-N', 'RGCE-NATIVE'], stderr=subprocess.DEVNULL)
    run('iptables', '-F', 'RGCE-NATIVE')
    for line in Path('/etc/resolv.conf').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == 'nameserver' and ':' not in fields[1]:
            for protocol in ('udp', 'tcp'):
                run('iptables', '-A', 'RGCE-NATIVE', '-d', fields[1], '-p', protocol, '--dport', '53', '-j', 'ACCEPT')
    for subnet in ('0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.168.0.0/16','198.18.0.0/15','224.0.0.0/4','240.0.0.0/4'):
        run('iptables','-A','RGCE-NATIVE','-d',subnet,'-j','DROP')
    run('iptables','-A','RGCE-NATIVE','-p','tcp','--dport','443','-j','ACCEPT')
    run('iptables','-A','RGCE-NATIVE','-j','DROP')
    # Permit replies to host-initiated loopback gateway connections, not new agent→host sessions.
    for chain, args in [('INPUT', ['-i','br-rgce-native','-j','DROP']),
                        ('INPUT', ['-i','br-rgce-native','-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT']),
                        ('DOCKER-USER',['-i','br-rgce-native','-j','RGCE-NATIVE'])]:
        if subprocess.run(['iptables','-C',chain,*args],stderr=subprocess.DEVNULL).returncode:
            run('iptables','-I',chain,'1',*args)


def install():
    sys.path.insert(0,str(SOURCE/'tools'))
    import native_validator
    native_validator.start('rgce-native')
    run('python3',str(SOURCE/'tools/native_session_limits.py'),'--image',CFG['image'],
        '--output',str(ROOT/'web_server_chat.py'))
    profiles = ROOT / 'profiles'
    profiles.mkdir(exist_ok=True)
    for name in ('desk',):
        source = SOURCE / CFG['profiles_dir'] / name
        if not (source / 'distribution.yaml').is_file():
            raise SystemExit('Missing native profile: '+name)
        shutil.copytree(source, profiles/name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('cron'))
        config = profiles/name/'config.yaml'
        text = config.read_text().replace('__MODEL_NAME__',json.dumps(CFG['model_name'])).replace('__MODEL_BASE_URL__',json.dumps(CFG['model_base_url']))
        config.write_text(text)
    run('python3','-m','venv',str(ROOT/'venv'))
    run(str(ROOT/'venv/bin/pip'),'install','boto3==1.42.89')
    units = {
      'rgce-native.service': '''[Unit]
Description=Native Hermes CE gateway
After=docker.service
Requires=docker.service
[Service]
ExecStartPre=-/usr/bin/docker rm -f rgce-native
ExecStart=/usr/bin/docker run --rm --name rgce-native --network rgce-native --network rgce-native-validation --env-file /run/rgce-native/model.env -p 127.0.0.1:9120:9120 -v /data/hermes:/opt/data -v /data/shared:/opt/data/shared:ro -v /run/rgce-native-reader:/opt/ce-reader:ro -v /opt/rgce-native/profiles:/opt/rg-profiles:ro -v /opt/rgce-native/profiles/desk:/opt/ce-package:ro -v /opt/rgce-native/web_server_chat.py:/opt/hermes/hermes_cli/web_server_chat.py:ro --memory ''' + str(int(CFG.get('container_memory_mb', 6144))) + '''m --pids-limit 1024 ''' + CFG['image'] + ''' gateway run
ExecStop=/usr/bin/docker stop -t 30 rgce-native
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
''',
      'rgce-native-boot.service': '''[Unit]
Description=Restore retained native Hermes state and tmpfs credentials
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
TimeoutStartSec=900
ExecStart=/usr/bin/python3 /opt/rgce-native/source/deploy/aws-native/host.py
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
''',
      'rgce-native-hydrate.service': '''[Unit]
Description=Hydrate authoritative CE S3 evidence, no LLM
[Service]
Type=oneshot
ExecStart=/opt/rgce-native/venv/bin/python /opt/rgce-native/source/tools/native_data.py hydrate --bucket '''+CFG['bucket']+' --prefix '+CFG['prefix']+''' --destination /data/shared
Environment=AWS_DEFAULT_REGION='''+CFG['region']+'''
''',
      'rgce-native-hydrate.timer': '''[Unit]
Description=Refresh local read-only evidence view, no model calls
[Timer]
OnBootSec=30
OnUnitActiveSec=30
Unit=rgce-native-hydrate.service
[Install]
WantedBy=timers.target
'''}
    if CFG.get('knowledge_view'):
        # This directory is a disposable read-only cache, not the source library.
        uri='s3://'+CFG['bucket']+'/'+CFG['prefix']+'/knowledge/'+CFG['knowledge_view']+'/'
        units['rgce-native-hydrate.service'] += 'ExecStartPost=/usr/bin/aws s3 sync '+uri+' /data/shared/knowledge --delete --only-show-errors\n'
    units['rgce-reader-creds.service'] = "[Unit]\nDescription=Refresh invoke-only CE capability credentials\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /opt/rgce-native/source/deploy/aws-native/host.py --refresh-reader\n"
    units['rgce-reader-creds.timer'] = "[Unit]\nDescription=Refresh CE capability token\n[Timer]\nOnBootSec=60\nOnUnitActiveSec=1200\n[Install]\nWantedBy=timers.target\n"
    for name, body in units.items():
        Path('/etc/systemd/system',name).write_text(body)
    run('systemctl','daemon-reload')
    # Collection is one deterministic boot invocation, never an agent or model schedule.
    response = aws('lambda','invoke','--function-name',CFG['collector_arn'], '/run/rgce-native/collection.json')
    if response.get('FunctionError'):
        raise SystemExit('Discovery failed; inspect host-only collection receipt')
    run('systemctl','start','rgce-native-hydrate.service')
    run('docker','pull',CFG['image'])
    run('docker','run','--rm','--entrypoint','/opt/hermes/.venv/bin/python',
        '--env-file','/run/rgce-native/model.env',
        '-v','/data/hermes:/opt/data:ro',
        '-v',str(profiles/'desk')+':/opt/ce-package:ro',
        '-v',str(SOURCE/'tools/model_probe.py')+':/probe.py:ro',
        CFG['image'],'/probe.py','/opt/data/profiles/ce-desk/config.yaml','/opt/ce-package/config.yaml')
    # Preserve the former analyst home outside Hermes's active profile directory.
    # Stop writers before moving its databases; never delete conversation history.
    legacy = Path('/data/hermes/profiles/ce-analyst')
    if legacy.exists():
        run('systemctl','stop','rgce-native.service')
        archive = Path('/data/hermes/retired-profiles')
        archive.mkdir(exist_ok=True)
        destination = archive / ('ce-analyst-' + str(time.time_ns()))
        shutil.move(str(legacy), str(destination))
    run('systemctl','restart','rgce-native.service')
    for _ in range(90):
        if subprocess.run(['docker','exec','rgce-native','true'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0:
            break
        time.sleep(2)
    for name in ('desk',):
        installed = 'ce-' + name
        exists = subprocess.run(['docker','exec','rgce-native','test','-d','/opt/data/profiles/'+installed]).returncode == 0
        if exists:
            # Reboot/Spot replacement is recovery, not an operator profile upgrade.
            # Preserve model routing, user skills, plugins and edited instructions.
            print('Retained profile preserved: '+installed+'; upgrades are operator initiated')
        else:
            run('docker','exec','rgce-native','hermes','profile','install','/opt/rg-profiles/'+name,'--name',installed,'--yes')
        # The CE runtime is operator-owned code, mounted read-only. User-added
        # plugins remain separate; they require explicit operator enablement.
        plugins = Path('/data/hermes/profiles',installed,'plugins')
        plugins.mkdir(exist_ok=True)
        link = plugins/'ce-runtime'
        if not link.is_symlink():
            if link.exists():
                backup = Path('/data/hermes/ce-upgrades')/('plugin-'+str(time.time_ns()))
                backup.parent.mkdir(exist_ok=True)
                shutil.move(str(link),str(backup))
            link.symlink_to('/opt/ce-package/plugins/ce-runtime')
    subprocess.run(['docker','exec','-i','--user','10000:10000','rgce-native',
                    '/opt/hermes/.venv/bin/python','-','--home','/opt/data/profiles/ce-desk',
                    '--guard-default-only'], input=(SOURCE/'tools/upgrade_native_profile.py').read_text(),
                    text=True,check=True)
    run('systemctl','restart','rgce-native.service')
    import native_ui
    if CFG.get('hermes_ui', False):
        for _ in range(30):
            if subprocess.run(['docker','exec','rgce-native','true'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(2)
        native_ui.start('rgce-native', 9122)
    else:
        native_ui.stop('rgce-native')
    # Boot service owns gateway startup so reboot cannot race volume/secrets setup.
    run('systemctl','enable','rgce-native-boot.service')
    run('systemctl','enable','--now','rgce-native-hydrate.timer')
    run('systemctl','enable','--now','rgce-reader-creds.timer')


if __name__ == '__main__':
    if '--refresh-reader' in sys.argv:
        reader_credentials()
        raise SystemExit(0)
    attach()
    secrets()
    reader_credentials()
    network()
    install()
