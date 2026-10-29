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
CONFIG = Path('/data/rgconfig')          # triage.yaml only; facts and cache are rebuilt from S3/Iceberg
VUID = 10002                              # validation service user: runs Terraform, tflint and cfn-lint; no access to the GitHub key
VALIDATE_HOME = Path('/var/lib/rgvalidate')
VALIDATE_SOCKET = Path('/run/rgvalidate/validate.sock')
OPERATOR_TOKEN = Path('/data/rggithub/operator.token')   # the desk's copy of the web console's setup secret (desk-only)
OPERATOR_TOKEN_IN_CONTAINER = '/opt/data/.rg-operator-token'  # the dashboard backend reads this one; the agent's tools have no way to call the setup routes
GITHUB = Path('/data/rggithub')           # GitHub App key and policy: desk-only, never mounted into the agent container
IAC = Path('/data/iac')
RUNDIR = Path('/run/rgtriage')
SOCKET = RUNDIR / 'rgtriage.sock'
VENV = Path('/opt/rgtriage/venv')
CODE = Path('/opt/rgtriage/src')          # readable copy of the rgtriage package for uid 10000
PACKAGE = Path('/opt/remedigenius/package')
LOGIN = HERMES_HOME / 'remedigenius-login.json'
CONTAINER = 'remedigenius'
SUBNET = '172.29.242.0/24'
PROFILE = 'remedigenius'
PACKAGES = ['boto3==1.42.89', 'PyYAML==6.0.3', 'cfn-lint==1.57.2',  # cfn-lint: deterministic CloudFormation checks before a PR
            'pyiceberg[sql-sqlite,pyarrow]==0.12.0', 'pyarrow==19.0.1', 'sqlalchemy==2.0.41']
TERRAFORM = ('1.12.2', '1eaed12ca41fcfe094da3d76a7e9aa0639ad3409c43be0103ee9f5a1ff4b7437')
TFLINT = ('0.63.1', '8441a7d97df20431f19c9b9d27ff4c63e308c964e86660bc7cc0cf7bbe0725e8')
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
    # A different user for the code we do not trust (validation): it cannot read what the desk user can (GitHub key and policy).
    if subprocess.run(['getent', 'group', str(VUID)], capture_output=True).returncode:
        run('groupadd', '--system', '--gid', str(VUID), 'rgvalidate')
    if subprocess.run(['getent', 'passwd', str(VUID)], capture_output=True).returncode:
        run('useradd', '--system', '--uid', str(VUID), '--gid', str(VUID), '--no-create-home', '--shell', '/sbin/nologin', 'rgvalidate')


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
    install_wrapper()
    install_zip_binary('terraform', *TERRAFORM, 'https://releases.hashicorp.com/terraform/{v}/terraform_{v}_linux_amd64.zip')
    install_zip_binary('tflint', *TFLINT, 'https://github.com/terraform-linters/tflint/releases/download/v{v}/tflint_linux_amd64.zip')


def wrapper_script() -> str:
    """`sudo rgdesk <rgtriage args>`: run the desk CLI as the desk user with the desk environment (operator use over SSM)."""
    return ("#!/bin/sh\n"
            f"exec sudo -u '#{UID}' env PYTHONPATH={CODE.as_posix()} RGTRIAGE_HOME={DESK.as_posix()} RGTRIAGE_CONFIG={(CONFIG / 'triage.yaml').as_posix()} RGGITHUB_HOME={GITHUB.as_posix()} "
            f"RGGITHUB_IAC_DIR={IAC.as_posix()} RGVALIDATE_SOCKET={VALIDATE_SOCKET.as_posix()} RGTRIAGE_PROPOSALS=/opt/data/proposals "
            f"HOME={DESK.as_posix()}/.home "
            f"{(VENV / 'bin/python').as_posix()} -m rgtriage \"$@\"\n")


def install_wrapper():
    path = Path('/usr/local/bin/rgdesk')
    path.write_text(wrapper_script())
    path.chmod(0o755)


def install_zip_binary(name, version, digest, url):
    """A pinned, checksummed single-binary release zip into /usr/local/bin (skipped when that version is already there)."""
    binary = Path('/usr/local/bin') / name
    if binary.exists() and version in subprocess.run([str(binary), 'version' if name == 'terraform' else '--version'],
                                                    capture_output=True, text=True).stdout:
        return
    data = urllib.request.urlopen(url.format(v=version), timeout=120).read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f'{name} download checksum mismatch')
    archive = Path(f'/tmp/{name}.zip')
    archive.write_bytes(data)
    with zipfile.ZipFile(archive) as z:
        binary.write_bytes(z.read(name))
    binary.chmod(0o755)
    archive.unlink()


