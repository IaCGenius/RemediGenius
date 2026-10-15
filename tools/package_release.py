"""Inspect a release source archive for private data and unsafe paths.
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
