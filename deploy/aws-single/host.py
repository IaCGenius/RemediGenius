"""RemediGenius Community Edition (RemediGenius-CE) — Spot host bootstrap.

The instance is disposable: S3 holds the durable state. At boot this script restores the
Hermes home and the desk state from S3 (only into empty folders), starts the desk service
(the only component with AWS credentials, reading through the read-only audit role), and
runs Hermes in the pinned container with the `remedigenius` profile and no AWS credentials.
The desk service checkpoints both homes to S3 every 2 minutes, after scans and decisions,
on shutdown, and as soon as AWS announces a Spot interruption.
"""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path('/opt/remedigenius')          # root-only: config, source archive
SOURCE = ROOT / 'source'
UID = 10000                               # Hermes container user; also the desk service user
HERMES_HOME = Path('/data/hermes')
DESK = Path('/data/rgtriage')
IAC = Path('/data/iac')
RUNDIR = Path('/run/rgtriage')
SOCKET = RUNDIR / 'rgtriage.sock'
VENV = Path('/opt/rgtriage/venv')
CODE = Path('/opt/rgtriage/src')          # readable copy of the rgtriage package for uid 10000
PACKAGE = Path('/opt/remedigenius/package')
LOGIN = HERMES_HOME / 'remedigenius-login.json'
API_KEY = HERMES_HOME / '.remedigenius-api-key'
CONTAINER = 'remedigenius'
WEBUI_CONTAINER = 'remedigenius-webui'
# Community Hermes WebUI (MIT, https://github.com/nesquena/hermes-webui), pinned; not maintained by RemediGenius.
WEBUI_IMAGE = 'ghcr.io/nesquena/hermes-webui:0.52.492@sha256:e507cafa7b112de9abd58348423ded28a8182539e6ebb5f95be603f20aff52e6'
SUBNET = '172.29.242.0/24'
API_PORT = 8642
PROFILE = 'remedigenius'
PACKAGES = ['boto3==1.42.89', 'PyYAML==6.0.2']
TERRAFORM = ('1.12.2', '1eaed12ca41fcfe094da3d76a7e9aa0639ad3409c43be0103ee9f5a1ff4b7437')
# Inside the container the desk paths are identical, so no path translation is needed.
PROPOSALS = '/opt/data/proposals'  # inside the Hermes home: Hermes only permits writes under /opt/data
CONTAINER_MOUNTS = ['-v', f'{DESK.as_posix()}:{DESK.as_posix()}:ro',
                    '-v', f'{RUNDIR.as_posix()}:{RUNDIR.as_posix()}', '-v', f'{IAC.as_posix()}:{IAC.as_posix()}:ro']


def run(*args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)


def durable_url(cfg):
    return f"s3://{cfg['bucket']}/state"


def ensure_user():
    # systemd resolves User=/Group= through NSS, so uid and gid 10000 must exist on the host.
    if subprocess.run(['getent', 'group', str(UID)], capture_output=True).returncode:
        run('groupadd', '--system', '--gid', str(UID), 'remedigenius')
    if subprocess.run(['getent', 'passwd', str(UID)], capture_output=True).returncode:
        run('useradd', '--system', '--uid', str(UID), '--gid', str(UID), '--no-create-home', '--shell', '/sbin/nologin',
            'remedigenius')


def install_runtime():
    ensure_user()
    if not (VENV / 'bin/python').exists():
        run('dnf', 'install', '-y', '-q', 'python3.11', 'python3.11-pip', 'unzip')
        run('python3.11', '-m', 'venv', str(VENV))
    run(str(VENV / 'bin/pip'), 'install', '--quiet', '--disable-pip-version-check', *PACKAGES)
    if CODE.exists():
        shutil.rmtree(CODE)
    shutil.copytree(SOURCE / 'rgtriage', CODE / 'rgtriage', ignore=shutil.ignore_patterns('__pycache__'))
    for path in [CODE, *CODE.rglob('*')]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    version, digest = TERRAFORM
    binary = Path('/usr/local/bin/terraform')
    if binary.exists() and version in subprocess.run([str(binary), 'version'], capture_output=True, text=True).stdout:
        return
    data = urllib.request.urlopen(f'https://releases.hashicorp.com/terraform/{version}/terraform_{version}_linux_amd64.zip',
                                  timeout=120).read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit('Terraform download checksum mismatch')
    archive = Path('/tmp/terraform.zip')
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as z:
        binary.write_bytes(z.read('terraform'))
    binary.chmod(0o755)
    archive.unlink()


