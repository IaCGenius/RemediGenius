"""Fixed validator commands only. Run in the credential-free, internal-network container."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

TOOLCHAIN = json.loads(Path(__file__).with_name('toolchain.json').read_text(encoding='utf-8-sig'))
LIMITS = 'Syntax/schema checks only; no plan, apply, permissions, live state or security-impact verification.'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def validate(request):
    if set(request) - {'format', 'files', 'argv'}:
        raise ValueError('Unknown validation argument')
    kind = request.get('format')
    if kind not in ('terraform', 'cloudformation', 'aws-cli'):
        raise ValueError('Choose terraform, cloudformation or aws-cli')
    files = request.get('files', {})
    if not isinstance(files, dict) or len(files) > 12:
        raise ValueError('Supply at most 12 text files')
    for name, body in files.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', name) or not isinstance(body, str):
            raise ValueError('Use plain filenames and text content; no paths')
        if not name.endswith(('.tf', '.json', '.yaml', '.yml')) or len(body) > 64000:
            raise ValueError('Unsupported file or file too large')
    if len(json.dumps(request)) > 128000:
        raise ValueError('Validation request too large')
    checks = []
    deadline = time.monotonic() + 75
    with tempfile.TemporaryDirectory(prefix='ce-validate-') as tmp:
        root = Path(tmp)
        for name, body in files.items():
            (root/name).write_text(body, encoding='utf-8')

        def run(args):
            result = subprocess.run(args, cwd=root, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                timeout=max(1, deadline-time.monotonic()), shell=False)
            checks.append({'command': args, 'exit_code': result.returncode,
                           'output': result.stdout[:12000], 'output_truncated': len(result.stdout)>12000})
            return result.returncode == 0

        if kind == 'terraform':
            if not files or any(not n.endswith('.tf') for n in files):
                raise ValueError('Terraform input must contain only .tf files')
            ok = run(['terraform', 'fmt', '-no-color', '.'])
            # No backend, downloads, module installation, plan or apply. Only the
            # trusted AWS provider already installed in this image is available.
            if ok:
                ok = run(['terraform', 'init', '-backend=false', '-input=false', '-get=false', '-no-color', '-plugin-dir=/providers'])
            if ok:
                ok = run(['terraform', 'validate', '-json'])
        elif kind == 'cloudformation':
            if len(files) != 1 or not next(iter(files)).endswith(('.yaml', '.yml', '.json')):
                raise ValueError('Supply one CloudFormation JSON/YAML template')
            ok = run(['cfn-lint', '--format', 'json', '--template', next(iter(files)), '--regions', 'us-east-1'])
        else:
            argv = request.get('argv')
            if not isinstance(argv, list) or not 2 <= len(argv) <= 80 or any(not isinstance(x,str) for x in argv):
                raise ValueError('Supply AWS CLI argv without the aws executable; one API command')
            if not all(re.fullmatch(r'[a-z][a-z0-9-]*', x) for x in argv[:2]) or argv[0] in ('s3', 'configure', 'login', 'sso'):
                raise ValueError('Only API-backed AWS CLI commands support this validator')
            forbidden = ('--generate-cli-skeleton','--endpoint-url','--profile','--debug','--cli-auto-prompt','--cli-input-yaml')
            for token in argv:
                if any(token == x or token.startswith(x+'=') for x in forbidden):
                    raise ValueError('Unsupported CLI option for offline validation')
                if 'file://' in token or 'fileb://' in token:
                    name = token.split('file://',1)[-1]
                    if not token.startswith('file://') or name not in files:
                        raise ValueError('CLI file inputs must name a submitted file')
            # Appended by trusted code, never accepted from the model. CLI parses
            # and validates but does not send the requested API operation.
            ok = run(['aws', *argv, '--generate-cli-skeleton', 'output', '--no-cli-pager'])
        validated = {name:(root/name).read_text(encoding='utf-8') for name in files}
    return {'status':'PASS' if ok else 'FAIL', 'format':kind,
            'input_sha256':digest(request), 'validated_sha256':digest({'files':validated,'argv':request.get('argv')}),
            'files':validated, 'checks':checks, 'toolchain':TOOLCHAIN, 'limits':LIMITS}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Do not log submitted source or identifiers.

    def reply(self, value, code=200):
        body=json.dumps(value).encode()
        self.send_response(code);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

    def do_GET(self):
        self.reply({'status':'READY','toolchain':TOOLCHAIN,'limits':LIMITS} if self.path=='/health' else {'status':'NOT_FOUND'},200 if self.path=='/health' else 404)

    def do_POST(self):
        if self.path != '/validate':
            self.reply({'status':'NOT_FOUND'},404);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 128000: raise ValueError('Invalid request size')
            self.connection.settimeout(10)
            result=validate(json.loads(self.rfile.read(size)))
        except subprocess.TimeoutExpired:
            result={'status':'BLOCKED','reason':'Validator deadline reached; no validation pass','toolchain':TOOLCHAIN}
        except (ValueError, TypeError) as exc:
            result={'status':'BLOCKED','reason':str(exc)[:300],'toolchain':TOOLCHAIN}
        except Exception:
            result={'status':'BLOCKED','reason':'Validator environment failed; no validation pass','toolchain':TOOLCHAIN}
        self.reply(result)


if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 9130), Handler).serve_forever()
