"""Assemble the private preview from committed source and accepted local artifacts.
No network calls, credential discovery, cloud deployment or publication.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def inspect_source(path, private_patterns=()):
    """Inspect every member, including the tests that implement privacy checks."""
    patterns = [r'AKIA[A-Z0-9]{16}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                r'ghp_[A-Za-z0-9]{36}', *private_patterns]
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate source member')
        for name in names:
            part = PurePosixPath(name)
            if part.is_absolute() or '..' in part.parts or '\\' in name:
                raise ValueError('Unsafe source archive path')
            if {'.git', '.rgce', '.aws', '.venv', '.terraform', 'dist', '__pycache__'} & set(part.parts):
                raise ValueError('Private/runtime directory in source archive')
            if part.name in ('auth.json', 'credentials', '.env') or part.name.endswith(('.tfstate', '.tfplan', '.tfvars.json')) or (part.name.endswith('.tfvars') and part.name != 'example.tfvars'):
                raise ValueError('Private state/configuration in source archive')
            if name.endswith('/'):
                continue
            data = archive.read(name).decode('utf-8', errors='ignore')
            if any(re.search(pattern, data) for pattern in patterns):
                raise ValueError('Private identifier or credential shape in source member: ' + name)
        return len([name for name in names if not name.endswith('/')])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default='dist/private-preview')
    args = parser.parse_args()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise SystemExit('Commit the reviewed source and acceptance report before packaging')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    init = (ROOT / 'rgce/__init__.py').read_text(encoding='utf-8')
    version = re.search(r'__version__ = "([0-9A-Za-z.]+)"', init).group(1)
    accepted = json.loads((ROOT / 'docs/acceptance' / ('rc' + version.split('rc')[-1] + '-results.json')).read_text())
    dist = ROOT / 'dist'
    wheel = dist / ('remedigenius_community-' + version + '-py3-none-any.whl')
    runtime = dist / ('remedigenius-community-' + version + '-runtime.tar.gz')
    if sha(wheel) != accepted['windows_wheel']['wheel_sha256'] or sha(runtime) != accepted['image_archive_sha256']:
        raise SystemExit('Artifacts differ from the accepted wheel/runtime')
    folder = Path(args.output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    bundle = folder / ('remedigenius-ce-private-preview-' + version)
    bundle.mkdir(exist_ok=False)  # Never blend candidates or silently overwrite a previous bundle.
    source = bundle / 'source.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--output=' + str(source), commit], cwd=ROOT, check=True)
    private = ROOT / '.rgce/private-patterns.json'
    patterns = json.loads(private.read_text()) if private.exists() else []
    source_count = inspect_source(source, patterns)
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(wheel) as whl:
        files = [n for n in whl.namelist() if n.startswith('rgce/') and not n.endswith('/')]
        for name in files:
            if src.read(name).replace(b'\r\n', b'\n') != whl.read(name).replace(b'\r\n', b'\n'):
                raise ValueError('Wheel differs from committed source: ' + name)
    shutil.copyfile(wheel, bundle / wheel.name)
    shutil.copyfile(runtime, bundle / 'runtime.tar.gz')
    dependencies = dist / ('requirements-tested-docker-rc' + version.split('rc')[-1] + '.txt')
    shutil.copyfile(dependencies, bundle / 'DEPENDENCIES.txt')
    for name, target in [('docs/FEEDBACK.md', 'FEEDBACK.md'), ('docs/V0.1-QUICKSTART.md', 'FIRST-INVESTIGATION.md'),
                         ('SECURITY.md', 'SECURITY.md'), ('LICENSE', 'LICENSE'), ('NOTICE', 'NOTICE'),
                         ('integrations/skills/remedigenius-investigate/SKILL.md', 'INVESTIGATION-SKILL.md')]:
        shutil.copyfile(ROOT / name, bundle / target)
    first = bundle / 'FIRST-INVESTIGATION.md'
    first.write_text(re.sub(r'\]\(([^:#)]+\.md)\)', r'](source/docs/\1)', first.read_text(encoding='utf-8')), encoding='utf-8')
    security = bundle / 'SECURITY.md'
    security.write_text(security.read_text(encoding='utf-8').replace('](docs/', '](source/docs/'), encoding='utf-8')
    compose = (ROOT / 'compose.yaml').read_text(encoding='utf-8')
    compose = compose.replace('    build:\n      context: .\n      dockerfile: Dockerfile\n', '')
    compose = compose.replace('name: remedigenius-ce', 'name: remedigenius-ce-preview')
    compose = compose.replace('    restart: unless-stopped', '    pull_policy: never\n    platform: linux/amd64\n    restart: unless-stopped')
    (bundle / 'compose.yaml').write_text(compose, encoding='utf-8')
    start = (ROOT / 'docs/PREVIEW-START-HERE.md').read_text(encoding='utf-8').replace('__VERSION__', version)
    (bundle / 'START-HERE.md').write_text(start, encoding='utf-8')
    release = {'version':version, 'channel':'private-preview', 'source_commit':commit,
        'image_tag':'remedigenius-ce:' + version, 'image_id':accepted['docker_image'],
        'platform':'linux/amd64', 'source_members_checked':source_count, 'package_files_matched':len(files),
        'acceptance':accepted, 'files':{p.name:sha(p) for p in sorted(bundle.iterdir()) if p.is_file()}}
    (bundle / 'RELEASE.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
    files = sorted(p for p in bundle.iterdir() if p.is_file())
    (bundle / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + p.name + '\n' for p in files), encoding='utf-8')
    output = folder / (bundle.name + '.zip')
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_STORED) as archive:
        for path in sorted(bundle.iterdir()):
            archive.write(path, bundle.name + '/' + path.name)
    output.with_suffix('.zip.sha256').write_text(sha(output) + '  ' + output.name + '\n', encoding='utf-8')
    print(json.dumps({'bundle':str(output), 'sha256':sha(output), 'source_commit':commit, 'source_members_checked':source_count}))


if __name__ == '__main__':
    main()
