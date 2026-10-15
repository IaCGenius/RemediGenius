"""Bound native dashboard terminals using an exact pinned-source overlay.

No custom session lifecycle: Hermes still evicts detached terminals and rejects
excess attached terminals. Saved conversations remain in the retained data volume.
Revalidate this overlay explicitly whenever the official image changes.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess

SOURCE = '/opt/hermes/hermes_cli/web_server_chat.py'
SOURCE_SHA256 = 'fe0bdf3b29f67898468aab9ada771fed98d2cb5f10dbb82caae6b1aeb8db436f'
OLD = b'ttl=30 * 60, max_sessions=16, buffer_cap=1 * 1024 * 1024'
NEW = b'ttl=10 * 60, max_sessions=2, buffer_cap=1 * 1024 * 1024'


def overlay(body):
    if hashlib.sha256(body).hexdigest() != SOURCE_SHA256 or body.count(OLD) != 1:
        raise ValueError('Unreviewed Hermes dashboard source; revalidate session overlay before upgrading')
    return body.replace(OLD, NEW, 1)


def prepare(image, output):
    if '@sha256:' not in image:
        raise ValueError('Use the reviewed digest-pinned official image')
    result = subprocess.run(['docker','run','--rm','--network','none','--entrypoint',
                             'cat',image,SOURCE], check=True, capture_output=True, timeout=120)
    body = overlay(result.stdout)
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)
    return output


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    prepare(args.image,args.output)
    print('Verified native session overlay: two terminals, ten-minute detached TTL')