def desk(*args, user=None, **kw):
    """Run the rgtriage CLI with the host venv (as root unless a user is given)."""
    env = dict(os.environ, PYTHONPATH=str(CODE), RGTRIAGE_HOME=str(DESK), HOME=str(DESK / '.home'),
               AWS_STS_REGIONAL_ENDPOINTS='regional')
    prefix = ['setpriv', f'--reuid={UID}', f'--regid={UID}', '--clear-groups'] if user else []
    return run(*prefix, str(VENV / 'bin/python'), '-m', 'rgtriage', *args, env=env, **kw)


def restore_state(cfg):
    """Durable copy first: an empty disk (new Spot instance) is filled from the latest S3 checkpoints."""
    for path in (HERMES_HOME, DESK):
        path.mkdir(parents=True, exist_ok=True)
    result = desk('durable', 'restore', '--url', durable_url(cfg), '--home', f'hermes={HERMES_HOME}',
                  '--home', f'desk={DESK}', '--owner', f'{UID}:{UID}', capture_output=True)
    print(result.stdout.strip())
    for path in (HERMES_HOME, DESK, HERMES_HOME / 'proposals', DESK / '.home', DESK / '.lineage', IAC, HERMES_HOME / 'work'):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, UID, UID)
    for path in (DESK / '.lineage').iterdir():
        os.chown(path, UID, UID)
    # Same path on the host as in the container, so the desk can validate files the agent proposes.
    link = Path('/opt/data')
    if not link.is_symlink():
        link.symlink_to(HERMES_HOME)


def member_accounts(cfg) -> list[dict]:
    """Member accounts from Terraform: common role name per account id, plus any explicit role ARNs."""
    members = {}
    for account_id in cfg.get('member_account_ids') or []:
        members[account_id] = f"arn:aws:iam::{account_id}:role/{cfg.get('member_role_name') or 'RemediGeniusReadOnly'}"
    for arn in cfg.get('member_role_arns') or []:
        members[arn.split(':')[4]] = arn
    return [{'name': f'member-{a}', 'account_id': a, 'role_arn': r, 'criticality': 'business_critical'}
            for a, r in members.items()]


MERGE = """
import json, sys, yaml
path, data = sys.argv[1], json.load(sys.stdin)
current = yaml.safe_load(open(path)) if data['exists'] else None
if current is None:
    current = data['initial']
    changed = True
else:
    known = {str(a.get('account_id')) for a in current.get('accounts', [])}
    added = [a for a in data['members'] if a['account_id'] not in known]
    current.setdefault('accounts', []).extend(added)
    changed = bool(added)
if changed:
    with open(path, 'w') as f:
        f.write(data['header'] + yaml.safe_dump(current, sort_keys=False))
print(json.dumps({'changed': changed}))
"""