def desk(*args, user=None, **kw):
    """Run the rgtriage CLI with the host venv (as root unless a user is given)."""
    env = dict(os.environ, PYTHONPATH=str(CODE), RGTRIAGE_HOME=str(DESK), HOME=str(DESK / '.home'),
               RGTRIAGE_CONFIG=str(CONFIG / 'triage.yaml'), RGGITHUB_HOME=str(GITHUB), AWS_STS_REGIONAL_ENDPOINTS='regional')
    prefix = ['setpriv', f'--reuid={UID}', f'--regid={UID}', '--clear-groups'] if user else []
    return run(*prefix, str(VENV / 'bin/python'), '-m', 'rgtriage', *args, env=env, **kw)


def restore_state(cfg):
    """Durable copy first: an empty disk (new Spot instance) is filled from the latest S3 checkpoints."""
    for path in (HERMES_HOME, DESK, CONFIG, GITHUB):
        path.mkdir(parents=True, exist_ok=True)
    result = desk('durable', 'restore', '--url', durable_url(cfg), '--home', f'hermes={HERMES_HOME}',
                  '--home', f'config={CONFIG}', '--home', f'github={GITHUB}', '--owner', f'{UID}:{UID}', capture_output=True)
    print(result.stdout.strip())
    for path in (HERMES_HOME, DESK, CONFIG, GITHUB, HERMES_HOME / 'proposals', DESK / '.home', DESK / '.lineage', IAC, HERMES_HOME / 'work'):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, UID, UID)
    GITHUB.chmod(0o700)  # only the desk user; the folder is not mounted into the Hermes container
    for path in (VALIDATE_HOME, VALIDATE_HOME / 'scratch', VALIDATE_HOME / '.home'):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, VUID, VUID)
    VALIDATE_HOME.chmod(0o700)
    for path in (DESK / '.lineage').iterdir():
        os.chown(path, UID, UID)
    # Same path on the host as in the container, so the desk can validate files the agent proposes.
    link = Path('/opt/data')
    if not link.is_symlink():
        link.symlink_to(HERMES_HOME)


def write_operator_token():
    """A fresh secret every boot for the web console's GitHub setup. The desk accepts the connect, configure and disconnect operations over
    its socket only from a caller that presents it; the agent's own tool never does, and nothing the agent can call reaches the dashboard's
    routes. Both copies are 0600 and owned by the desk and container user."""
    token = secrets.token_urlsafe(32)
    for path in (OPERATOR_TOKEN, HERMES_HOME / '.rg-operator-token'):
        path.write_text(token)
        path.chmod(0o600)
        os.chown(path, UID, UID)


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
    profile = CONFIG / 'triage.yaml'
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
               'organization': {'discover': True, 'member_role_name': cfg.get('member_role_name') or 'RemediGeniusReadOnly'},
               'storage': {'profile': 'aws', 'namespace': cfg['name'], 'warehouse_uri': cfg['warehouse'],
                           'catalog_database': cfg['glue_database'], 'raw_prefix': 'raw', 'buffer_limit_mb': 256,
                           'maintenance': {'snapshot_retention_days': 14, 'min_snapshots': 5,
                                           'target_file_size_mb': 128, 'interval_hours': 24,
                                           'orphan_retention_hours': 72}}}
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
    # Untrusted validation tools may use the internet (provider downloads) but never the instance metadata service (the instance
    # role's credentials), the agent's container network or other private addresses.
    for destination in ('169.254.0.0/16', SUBNET, '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'):
        args = ['-m', 'owner', '--uid-owner', str(VUID), '-d', destination, '-j', 'REJECT']
        if subprocess.run(['iptables', '-C', 'OUTPUT', *args], stderr=subprocess.DEVNULL).returncode:
            run('iptables', '-I', 'OUTPUT', '1', *args)
    for line in Path('/etc/resolv.conf').read_text().splitlines():  # name resolution is still allowed (inserted before the blocks)
        fields = line.split()
        if len(fields) >= 2 and fields[0] == 'nameserver' and ':' not in fields[1]:
            for protocol in ('udp', 'tcp'):
                args = ['-m', 'owner', '--uid-owner', str(VUID), '-d', fields[1], '-p', protocol, '--dport', '53', '-j', 'ACCEPT']
                if subprocess.run(['iptables', '-C', 'OUTPUT', *args], stderr=subprocess.DEVNULL).returncode:
                    run('iptables', '-I', 'OUTPUT', '1', *args)


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


