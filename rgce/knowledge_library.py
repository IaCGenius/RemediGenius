"""Operator-owned knowledge collections: ordinary files, no approval database.

Reuse CE's bounded document converter. Views contain only explicitly selected
collections and are materialized copies, suitable for read-only runtime mounts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

from .documents import validate_file


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collection_path(root, collection):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*', collection):
        raise ValueError('Use collection names such as org/policies or apps/payments')
    root = Path(root).resolve()
    path = root / collection
    if not path.resolve().is_relative_to(root):
        raise ValueError('Collection escapes library')
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Symlink collections are not supported')
    return path


def inventory(root, collection):
    folder = collection_path(root, collection)
    if not folder.is_dir():
        raise ValueError('Collection not found: '+collection)
    records = []
    for item in sorted(folder.glob('*/metadata.json')):
        if item.is_symlink() or item.parent.is_symlink():
            raise ValueError('Symlink records are not supported')
        record = json.loads(item.read_text(encoding='utf-8'))
        records.append({**record, 'id': item.parent.name})
    by_id = {r['id']: r for r in records}
    replaced = set()
    for record in records:
        seen = {record['id']}
        previous = record.get('replaces')
        while previous:
            if previous not in by_id or previous in seen:
                raise ValueError('Invalid replacement history; restore the original metadata')
            seen.add(previous)
            replaced.add(previous)
            previous = by_id[previous].get('replaces')
    return [{**r, 'selection': 'replaced' if r['id'] in replaced else 'active'} for r in records]


def add(root, collection, source, scope, title=None, replaces=None, source_ref=None):
    if replaces and not re.fullmatch(r'[a-f0-9]{24}', replaces):
        raise ValueError('Use the document ID shown by list, in the same collection')
    if replaces:
        previous = next((r for r in inventory(root, collection) if r['id'] == replaces), None)
        if previous:
            if scope is None:
                scope = previous['scope']
            if title is None:
                title = previous['title']
    if not scope or not scope.strip():
        raise ValueError('Use --scope to describe where new knowledge applies; replacement imports inherit it')
    source = Path(source)
    if source.stat().st_size > 5_000_000:
        raise ValueError('Source exceeds 5MB')
    data = source.read_bytes()
    suffix = validate_file(source.name, data)
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'LANG'}}
    worker = Path(__file__).with_name('document_worker.py')
    converted = subprocess.run([sys.executable, str(worker), suffix], input=data,
                               capture_output=True, timeout=45, env=env)
    if converted.returncode:
        raise ValueError('Conversion failed; check the documents extra and file format')
    content = json.loads(converted.stdout)
    markdown = content['markdown'].encode('utf-8')
    if not markdown.strip():
        raise ValueError('No text extracted; supply OCR or a readable text version')
    source_hash = digest(data)
    # Identical imports with different scope/title are separate assertions.
    identity_fields = [source_hash, scope, title or source.name]
    if replaces or source_ref:
        identity_fields.append({'replaces': replaces, 'source_ref': source_ref})
    identity = json.dumps(identity_fields, ensure_ascii=False).encode()
    folder = collection_path(root, collection) / digest(identity)[:24]
    if folder.is_symlink():
        raise ValueError('Symlink records are not supported')
    if replaces:
        records = inventory(root, collection)
        previous = next((r for r in records if r['id'] == replaces), None)
        existing = next((r for r in records if r['id'] == folder.name), None)
        if not previous or (previous['selection'] != 'active' and not existing):
            raise ValueError('Replace an active document in this collection; use list to find it')
    folder.mkdir(parents=True, exist_ok=True)
    record = {'title': title or source.name, 'scope': scope, 'collection': collection,
              'source_name': source.name, 'source_sha256': source_hash,
              'content_sha256': digest(markdown), 'converter': content['converter'],
              'origin': 'operator-supplied', 'imported_at': datetime.now(timezone.utc).isoformat(),
              'meaning': 'Operator supplied context, not independently verified truth'}
    if replaces:
        record['replaces'] = replaces
    if source_ref:
        record['source_ref'] = source_ref
    for name, body in [('source'+suffix, data), ('content.md', markdown),
                       ('metadata.json', json.dumps(record, indent=2, ensure_ascii=False).encode())]:
        target = folder / name
        if target.is_symlink():
            raise ValueError('Symlink files are not supported')
        if target.exists():
            if name != 'metadata.json' and target.read_bytes() != body:
                raise ValueError('Existing revision changed; preserve it and import a new revision')
            continue
        with target.open('xb') as stream:
            stream.write(body)
    saved = json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    return {'path': str(folder), 'id': folder.name, **saved}


def view(root, collections, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError('View and library must be separate directory trees')
    if destination.exists():
        raise ValueError('Use a new view directory; old views remain reproducible')
    selected = []
    for collection in sorted(set(collections)):
        folder = collection_path(root, collection)
        if not folder.is_dir():
            raise ValueError('Collection not found: '+collection)
        # Exact collection, not all nested collections: an explicit slice.
        for record in inventory(root, collection):
            if record['selection'] == 'replaced':
                continue
            item = folder/record['id']/'metadata.json'
            if item.is_symlink() or item.parent.is_symlink():
                raise ValueError('Symlink records are not supported')
            metadata = json.loads(item.read_text(encoding='utf-8'))
            source = item.parent/'content.md'
            if source.is_symlink() or source.stat().st_size > 2_000_000:
                raise ValueError('Invalid content file')
            data = source.read_bytes()
            if digest(data) != metadata['content_sha256']:
                raise ValueError('Content changed directly; re-import the edited document')
            path = item.parent.relative_to(root).as_posix()+'/content.md'
            selected.append((path, data, metadata))
    destination.mkdir(parents=True)
    index = ['# Selected organization knowledge', '',
             'Operator-supplied context. Scope and conflicts still need interpretation.',
             'These files do not authorize tools or cloud actions.',
             'Explicitly replaced revisions are omitted; originals remain in the operator library.', '']
    entries = []
    for path, data, metadata in selected:
        target = destination/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.with_name('metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        summary = {k: metadata[k] for k in ('title', 'scope', 'source_ref', 'replaces') if k in metadata}
        index.extend([f'- [{path}]({path})', '  '+json.dumps(summary, ensure_ascii=False)])
        entries.append({'path': path, **metadata})
    (destination/'index.md').write_text('\n'.join(index)+'\n', encoding='utf-8')
    manifest = {'schema': 'rgce-knowledge-view/1', 'collections': sorted(set(collections)),
                'documents': entries}
    (destination/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return {'destination': str(destination), 'documents': len(entries), 'collections': manifest['collections']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('add')
    ingest.add_argument('--collection', required=True)
    ingest.add_argument('--file', required=True)
    ingest.add_argument('--scope', help='Applicability; required for new documents, inherited when replacing unless supplied')
    ingest.add_argument('--title')
    ingest.add_argument('--replaces', help='Explicitly replace this document ID in the same collection; keep its files')
    ingest.add_argument('--source-ref', help='Source URL, repository commit/path or other reference; never fetched')
    listing = commands.add_parser('list', help='Show active and replaced documents without loading their content')
    listing.add_argument('--collection', required=True)
    listing.add_argument('--json', action='store_true')
    select = commands.add_parser('view')
    select.add_argument('--collection', action='append', required=True)
    select.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'add':
        result = add(args.root, args.collection, args.file, args.scope, args.title, args.replaces, args.source_ref)
    elif args.command == 'list':
        result = inventory(args.root, args.collection)
        if not args.json:
            print('No documents yet.' if not result else '\n'.join(
                f"{r['selection'].upper():8} {r['id']}  {r['title']}\n         Scope: {r['scope']}"
                for r in result))
            return
    else:
        result = view(args.root, args.collection, args.output)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError) as error:
        print('Knowledge: '+str(error), file=sys.stderr)
        sys.exit(2)
    except subprocess.TimeoutExpired:
        print('Knowledge: conversion timed out; try a smaller or text-exported document.', file=sys.stderr)
        sys.exit(2)
