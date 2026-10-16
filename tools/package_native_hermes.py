"""Package reviewed native CE source; print the digest for Terraform inputs.

Usage: python tools/package_native_hermes.py --output .rgce/native-source.zip
Does not upload, read credentials, or modify deployment configuration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def package(output):
    root = Path(__file__).resolve().parents[1]
    desk = root / 'profiles/ce/desk'
    reviewed = [desk/'SOUL.md']
    for directory in ('plugins/ce-runtime', 'skills'):
        reviewed.extend(p for p in (desk/directory).rglob('*') if p.is_file()
                        and p.suffix in ('.py','.md','.json','.yaml') and p.name!='manifest.json')
    manifest = {'version':'ce-runtime/0.1.3','files':{
        p.relative_to(desk).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(reviewed)}}
    selected = [root / 'tools/native_data.py', root / 'tools/upgrade_native_profile.py',
                root / 'tools/native_session_limits.py', root / 'tools/native_validator.py', root / 'tools/model_probe.py']
    extensions = {'.py', '.tf', '.md', '.yaml', '.yml', '.tftpl', '.sh', '.json'}
    for directory in ('deploy/aws-native', 'deploy/validator', 'profiles/ce'):
        for path in (root / directory).rglob('*'):
            parts = path.relative_to(root).parts
            if (path.is_file() and not any(p.startswith('.') or p == '__pycache__' for p in parts)
                    and '.tfstate' not in path.name and '.tfvars' not in path.name
                    and (path.suffix in extensions or path.name in ('LICENSE','Dockerfile'))):
                selected.append(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(selected):
            # Stable metadata makes identical reviewed source produce the same digest.
            entry = zipfile.ZipInfo(path.relative_to(root).as_posix(), (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
        entry = zipfile.ZipInfo('profiles/ce/desk/plugins/ce-runtime/manifest.json', (2020,1,1,0,0,0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(entry, json.dumps(manifest,sort_keys=True))
    return {'archive': str(output), 'files': len(selected)+1,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(package(parser.parse_args().output)))