def write_desk_profile(cfg):
    """First boot writes triage.yaml; later boots only add member accounts newly listed in Terraform.

    Everything else in the file is the operator's (it is kept in the S3 checkpoints). Other organization
    accounts and delegated-administrator status are found by the desk at every scan, not configured here.
    """
    profile = DESK / 'triage.yaml'
    main_account = {'name': cfg['name'], 'account_id': cfg['account_id'], 'role_arn': cfg['audit_role_arn'],
                    'criticality': 'business_critical'}
    initial = {'name': cfg['name'], 'regions': cfg.get('regions') or [cfg['region']],
               'accounts': [main_account] + member_accounts(cfg),
               'goals': [{'text': 'Protect customer data stored in S3 and databases',
                          'boost': {'resource_types': ['AwsS3Bucket', 'AwsRdsDbInstance', 'AwsDynamoDbTable'], 'points': 5}},
                         {'text': 'Detect and stop misuse of privileged identities',
                          'boost': {'resource_types': ['AwsIamUser', 'AwsIamRole', 'AwsIamAccessKey'],
                                    'signals': ['identity_risk', 'root_usage'], 'points': 5}}],
               'iac_paths': [str(IAC)],
               'organization': {'discover': True, 'member_role_name': cfg.get('member_role_name') or 'RemediGeniusReadOnly'}}
    request = {'exists': profile.exists(), 'initial': initial, 'members': member_accounts(cfg),
               'header': '# RemediGenius-CE desk profile. Edit freely; it is saved to S3. Terraform only adds member accounts.\n'}
    result = run(str(VENV / 'bin/python'), '-c', MERGE, str(profile), input=json.dumps(request), capture_output=True).stdout
    os.chown(profile, UID, UID)
    print(f'triage.yaml: {result.strip()}')


def network():
    """Hermes container egress: HTTPS to the internet only; no instance metadata, no private ranges."""
    if subprocess.run(['docker', 'network', 'inspect', CONTAINER], capture_output=True).returncode:
        run('docker', 'network', 'create', '--subnet', '172.29.242.0/24', '--opt',
            'com.docker.network.bridge.name=br-remedigenius', CONTAINER)
    subprocess.run(['iptables', '-N', 'REMEDIGENIUS'], stderr=subprocess.DEVNULL)
    run('iptables', '-F', 'REMEDIGENIUS')
    # Container to container on this network only: the WebUI reaches the Hermes API server; replies come back.
    run('iptables', '-A', 'REMEDIGENIUS', '-s', SUBNET, '-d', SUBNET, '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT')
    run('iptables', '-A', 'REMEDIGENIUS', '-s', SUBNET, '-d', SUBNET, '-p', 'tcp', '--dport', str(API_PORT), '-j', 'ACCEPT')
    for line in Path('/etc/resolv.conf').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == 'nameserver' and ':' not in fields[1]:
            for protocol in ('udp', 'tcp'):
                run('iptables', '-A', 'REMEDIGENIUS', '-d', fields[1], '-p', protocol, '--dport', '53', '-j', 'ACCEPT')
    for subnet in ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '172.16.0.0/12',
                   '192.168.0.0/16', '198.18.0.0/15', '224.0.0.0/4', '240.0.0.0/4'):
        run('iptables', '-A', 'REMEDIGENIUS', '-d', subnet, '-j', 'DROP')
    run('iptables', '-A', 'REMEDIGENIUS', '-p', 'tcp', '--dport', '443', '-j', 'ACCEPT')
    run('iptables', '-A', 'REMEDIGENIUS', '-j', 'DROP')
    for chain, args in [('INPUT', ['-i', 'br-remedigenius', '-j', 'DROP']),
                        ('INPUT', ['-i', 'br-remedigenius', '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT']),
                        ('DOCKER-USER', ['-i', 'br-remedigenius', '-j', 'REMEDIGENIUS'])]:
        if subprocess.run(['iptables', '-C', chain, *args], stderr=subprocess.DEVNULL).returncode:
            run('iptables', '-I', chain, '1', *args)


def seed_model(config_text: str, model_seed) -> str:
    """Fill model placeholders when a key is supplied; otherwise drop the model block so Hermes asks for one."""
    if model_seed:
        name, base_url = model_seed
        return config_text.replace('__MODEL_NAME__', json.dumps(name)).replace('__MODEL_BASE_URL__', json.dumps(base_url))
    out, skipping = [], False
    for line in config_text.splitlines(keepends=True):
        if line.startswith('model:'):
            skipping = True
            continue
        if skipping and (line.startswith((' ', '\t')) or not line.strip()):
            continue
        skipping = False
        out.append(line)
    return ''.join(out)


