"""Single-host CE bootstrap; cloud collection stays on this host."""
import json,os,re,shutil,sys,subprocess,time,urllib.request,secrets
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/opt/rgce-native')
SOURCE=ROOT/'source'
CFG=json.loads((ROOT/'config.json').read_text())
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

def install(upgrade=False):
    attach();network()
    sys.path.insert(0,str(SOURCE/'tools'))
    import native_validator,native_ui,native_session_limits
    envdir=Path('/run/ce-collector');envdir.mkdir(exist_ok=True);os.chown(envdir,10000,10000)
    env={'AWS_DEFAULT_REGION':CFG['region'],'ACCOUNT_ID':CFG['account_id'],'BUCKET':CFG['bucket'],'PREFIX':CFG['prefix'],
         'INTERVAL_HOURS':'24','CHECKS':json.dumps([{'target':'default','region':CFG['region'],'service':'securityhub','operation':'get_findings','parameters':{},'max_pages':2},{'target':'default','region':CFG['region'],'service':'config','operation':'describe_configuration_recorders','parameters':{},'max_pages':1}]),
         'TARGETS':json.dumps({'default':{'account_id':CFG['account_id'],'regions':[CFG['region']],**({'role_arn':CFG['audit_role_arn'],'audit_role_arn':CFG['audit_role_arn']} if CFG.get('audit_role_arn') else {})}})}
    envfile=ROOT/'collector.env';envfile.write_text(''.join(k+'='+v+'\n' for k,v in env.items()));envfile.chmod(0o600)
    run('docker','build','-t','remedigenius-collector:local',str(SOURCE/'deploy/collector'))
    # Restore before Hermes opens any database. Existing retained EBS wins.
    home=Path('/data/hermes')
    if not (home/'config.yaml').exists():
        work=home/'work'
        if work.is_dir() and not any(work.iterdir()):work.rmdir()
        if not any(home.iterdir()):
            run('docker','run','--rm','--network','host','--env-file',str(envfile),'-v','/data/hermes:/state',
                'remedigenius-collector:local','python','state_store.py','restore')
    if (home/'.restore-in-progress').exists():raise RuntimeError('Incomplete state restore; stop before opening databases')
    (home/'shared').mkdir(exist_ok=True);os.chown(home/'shared',10000,10000)
    loginfile=home/'ce-login.json'
    if not loginfile.exists():
        loginfile.write_text(json.dumps({'username':'owner','password':secrets.token_urlsafe(24),'secret':secrets.token_hex(32)}));loginfile.chmod(0o600);os.chown(loginfile,10000,10000)
    login=json.loads(loginfile.read_text())
    model=aws('secretsmanager','get-secret-value','--secret-id',CFG['model_secret'])['SecretString'] if CFG.get('model_secret') else ''
    values={'HERMES_DASHBOARD':'1','HERMES_DASHBOARD_PORT':'9120','HERMES_DASHBOARD_BASIC_AUTH_USERNAME':login['username'],
            'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD':login['password'],'HERMES_DASHBOARD_BASIC_AUTH_SECRET':login['secret'],
            'AWS_EC2_METADATA_DISABLED':'true','HERMES_TUI_TOOLSETS':'skills,clarify,ce_runtime'}
    if model:values['MODEL_API_KEY']=model
    if any('\n' in v or '\r' in v for v in values.values()):raise ValueError('Invalid credential shape')
    runtime=Path('/run/rgce-native');runtime.mkdir(exist_ok=True,mode=0o700)
    envpath=runtime/'model.env';envpath.write_text(''.join(k+'='+v+'\n' for k,v in values.items()));envpath.chmod(0o600)
    profiles=ROOT/'profiles';shutil.copytree(SOURCE/'profiles/ce/desk',profiles/'desk',dirs_exist_ok=True)
    cfg=profiles/'desk/config.yaml'
    seed=cfg.read_text()
    if model:
        seed=seed.replace('__MODEL_NAME__',json.dumps(CFG['model_name'])).replace('__MODEL_BASE_URL__',json.dumps(CFG['model_base_url']))
    else:
        # This reviewed template starts with a model mapping. Leave it unset on
        # keyless first boot so native Hermes onboarding remains visible. The
        # retained profile is not overwritten on subsequent boots.
        seed,count=re.subn(r'\Amodel:\n(?:[ \t]+.*\n)*','',seed,count=1)
        if count!=1:raise RuntimeError('Unexpected CE model template; refuse an unconfigured model seed')
    cfg.write_text(seed)
    native_validator.start('rgce-native')
    native_session_limits.prepare(CFG['image'],ROOT/'web_server_chat.py')
    units={
     'rgce-collector.service': '''[Unit]
After=docker.service
Requires=docker.service
[Service]
ExecStartPre=-/usr/bin/docker rm -f rgce-collector
ExecStart=/usr/bin/docker run --rm --name rgce-collector --network host --env-file /opt/rgce-native/collector.env --read-only --cap-drop ALL --security-opt no-new-privileges --memory 512m --pids-limit 128 --tmpfs /tmp:uid=10000,gid=10000 -v /run/ce-collector:/run/ce-collector -v /data/hermes:/state remedigenius-collector:local
Restart=on-failure
RestartSec=5
''',
     'rgce-native.service': '''[Unit]
After=rgce-collector.service
Requires=rgce-collector.service
[Service]
ExecStartPre=-/usr/bin/docker rm -f rgce-native
ExecStart=/usr/bin/docker run --rm --name rgce-native --network rgce-native --network rgce-native-validation --env-file /run/rgce-native/model.env -p 127.0.0.1:9120:9120 -v /data/hermes:/opt/data -v /data/hermes/shared:/opt/data/shared:ro -v /run/ce-collector:/opt/ce-reader:ro -v /opt/rgce-native/profiles/desk:/opt/ce-package:ro -v /opt/rgce-native/web_server_chat.py:/opt/hermes/hermes_cli/web_server_chat.py:ro --memory '''+str(CFG.get('container_memory_mb',6144))+'''m --pids-limit 1024 '''+CFG['image']+''' gateway run
ExecStop=/usr/bin/docker stop -t 30 rgce-native
Restart=always
RestartSec=10
''',
     'rgce-state.service': '''[Service]
Type=oneshot
TimeoutStartSec=120
ExecStart=/usr/bin/docker exec rgce-collector python state_store.py backup
''',
     'rgce-state.timer': '''[Timer]
OnBootSec=120
OnUnitActiveSec=120
[Install]
WantedBy=timers.target
''',
     'rgce-native-boot.service': '''[Unit]
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
TimeoutStartSec=1800
ExecStart=/usr/bin/python3 /opt/rgce-native/source/deploy/aws-single/host.py
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
'''}
    for name,body in units.items():Path('/etc/systemd/system',name).write_text(body)
    run('systemctl','daemon-reload');run('systemctl','restart','rgce-collector.service')
    for _ in range(60):
        if (envdir/'collector.sock').exists():break
        time.sleep(2)
    else:raise RuntimeError('Collector failed; check rgce-collector logs')
    run('systemctl','restart','rgce-native.service')
    for _ in range(90):
        if subprocess.run(['docker','exec','rgce-native','test','-f','/opt/data/config.yaml'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
        time.sleep(2)
    profile=home/'profiles/ce-desk'
    fresh = not profile.exists()
    if fresh:run('docker','exec','rgce-native','hermes','profile','install','/opt/ce-package','--name','ce-desk','--yes')
    if fresh or upgrade:
        subprocess.run(['docker','exec','-i','--user','10000:10000','rgce-native','/opt/hermes/.venv/bin/python','-',
                    '--home','/opt/data/profiles/ce-desk','--guard-default'],input=(SOURCE/'tools/upgrade_native_profile.py').read_text(),text=True,check=True)
    else:
        # Checkpoints omit symlinks. Recreate only known CE links, preserving
        # operator-owned configuration, skills and sessions during host recovery.
        links = {profile/'plugins/ce-runtime':'/opt/ce-package/plugins/ce-runtime'}
        links.update({home/n:'/opt/data/profiles/ce-desk/'+n for n in ('SOUL.md','skills','plugins')})
        for link,target in links.items():
            if not link.exists() and not link.is_symlink():
                link.parent.mkdir(parents=True,exist_ok=True)
                link.symlink_to(target)
                os.lchown(link,10000,10000)
    native_ui.seed_model('rgce-native')
    run('docker','restart','rgce-native')
    if CFG.get('hermes_ui'):native_ui.start('rgce-native',9122)
    run('systemctl','enable','rgce-native-boot.service')
    run('systemctl','enable','--now','rgce-state.timer')
    run('systemctl','start','rgce-state.service')
    print('CE ready for model onboarding. Retrieve dashboard credentials locally from /data/hermes/ce-login.json; never paste them into chat.')

if __name__=='__main__':install(upgrade='--upgrade' in sys.argv)
