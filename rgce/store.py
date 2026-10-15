"""Append-only through the product API. Local administrators still control the disk."""
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def default_home():
    return Path(os.environ.get("RGCE_HOME", str(Path.home() / ".rgce"))).resolve()


class Store:
    def __init__(self, home=None, object_storage=None):
        self._write_lock = threading.RLock()
        self._recovery_required = False
        self.home = Path(home).resolve() if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "evidence.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, created TEXT NOT NULL, body TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS records_kind ON records(kind, created)")
        self.objects = object_storage
        if self.objects is None and os.environ.get('RGCE_STORAGE_BUCKET'):
            from .object_storage import ObjectStorage
            self.objects = ObjectStorage(os.environ['RGCE_STORAGE_BUCKET'], os.environ.get('RGCE_STORAGE_PREFIX', ''))
        if self.objects:
            identity = self.objects.bucket + '/' + self.objects.prefix
            with self.connect() as db:
                # SQLite DDL otherwise commits outside the implicit DML transaction:
                # a rejected switch must not leave a binding table in a local home.
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS storage_binding (identity TEXT NOT NULL)')
                bound = db.execute('SELECT identity FROM storage_binding').fetchone()
                if bound and bound[0] != identity:
                    raise ValueError('Cache belongs to another S3 workspace; use a fresh home')
                if not bound:
                    if db.execute('SELECT COUNT(*) FROM records').fetchone()[0]:
                        raise ValueError('S3 mode requires a fresh home; migrate explicitly')
                    db.execute('INSERT INTO storage_binding VALUES (?)', (identity,))
            self.recover()
        else:
            with self.connect() as db:
                if db.execute("SELECT name FROM sqlite_master WHERE name='storage_binding'").fetchone():
                    raise ValueError('This cache requires its S3 configuration; refusing local-only writes')

    def recover(self):
        records = sorted(self.objects.records(), key=lambda r: (r['stored_at'], r['id']))
        # Originals are independent durable objects; do not report complete recovery
        # if one referenced original is missing or corrupt.
        for r in records:
            if r['kind'] == 'document_source':
                from .documents import validate_file, write_review_copy
                b = r['body']
                data = self.objects.original(b['source_sha256'])
                suffix = validate_file(b['name'], data)
                original = self.home / 'knowledge' / 'originals' / b['source_sha256'] / ('source' + suffix)
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(data)
                write_review_copy(self, r)
        with self.connect() as db:
            db.execute('DELETE FROM records')
            for r in records:
                db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)', (r['id'], r['kind'], r['stored_at'], canonical(r['body'])))
        return len(records)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, body):
        payload = {"kind": kind, "body": body}
        key = digest(payload)
        record = {'id': key, 'kind': kind, 'stored_at': now(), 'body': body}
        with self.write_guard():
            record = self.persist_record(record)
            with self.connect() as db:
                db.execute("INSERT OR IGNORE INTO records VALUES (?,?,?,?)", (key, kind, record['stored_at'], canonical(body)))
        return self.get(key)

    @contextmanager
    def write_guard(self):
        with self._write_lock:
            if self._recovery_required:
                raise ValueError('Durable write outcome uncertain; restart the workspace to recover before writing again')
            yield
            self._recovery_required = False

    def persist_record(self, record):
        if self.objects:
            # Remains set if remote acknowledgement or local commit fails. A retry
            # must recover S3 first, rather than publish against a stale cache.
            self._recovery_required = True
            return self.objects.put_record(record)
        return record

    def get(self, key):
        with self.connect() as db:
            row = db.execute("SELECT id,kind,created,body FROM records WHERE id=?", (key,)).fetchone()
        if not row:
            raise ValueError("Record not found")
        body = json.loads(row[3])
        if digest({"kind": row[1], "body": body}) != row[0]:
            raise ValueError("Record integrity check failed")
        return {"id": row[0], "kind": row[1], "stored_at": row[2], "body": body}

    def list(self, kind=None, limit=100):
        with self.connect() as db:
            rows = db.execute("SELECT id FROM records WHERE (? IS NULL OR kind=?) ORDER BY created DESC, rowid DESC LIMIT ?", (kind, kind, min(max(limit, 1), 500))).fetchall()
        return [self.get(row[0]) for row in rows]