WATCH_SCRIPT = '''"""Hermes cron script: print only new P1/P2 security findings (empty output = silent)."""
import json, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(1200); s.connect(%r)
s.sendall(json.dumps({"args": ["watch", "--min-priority", "P2"]}).encode() + b"\\n")
data = b""
while True:
    chunk = s.recv(65536)
    if not chunk:
        break
    data += chunk
reply = json.loads(data)
print(reply.get("stdout", "") if reply.get("rc") == 0 else "rgtriage watch failed: " + reply.get("stderr", "")[-600:], end="")
'''


def sync_profile(source: Path, hermes_home: Path):
    """Refresh code-owned profile files every boot; config.yaml, .env, sessions and memory stay as they are."""
    package = source / 'profiles/remedigenius'
    profile = hermes_home / 'profiles' / PROFILE
    shutil.copy2(package / 'SOUL.md', profile / 'SOUL.md')
    for skill in (package / 'skills').iterdir():
        target = profile / 'skills' / skill.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(skill, target)
    plugin = profile / 'plugins/rg-triage'
    if plugin.exists():
        shutil.rmtree(plugin)
    shutil.copytree(package / 'plugins/rg-triage', plugin, ignore=shutil.ignore_patterns('__pycache__'))
    (plugin / 'local.json').write_text(json.dumps({'socket': SOCKET.as_posix(), 'home': DESK.as_posix(), 'proposals': PROPOSALS}))
    scripts = profile / 'scripts'
    scripts.mkdir(exist_ok=True)
    (scripts / 'rgtriage-watch.py').write_text(WATCH_SCRIPT % SOCKET.as_posix())
    # Knowledge tab (dashboard plugin): drafts and imports reach the desk through the folders below.
    tab = hermes_home / 'plugins' / 'rg-knowledge'
    if tab.exists():
        shutil.rmtree(tab)
    shutil.copytree(package / 'dashboard-plugins/rg-knowledge', tab, ignore=shutil.ignore_patterns('__pycache__', 'local.json'))
    (tab / 'local.json').write_text(json.dumps({'socket': SOCKET.as_posix(), 'home': DESK.as_posix(), 'proposals': PROPOSALS,
                                                'inbox': '/opt/data/knowledge-inbox', 'files': '/opt/data/knowledge-files',
                                                'profile': PROFILE, 'improve': '/opt/data/rg-improve',
                                                'package': '/opt/remedigenius-package'}))
    folders = [hermes_home / 'proposals' / 'knowledge', hermes_home / 'knowledge-inbox', hermes_home / 'knowledge-files',
               hermes_home / 'rg-improve', hermes_home / 'rg-traces']
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    # Skill improvements a person approved survive instance replacement when made for this shipped version.
    sys.path.insert(0, str(tab))
    from improve.runner import apply_approved
    print(f"approved skill improvements: {json.dumps(apply_approved(hermes_home / 'rg-improve', package / 'skills', profile / 'skills'))}")
    for path in [profile, *profile.rglob('*'), hermes_home / 'plugins', tab, *tab.rglob('*'), *folders]:
        if hasattr(os, 'lchown'):
            os.lchown(path, UID, UID)
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else (0o600 if path.name == '.env' else 0o644))