WATCH_SCRIPT = '''"""Hermes cron script: print only new P1/P2 security findings (empty output = silent).

Reaches the desk over its Unix socket. The desk can be restarting (about 3 seconds) or just starting, so a failed connection is retried for
WAIT seconds before giving up with a one-line reason. It only works inside the agent container, which is where the socket folder is mounted."""
import json, os, socket, sys, time

PATH = %r
WAIT = 90


def connect():
    last, deadline = None, time.time() + WAIT
    while True:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.settimeout(30)
            s.connect(PATH)
            return s
        except OSError as exc:
            last = exc
            s.close()
            if time.time() >= deadline:
                break
            time.sleep(3)
    where = ("the desk's socket folder is not mounted in this process: this job must run inside the agent container"
             if not os.path.isdir(os.path.dirname(PATH)) else "the desk service is not answering")
    print(f"security watch could not reach the desk ({type(last).__name__}): {where}. It will try again at the next run.")
    sys.exit(1)


s = connect()
s.settimeout(1200)
s.sendall(json.dumps({"args": ["watch", "--min-priority", "P2"]}).encode() + b"\\n")
data = b""
while True:
    chunk = s.recv(65536)
    if not chunk:
        break
    data += chunk
try:
    reply = json.loads(data)
except ValueError:
    print("security watch got an unreadable answer from the desk. It will try again at the next run.")
    sys.exit(1)
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
    # `hermes profile install` also copied the dashboard plugin into the profile; keep that copy on this release too.
    copy = profile / 'dashboard-plugins'
    if copy.exists():
        shutil.rmtree(copy)
        shutil.copytree(package / 'dashboard-plugins', copy, ignore=shutil.ignore_patterns('__pycache__', 'local.json'))
    shutil.copytree(package / 'dashboard-plugins/rg-knowledge', tab, ignore=shutil.ignore_patterns('__pycache__', 'local.json'))
    (tab / 'local.json').write_text(json.dumps({'socket': SOCKET.as_posix(), 'home': DESK.as_posix(), 'proposals': PROPOSALS,
                                                'inbox': '/opt/data/knowledge-inbox', 'files': '/opt/data/knowledge-files',
                                                'profile': PROFILE, 'improve': '/opt/data/rg-improve',
                                                'package': '/opt/remedigenius-package'}))
    # GitHub tab (dashboard plugin): setup steps go to the desk through its socket with the operator token (read from the file below).
    github_tab = hermes_home / 'plugins' / 'rg-github'
    if github_tab.exists():
        shutil.rmtree(github_tab)
    shutil.copytree(package / 'dashboard-plugins/rg-github', github_tab, ignore=shutil.ignore_patterns('__pycache__', 'local.json'))
    (github_tab / 'local.json').write_text(json.dumps({'socket': SOCKET.as_posix(), 'operator_token_file': OPERATOR_TOKEN_IN_CONTAINER}))
    folders = [hermes_home / 'proposals' / 'knowledge', hermes_home / 'knowledge-inbox', hermes_home / 'knowledge-files',
               hermes_home / 'rg-improve', hermes_home / 'rg-traces']
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    # Skill improvements a person approved survive instance replacement when made for this shipped version.
    sys.path.insert(0, str(tab))
    from improve.runner import apply_approved
    print(f"approved skill improvements: {json.dumps(apply_approved(hermes_home / 'rg-improve', package / 'skills', profile / 'skills'))}")
    for path in [profile, *profile.rglob('*'), hermes_home / 'plugins', tab, *tab.rglob('*'), github_tab, *github_tab.rglob('*'), *folders]:
        if hasattr(os, 'lchown'):
            os.lchown(path, UID, UID)
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else (0o600 if path.name == '.env' else 0o644))


def units(cfg: dict) -> dict:
    env = (f'Environment=RGTRIAGE_HOME={DESK.as_posix()}\nEnvironment=RGTRIAGE_CONFIG={(CONFIG / "triage.yaml").as_posix()}\nEnvironment=PYTHONPATH={CODE.as_posix()}\n'
           f'Environment=HOME={DESK.as_posix()}/.home\nEnvironment=AWS_DEFAULT_REGION={cfg["region"]}\n'
           f'Environment=AWS_STS_REGIONAL_ENDPOINTS=regional\nEnvironment=TF_PLUGIN_CACHE_DIR={DESK.as_posix()}/.home/plugins\n'
           f'Environment=REMEDIGENIUS_MODEL_NAME={cfg.get("model_name") or ""}\n'
           f'Environment=REMEDIGENIUS_MODEL_BASE_URL={cfg.get("model_base_url") or ""}\n'
           f'Environment=RGGITHUB_HOME={GITHUB.as_posix()}\n'
           f'Environment=RGGITHUB_IAC_DIR={IAC.as_posix()}\n'
           f'Environment=RGVALIDATE_SOCKET={VALIDATE_SOCKET.as_posix()}\n'
           f'Environment=RGTRIAGE_OPERATOR_TOKEN_FILE={OPERATOR_TOKEN.as_posix()}\n')
    harden = (f'User={UID}\nGroup={UID}\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\n'
              f'ReadWritePaths={DESK.as_posix()} {CONFIG.as_posix()} {GITHUB.as_posix()} {IAC.as_posix()}\n')
    python = (VENV / 'bin/python').as_posix()
    homes = (f'--home hermes={HERMES_HOME.as_posix()} --home config={CONFIG.as_posix()} '
             f'--home github={GITHUB.as_posix()}')
    store = durable_url(cfg)
    memory = int(cfg.get('container_memory_mb', 6144))
    mounts = ' '.join(CONTAINER_MOUNTS)
    return {
        'remedigenius-desk.service': f'''[Unit]
