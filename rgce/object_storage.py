"""S3 durable records; local SQLite is a disposable index in this mode."""
import hashlib
import json
import os
import re
from datetime import datetime

from .store import canonical, digest


class ObjectStorage:
    def __init__(self, bucket, prefix, client=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
            raise ValueError('Invalid storage bucket')
        if not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', prefix):
            raise ValueError('Storage prefix must identify one workspace')
        self.bucket, self.prefix = bucket, prefix + '/'
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.Session(profile_name=os.environ.get('RGCE_STORAGE_PROFILE')).client(
                's3', config=Config(retries={'max_attempts': 3}, connect_timeout=5, read_timeout=30))
        self.client = client

    def read(self, key, limit=32_000_000):
        response = self.client.get_object(Bucket=self.bucket, Key=self.prefix + key)
        stream = response['Body']
        try:
            data = stream.read(limit + 1)
        finally:
            stream.close()
        if len(data) > limit:
            raise ValueError('Durable object exceeds size limit')
        return data

    def create(self, key, data):
        try:
            self.client.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=data,
                                   IfNoneMatch='*', ServerSideEncryption='AES256')
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') not in ('PreconditionFailed', '412'):
                raise
            if self.read(key) != data:
                raise ValueError('Existing durable object differs; refusing overwrite') from None

    def put_record(self, record):
        key = 'records/' + record['id'] + '.json'
        try:
            self.client.put_object(Bucket=self.bucket, Key=self.prefix + key,
                                   Body=canonical(record).encode('utf-8'), IfNoneMatch='*', ServerSideEncryption='AES256')
        except Exception as exc:
            if getattr(exc, 'response', {}).get('Error', {}).get('Code') not in ('PreconditionFailed', '412'):
                raise
            existing = json.loads(self.read(key))
            if any(existing.get(k) != record[k] for k in ('id', 'kind', 'body')):
                raise ValueError('Existing durable record differs') from None
            return existing
        return record

    def records(self):
        paginator = self.client.get_paginator('list_objects_v2')
        count = 0
        total = 0
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix + 'records/'):
            for obj in page.get('Contents', []):
                count += 1
                if count > 100000:
                    raise ValueError('Workspace exceeds 100000 records')
                key = obj['Key'][len(self.prefix):]
                if not re.fullmatch(r'records/[a-f0-9]{64}\.json', key):
                    raise ValueError('Unexpected durable record key')
                raw = self.read(key)
                total += len(raw)
                if total > 256_000_000:
                    raise ValueError('Workspace recovery exceeds 256MB of record data')
                record = json.loads(raw)
                if set(record) != {'id', 'kind', 'body', 'stored_at'} or not isinstance(record['stored_at'], str) or digest({'kind': record['kind'], 'body': record['body']}) != record['id'] or key != 'records/' + record['id'] + '.json':
                    raise ValueError('Durable record integrity check failed')
                if datetime.fromisoformat(record['stored_at'].replace('Z', '+00:00')).tzinfo is None:
                    raise ValueError('Durable record timestamp requires a timezone')
                yield record

    def put_original(self, source_hash, data):
        if hashlib.sha256(data).hexdigest() != source_hash:
            raise ValueError('Original integrity check failed')
        self.create('originals/' + source_hash, data)

    def original(self, source_hash):
        if not re.fullmatch(r'[a-f0-9]{64}', source_hash):
            raise ValueError('Invalid original hash')
        data = self.read('originals/' + source_hash, 5_000_000)
        if hashlib.sha256(data).hexdigest() != source_hash:
            raise ValueError('Durable original integrity check failed')
        return data


def migrate_local(store, target):
    """Explicit copy to a dedicated destination; source is never removed."""
    if store.objects:
        raise ValueError('Select a local-only source workspace for migration')
    with store.connect() as db:
        keys = [r[0] for r in db.execute('SELECT id FROM records ORDER BY created,rowid')]
    records = [store.get(key) for key in keys]
    existing = {r['id']: r for r in target.records()}
    expected = {r['id']: r for r in records}
    if any(key not in expected or record != expected[key] for key, record in existing.items()):
        raise ValueError('Destination contains other records; choose a dedicated empty prefix')
    originals = []
    from pathlib import Path
    from .documents import validate_file
    for r in records:
        if r['kind'] == 'document_source':
            b = r['body']; suffix = Path(b['name']).suffix.lower()
            path = store.home / 'knowledge' / 'originals' / b['source_sha256'] / ('source' + suffix)
            if not path.resolve().is_relative_to(store.home):
                raise ValueError('Original path escapes workspace')
            data = path.read_bytes()
            validate_file(b['name'], data)
            if hashlib.sha256(data).hexdigest() != b['source_sha256']:
                raise ValueError('Local original integrity check failed')
            originals.append((b['source_sha256'], data))
    for source_hash, data in originals: target.put_original(source_hash, data)
    for record in records: target.put_record(record)
    if {r['id']: r for r in target.records()} != expected:
        raise ValueError('Migration verification failed; retain source')
    for source_hash, data in originals:
        if target.original(source_hash) != data:
            raise ValueError('Original migration verification failed')
    return {'records_verified': len(records), 'originals_verified': len(originals),
            'source_retained': True, 'notice': 'Stop the local writer before opening the S3 workspace. Untracked files and agent sessions are not migrated.'}