def units(cfg: dict) -> dict:
    env = (f'Environment=RGTRIAGE_HOME={DESK.as_posix()}\nEnvironment=PYTHONPATH={CODE.as_posix()}\n'
           f'Environment=HOME={DESK.as_posix()}/.home\nEnvironment=AWS_DEFAULT_REGION={cfg["region"]}\n'
           f'Environment=AWS_STS_REGIONAL_ENDPOINTS=regional\nEnvironment=TF_PLUGIN_CACHE_DIR={DESK.as_posix()}/.home/plugins\n'
           f'Environment=REMEDIGENIUS_MODEL_NAME={cfg.get("model_name") or ""}\n'
           f'Environment=REMEDIGENIUS_MODEL_BASE_URL={cfg.get("model_base_url") or ""}\n')
    harden = (f'User={UID}\nGroup={UID}\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\n'
              f'ReadWritePaths={DESK.as_posix()}\n')
    python = (VENV / 'bin/python').as_posix()
    homes = f'--home hermes={HERMES_HOME.as_posix()} --home desk={DESK.as_posix()}'
    store = durable_url(cfg)
    memory = int(cfg.get('container_memory_mb', 6144))
    mounts = ' '.join(CONTAINER_MOUNTS)
    return {
        'remedigenius-desk.service': f'''[Unit]
Description=RemediGenius-CE desk: read-only AWS access, Unix socket API, S3 checkpoints
After=network-online.target
[Service]
{env}{harden}RuntimeDirectory=rgtriage
RuntimeDirectoryPreserve=yes
RuntimeDirectoryMode=0750
ExecStart={python} -m rgtriage serve --socket {SOCKET.as_posix()} --durable {store} {homes} --every 120 --spot
ExecStopPost={python} -m rgtriage durable checkpoint --url {store} {homes}
TimeoutStopSec=120
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
''',
        'remedigenius-scan.service': f'''[Unit]
Description=RemediGenius-CE scheduled scan
[Service]
Type=oneshot
TimeoutStartSec=1800
{env}{harden}ExecStart={python} -m rgtriage scan --quiet
''',
        'remedigenius-scan.timer': f'''[Timer]
OnBootSec=3min
OnUnitActiveSec={int(cfg.get('scan_interval_hours', 6))}h
[Install]
WantedBy=timers.target
''',
        'remedigenius-hermes.service': f'''[Unit]
Description=RemediGenius-CE Hermes (pinned image, no AWS credentials)
After=docker.service remedigenius-desk.service
Requires=docker.service
[Service]
ExecStartPre=-/usr/bin/docker rm -f {CONTAINER}
ExecStart=/usr/bin/docker run --rm --name {CONTAINER} --network {CONTAINER} --env-file /run/remedigenius/hermes.env -p 127.0.0.1:9120:9120 -v {HERMES_HOME.as_posix()}:/opt/data {mounts} -v {PACKAGE.as_posix()}:/opt/remedigenius-package:ro --memory {memory}m --pids-limit 1024 {cfg['image']} gateway run
ExecStop=/usr/bin/docker stop -t 30 {CONTAINER}
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
''',
        # Community Hermes WebUI (MIT, github.com/nesquena/hermes-webui): its code comes from the pinned WebUI image and
        # runs with the pinned Hermes image's own Python (the documented "manual launch"), so every Hermes module it reads
        # (skills, kanban, cron) matches the agent. Chat goes through the Hermes gateway of the remedigenius profile, so
        # skills, plugin guards and approvals stay in the Hermes container.
        'remedigenius-webui.service': f'''[Unit]
Description=Hermes WebUI (community project, MIT, pinned) for RemediGenius-CE, gateway mode
After=remedigenius-hermes.service
Requires=docker.service
[Service]
ExecStartPre=-/usr/bin/docker rm -f {WEBUI_CONTAINER}
ExecStartPre=-/usr/bin/docker volume rm -f {WEBUI_CONTAINER}-src
ExecStartPre=/usr/bin/docker run --rm --entrypoint sh -v {WEBUI_CONTAINER}-src:/webui {WEBUI_IMAGE} -c "cp -a /apptoo/. /webui/ && chmod -R a+rX,go-w /webui"
ExecStart=/usr/bin/docker run --rm --name {WEBUI_CONTAINER} --network {CONTAINER} --user {UID}:{UID} --entrypoint /opt/hermes/.venv/bin/python --env-file /run/remedigenius/webui.env -e HOME=/opt/data -e HERMES_HOME=/opt/data -e HERMES_WEBUI_STATE_DIR=/opt/data/webui -e HERMES_WEBUI_HOST=0.0.0.0 -e HERMES_WEBUI_PORT=8787 -e HERMES_WEBUI_SKIP_ONBOARDING=1 -e HERMES_WEBUI_CHAT_BACKEND=gateway -e HERMES_WEBUI_GATEWAY_BASE_URL=http://{CONTAINER}:{API_PORT}/p/{PROFILE} -e HERMES_API_URL=http://{CONTAINER}:{API_PORT} -e HERMES_WEBUI_AGENT_DIR=/opt/hermes -e AWS_EC2_METADATA_DISABLED=true -w /webui -v {HERMES_HOME.as_posix()}:/opt/data -v {WEBUI_CONTAINER}-src:/webui:ro -p 127.0.0.1:8787:8787 --memory 1024m --pids-limit 512 {cfg['image']} /webui/server.py
ExecStop=/usr/bin/docker stop -t 20 {WEBUI_CONTAINER}
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
''',
    }