Description=RemediGenius-CE desk: read-only AWS access, Unix socket API, S3 checkpoints
After=network-online.target remedigenius-validate.service
Wants=remedigenius-validate.service
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
        'remedigenius-validate.service': f'''[Unit]
Description=RemediGenius-CE validation service: Terraform, tflint and cfn-lint away from every credential
After=network-online.target
[Service]
User={VUID}
Group={VUID}
SupplementaryGroups={UID}
Environment=PYTHONPATH={CODE.as_posix()}
Environment=HOME={VALIDATE_HOME.as_posix()}/.home
Environment=TF_PLUGIN_CACHE_DIR={VALIDATE_HOME.as_posix()}/.home/plugins
Environment=PATH=/usr/local/bin:/usr/bin
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
ReadWritePaths={VALIDATE_HOME.as_posix()}
RuntimeDirectory=rgvalidate
RuntimeDirectoryMode=0755
RuntimeDirectoryPreserve=yes
MemoryMax=3G
TasksMax=512
ExecStart={(VENV / 'bin/python').as_posix()} -m rgtriage serve-validate --socket {VALIDATE_SOCKET.as_posix()} --scratch {VALIDATE_HOME.as_posix()}/scratch --workers 2 --group {UID}
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
ExecStartPre=/bin/sh -c 'n=0; while [ ! -S {SOCKET.as_posix()} ] && [ $$n -lt 60 ]; do n=$$((n+1)); sleep 1; done; exit 0'
ExecStartPre=-/usr/bin/docker rm -f {CONTAINER}
ExecStart=/usr/bin/docker run --rm --name {CONTAINER} --network {CONTAINER} --env-file /run/remedigenius/hermes.env -p 127.0.0.1:9120:9120 -v {HERMES_HOME.as_posix()}:/opt/data {mounts} -v {PACKAGE.as_posix()}:/opt/remedigenius-package:ro --memory {memory}m --pids-limit 1024 {cfg['image']} gateway run
ExecStop=/usr/bin/docker stop -t 30 {CONTAINER}
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
    values = {'HERMES_DASHBOARD': '1', 'HERMES_DASHBOARD_PORT': '9120',
              'HERMES_DASHBOARD_BASIC_AUTH_USERNAME': login['username'],
              'HERMES_DASHBOARD_BASIC_AUTH_PASSWORD': login['password'],
              'HERMES_DASHBOARD_BASIC_AUTH_SECRET': login['secret'],
              'AWS_EC2_METADATA_DISABLED': 'true', 'HERMES_TUI_TOOLSETS': 'skills,clarify,file,rg_triage'}
    if model_key:
        values['MODEL_API_KEY'] = model_key
    if any('\n' in v or '\r' in v for v in values.values()):
        raise ValueError('Invalid credential shape')
    runtime = Path('/run/remedigenius')
    runtime.mkdir(exist_ok=True, mode=0o700)
    path = runtime / 'hermes.env'
    path.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
    path.chmod(0o600)


def retire_webui():
    """v0.4.0 removed the community WebUI and the agent's API server it needed. If this host ever ran them (state and a systemd unit can survive
    from an older release), stop and delete the unit, the container and its volume, the API key and the generated wiki view. The WebUI's own
    folder (/data/hermes/webui) is left alone: it is the person's data, and can be deleted by hand."""
    subprocess.run(['systemctl', 'disable', '--now', 'remedigenius-webui.service'], capture_output=True)
    Path('/etc/systemd/system/remedigenius-webui.service').unlink(missing_ok=True)
    subprocess.run(['docker', 'rm', '-f', 'remedigenius-webui'], capture_output=True)
    subprocess.run(['docker', 'volume', 'rm', '-f', 'remedigenius-webui-src'], capture_output=True)
    (HERMES_HOME / '.remedigenius-api-key').unlink(missing_ok=True)
    shutil.rmtree(HERMES_HOME / 'rg-wiki', ignore_errors=True)
    Path('/run/remedigenius/webui.env').unlink(missing_ok=True)
    for env in (HERMES_HOME / '.env', HERMES_HOME / 'profiles' / PROFILE / '.env'):  # the API server key the WebUI used
        if env.exists():
            lines = env.read_text().splitlines()
            kept = [line for line in lines if not line.startswith('API_SERVER_KEY=')]
            if kept != lines:
                env.write_text('\n'.join(kept) + ('\n' if kept else ''))
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
changed = False
for name in ('rg-knowledge', 'rg-github'):
    if name not in enabled:
        enabled.append(name)
        changed = True
if changed:
    with path.open('w') as f:
        yaml.dump(data, f)
''' % PROFILE


