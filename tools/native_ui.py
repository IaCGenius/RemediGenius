"""Optional Hermes browser UI. No model keys or AWS credentials enter the UI container."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'hermes-ui'


def run(*args, capture=False, **kwargs):
    return subprocess.run(args, check=True, text=True, encoding='utf-8',
                          stdout=subprocess.PIPE if capture else None, **kwargs).stdout


def inspect(kind, name):
    r = subprocess.run(['docker', kind, 'inspect', name], capture_output=True, text=True)
    if r.returncode:
        if 'No such' in r.stderr or 'not found' in r.stderr: return None
        raise RuntimeError(r.stderr)
    return json.loads(r.stdout)[0]


def stop(name):
    container = name + '-ui'
    existing = inspect('container', container)
    if existing:
        if existing['Config'].get('Labels', {}).get('com.remedigenius.ce') != LABEL:
            raise ValueError('Refusing to remove an unrelated UI container')
        run('docker', 'rm', '-f', container)


def seed_model(name):
    # Native routed profiles intentionally do not inherit process secrets.
    # Seed only the launcher's existing MODEL_API_KEY; preserve operator overrides.
    run('docker', 'exec', '-i', '--user', '10000:10000', name, 'python', '-', input='''
import os
from pathlib import Path
p=Path('/opt/data/profiles/ce-desk/.env')
if not p.parent.is_dir(): raise SystemExit('Install ce-desk first')
s=p.read_text() if p.exists() else ''
if not any(line.startswith('MODEL_API_KEY=') for line in s.splitlines()):
 key=os.environ.get('MODEL_API_KEY','')
 if not key: raise SystemExit(0)  # Operator may configure a provider in Hermes after login.
 if any(c in key for c in '\\r\\n'): raise SystemExit('Invalid model key')
 pending=p.with_name('.env.ui-pending')
 fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f: f.write(s.rstrip()+'\\nMODEL_API_KEY='+key+'\\n')
 pending.replace(p)
 p.chmod(0o600)
''')


def start(name, port=9126):
    if not re.fullmatch(r'rgce-[a-z0-9-]{1,40}', name) or not 1024 <= port <= 65535:
        raise ValueError('Use a CE rgce- container name and a nonprivileged port')
    gateway = inspect('container', name)
    if not gateway or not gateway['State']['Running']:
        raise ValueError('Start the Hermes gateway first')
    source = ROOT / 'deploy/hermes-ui'
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(source.iterdir()) if p.is_file())).hexdigest()[:16]
    image = 'remedigenius-hermes-ui:' + digest
    if not inspect('image', image):
        run('docker', 'build', '-t', image, str(source))
    network = name + '-ui'
    net = inspect('network', network)
    if net is None:
        run('docker', 'network', 'create', '--internal', '--label', 'com.remedigenius.ce=hermes-ui', network)
    elif not net.get('Internal') or net.get('Labels', {}).get('com.remedigenius.ce') != LABEL:
        raise ValueError('UI network must be a CE-owned internal network')
    if network not in gateway['NetworkSettings']['Networks']:
        run('docker', 'network', 'connect', '--alias', 'ce-hermes-gateway', network, name)
    seed_model(name)
    stop(name)
    # Docker 25 on AL2023 does not publish ports on an internal-only endpoint.
    # Reuse the gateway's egress network for loopback publication; the separate
    # internal network still supplies the stable gateway alias. No AWS or model
    # credentials, volumes, or Docker socket are given to the UI.
    public_network = name if name in gateway['NetworkSettings']['Networks'] else 'bridge'
    run('docker', 'run', '-d', '--name', name+'-ui', '--label', 'com.remedigenius.ce='+LABEL,
        '--network', public_network, '--network', network, '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        '--memory', '128m', '--cpus', '0.5', '--pids-limit', '128', '--restart', 'unless-stopped',
        '--tmpfs', '/tmp:rw,nosuid,nodev,uid=101,gid=101',
        '--tmpfs', '/var/cache/nginx:rw,nosuid,nodev,uid=101,gid=101',
        '-p', f'127.0.0.1:{port}:8080', image)
    print(f'Optional UI: http://127.0.0.1:{port} (same Hermes login; select ce-desk)')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start','stop'])
    parser.add_argument('--name', default='rgce-workstation')
    parser.add_argument('--port', type=int, default=9126)
    args=parser.parse_args()
    if not re.fullmatch(r'rgce-[a-z0-9-]{1,40}',args.name): parser.error('Invalid CE name')
    if args.action == 'start': start(args.name,args.port)
    else: stop(args.name)