def hermes_env(cfg, model_key):
    if not LOGIN.exists():
        LOGIN.write_text(json.dumps({'username': 'owner', 'password': secrets.token_urlsafe(24), 'secret': secrets.token_hex(32)}))
        LOGIN.chmod(0o600)
        os.chown(LOGIN, UID, UID)
    login = json.loads(LOGIN.read_text())
    if not API_KEY.exists():  # Hermes API server key, used only by the WebUI on the private network
        API_KEY.write_text(secrets.token_urlsafe(32))
        API_KEY.chmod(0o600)
        os.chown(API_KEY, UID, UID)
    api_key = API_KEY.read_text().strip()
    values = {'HERMES_DASHBOARD': '1', 'HERMES_DASHBOARD_PORT': '9120',
              'HERMES_DASHBOARD_BASIC_AUTH_USERNAME': login['username'],
              'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD': login['password'],
              'HERMES_DASHBOARD_BASIC_AUTH_SECRET': login['secret'],
              'AWS_EC2_METADATA_DISABLED': 'true', 'HERMES_TUI_TOOLSETS': 'skills,clarify,file,rg_triage'}
    if cfg.get('webui', True):
        values.update({'API_SERVER_ENABLED': 'true', 'API_SERVER_HOST': '0.0.0.0', 'API_SERVER_PORT': str(API_PORT)})
    if model_key:
        values['MODEL_API_KEY'] = model_key
    if any('\n' in v or '\r' in v for v in values.values()):
        raise ValueError('Invalid credential shape')
    runtime = Path('/run/remedigenius')
    runtime.mkdir(exist_ok=True, mode=0o700)
    path = runtime / 'hermes.env'
    path.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
    path.chmod(0o600)
    webui = {'HERMES_WEBUI_PASSWORD': login['password'], 'HERMES_WEBUI_GATEWAY_API_KEY': api_key}
    (runtime / 'webui.env').write_text(''.join(f'{k}={v}\n' for k, v in webui.items()))
    (runtime / 'webui.env').chmod(0o600)


def set_api_key() -> None:
    """The API server key lives in the Hermes .env files (they win over the container environment):
    the root one for the shared gateway, the profile one for /p/remedigenius/ requests."""
    key = API_KEY.read_text().strip()
    for env in (HERMES_HOME / '.env', HERMES_HOME / 'profiles' / PROFILE / '.env'):
        if not env.parent.exists():
            continue
        lines = [l for l in (env.read_text().splitlines() if env.exists() else []) if not l.startswith('API_SERVER_KEY=')]
        env.write_text('\n'.join(lines + [f'API_SERVER_KEY={key}']) + '\n')
        env.chmod(0o600)
        os.chown(env, UID, UID)


def in_container(*args, check=True, **kw):
    return subprocess.run(['docker', 'exec', '--user', f'{UID}:{UID}', CONTAINER, *args], check=check, text=True, **kw)


def seed_model_key():
    """Native Hermes profiles do not inherit process secrets: copy MODEL_API_KEY into the profile .env once."""
    in_container('python', '-c', f'''
import os
from pathlib import Path
p = Path('/opt/data/profiles/{PROFILE}/.env')
s = p.read_text() if p.exists() else ''
key = os.environ.get('MODEL_API_KEY', '')
if key and not any(l.startswith('MODEL_API_KEY=') for l in s.splitlines()):
    p.write_text(s.rstrip() + ('\\n' if s.strip() else '') + 'MODEL_API_KEY=' + key + '\\n')
    p.chmod(0o600)
''')