def enable_knowledge_tab():
    """The dashboard serves user plugins only when enabled: in the profile (tab list) and at its launch scope (API)."""
    in_container('python', '-c', ENABLE_PROFILE_PLUGIN)
    for name in ('rg-knowledge', 'rg-github'):
        in_container('hermes', '-p', 'default', 'plugins', 'enable', name, capture_output=True)


KANBAN_OFF = ('kanban.dispatch_in_gateway', 'kanban.auto_decompose')


def kanban_off() -> bool:
    """True when the root config says the Kanban dispatcher and task splitting are off (read back, never assumed)."""
    for key in KANBAN_OFF:
        got = in_container('hermes', '-p', 'default', 'config', 'get', key, check=False, capture_output=True)
        if got.returncode or got.stdout.strip().splitlines()[-1:] != ['false']:
            return False
    return True


def ensure_kanban_off():
    """The gateway runs the Kanban dispatcher from the root config: cards are for people, never for worker agents.

    Hermes can rewrite its root config while it initializes, so the setting is applied after the last restart, read back, and the
    gateway restarted only if it had to change. A setting that does not stick fails the boot instead of shipping a dispatcher."""
    for _ in range(2):
        if kanban_off():
            return
        for key in KANBAN_OFF:
            in_container('hermes', '-p', 'default', 'config', 'set', key, 'false', capture_output=True)
        run('docker', 'restart', CONTAINER)
        for _ in range(60):
            if in_container('hermes', '-p', 'default', 'config', 'get', KANBAN_OFF[0], check=False, capture_output=True).returncode == 0:
                break
            time.sleep(2)
    if not kanban_off():
        raise RuntimeError('could not turn the Kanban dispatcher off in the Hermes root config; refusing to finish the boot')


def main():
    cfg = json.loads((ROOT / 'config.json').read_text())
    install_runtime()
    restore_state(cfg)
    retire_webui()
    write_operator_token()
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
    run('systemctl', 'enable', 'remedigenius-validate.service', 'remedigenius-desk.service', 'remedigenius-scan.timer', 'remedigenius-hermes.service')
    run('systemctl', 'restart', 'remedigenius-validate.service')
    for _ in range(60):
        if VALIDATE_SOCKET.exists():
            break
        time.sleep(1)
    else:
        raise RuntimeError('remedigenius-validate did not start; check journalctl -u remedigenius-validate')
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
    enable_knowledge_tab()
    in_container('hermes', 'profile', 'use', PROFILE)
    run('docker', 'restart', CONTAINER)
    ensure_kanban_off()
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
    print('RemediGenius-CE ready. Dashboard: tools/open-remedigenius (SSM tunnel); '
          'login in /data/hermes/remedigenius-login.json.')


if __name__ == '__main__':
    main()