ENABLE_PROFILE_PLUGIN = '''
from pathlib import Path
from ruamel.yaml import YAML
yaml, path = YAML(), Path('/opt/data/profiles/%s/config.yaml')
data = yaml.load(path.read_text())
enabled = data.setdefault('plugins', {}).setdefault('enabled', [])
if 'rg-knowledge' not in enabled:
    enabled.append('rg-knowledge')
    with path.open('w') as f:
        yaml.dump(data, f)
''' % PROFILE


def enable_knowledge_tab():
    """The dashboard serves user plugins only when enabled: in the profile (tab list) and at its launch scope (API)."""
    in_container('python', '-c', ENABLE_PROFILE_PLUGIN)
    in_container('hermes', '-p', 'default', 'plugins', 'enable', 'rg-knowledge', capture_output=True)


def main():
    cfg = json.loads((ROOT / 'config.json').read_text())
    install_runtime()
    restore_state(cfg)
    write_desk_profile(cfg)
    network()
    model_key = ''
    if cfg.get('model_secret'):
        model_key = run('aws', 'secretsmanager', 'get-secret-value', '--secret-id', cfg['model_secret'], '--region',
                        cfg['region'], '--query', 'SecretString', '--output', 'text', capture_output=True).stdout.strip()
    hermes_env(cfg, model_key)
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    shutil.copytree(SOURCE / 'profiles/remedigenius', PACKAGE)
    config = PACKAGE / 'config.yaml'
    config.write_text(seed_model(config.read_text(), (cfg['model_name'], cfg['model_base_url']) if model_key else None))
    for name, body in units(cfg).items():
        Path('/etc/systemd/system', name).write_text(body)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', 'remedigenius-desk.service', 'remedigenius-scan.timer', 'remedigenius-hermes.service')
    run('systemctl', 'restart', 'remedigenius-desk.service')
    for _ in range(60):
        if SOCKET.exists():
            break
        time.sleep(1)
    else:
        raise RuntimeError('remedigenius-desk did not start; check journalctl -u remedigenius-desk')
    run('systemctl', 'start', 'remedigenius-scan.timer')
    run('systemctl', 'restart', 'remedigenius-hermes.service')
    for _ in range(120):
        if in_container('test', '-f', '/opt/data/config.yaml', check=False, capture_output=True).returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Hermes container did not initialize; check journalctl -u remedigenius-hermes')
    if not (HERMES_HOME / 'profiles' / PROFILE).exists():
        subprocess.run(['docker', 'exec', CONTAINER, 'hermes', 'profile', 'install', '/opt/remedigenius-package',
                        '--name', PROFILE, '--yes'], check=True)
    sync_profile(SOURCE, HERMES_HOME)
    seed_model_key()
    if cfg.get('webui', True):
        set_api_key()
    enable_knowledge_tab()
    in_container('hermes', 'profile', 'use', PROFILE)
    run('docker', 'restart', CONTAINER)
    if cfg.get('webui', True):
        run('systemctl', 'enable', '--now', 'remedigenius-webui.service')
    else:
        subprocess.run(['systemctl', 'disable', '--now', 'remedigenius-webui.service'], capture_output=True)
    if cfg.get('watch_deliver'):
        for _ in range(30):
            jobs = in_container('hermes', '-p', PROFILE, 'cron', 'list', check=False, capture_output=True)
            if jobs.returncode == 0:
                break
            time.sleep(2)
        if 'security-watch' not in jobs.stdout:
            in_container('hermes', '-p', PROFILE, 'cron', 'create', f"every {int(cfg.get('scan_interval_hours', 6))}h",
                         '--name', 'security-watch', '--no-agent', '--script', 'rgtriage-watch.py',
                         '--deliver', cfg['watch_deliver'])
    print('RemediGenius-CE ready. Dashboard: tools/open-remedigenius (SSM tunnel); WebUI: add --webui; '
          'login in /data/hermes/remedigenius-login.json.')


if __name__ == '__main__':
    main()
