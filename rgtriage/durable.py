"""Durable storage for RemediGenius Community Edition state.

Local disks are disposable (a Spot instance can be reclaimed at any time; a workstation
container can be removed). The durable copy lives in S3 (Spot) or a local folder (Docker
workstation). Each home (the Hermes home, the desk state) is checkpointed as a verified
archive; a home is restored only when it is empty, so live state always wins.

  url: s3://bucket/prefix   or   /path/to/folder   (file:///path also accepted)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA = "remedigenius-ce-state/1"
LINEAGE = ".lineage"  # lineage ids live in the desk state, so homes such as Hermes can stay read-only to the desk
KEEP = 10  # snapshots kept per home
EXCLUDE = {".lineage", "cache", "image_cache", "audio_cache", "node_modules", ".git", "backups", "sandboxes", "installs", ".local",
           ".home", "__pycache__", "checkpoints"}
SKIP_SUFFIXES = ("-wal", "-shm", ".sock", ".pending", ".tmp", ".lock")


class Backend:
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def list(self, prefix: str) -> list[str]: ...
    def delete(self, key: str) -> None: ...


class FolderBackend(Backend):
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("key outside durable folder")
        return path

    def put(self, key, data):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key):
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def list(self, prefix):
        base = self._path(prefix)
        return sorted(p.relative_to(self.root).as_posix() for p in base.glob("*") if p.is_file()) if base.exists() else []

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


class S3Backend(Backend):
    def __init__(self, bucket: str, prefix: str):
        import boto3
        self.bucket, self.prefix = bucket, prefix.strip("/")
        self.s3 = boto3.client("s3")

    def _key(self, key):
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key, data):
        self.s3.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ServerSideEncryption="AES256")

    def get(self, key):
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def list(self, prefix):
        pages = self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self._key(prefix) + "/")
        cut = len(self.prefix) + 1 if self.prefix else 0
        return sorted(o["Key"][cut:] for page in pages for o in page.get("Contents", []))

    def delete(self, key):
        self.s3.delete_object(Bucket=self.bucket, Key=self._key(key))


def backend(url: str) -> Backend:
    if url.startswith("s3://"):
        bucket, _, prefix = url[5:].partition("/")
        return S3Backend(bucket, prefix)
    if url.startswith("file://"):
        url = url[7:]
    return FolderBackend(url)


DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
DB_ATTEMPTS = 6


def _backup(source_uri: str, dest: Path, uri: bool = True) -> None:
    dest.unlink(missing_ok=True)
    with closing(sqlite3.connect(source_uri, uri=uri, timeout=10)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)
    with closing(sqlite3.connect(dest)) as check:
        if check.execute("pragma quick_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("copy failed integrity check")


def _copy_database(source: Path, dest: Path) -> None:
    """Consistent copy of a live SQLite database, including its WAL.

    1. Online backup through a read-only connection.
    2. If SQLite cannot open it in place (WAL database without a -shm file on a read-only mount), copy the
       database with its -wal/-shm files to a private folder and back up from there; SQLite's WAL recovery
       turns that copy into a consistent snapshot, and an integrity check confirms it.
    Retries cover Hermes holding a write lock while it starts or stops.
    """
    for attempt in range(DB_ATTEMPTS):
        try:
            try:
                _backup(f"file:{source}?mode=ro", dest)
            except sqlite3.OperationalError as exc:
                if "unable to open" not in str(exc) and "readonly" not in str(exc):
                    raise
                with tempfile.TemporaryDirectory() as tmp:
                    copy = Path(tmp) / source.name
                    shutil.copyfile(source, copy)
                    for suffix in ("-wal", "-shm"):
                        side = source.with_name(source.name + suffix)
                        if side.exists():
                            shutil.copyfile(side, copy.with_name(copy.name + suffix))
                    _backup(str(copy), dest, uri=False)
            return
        except (sqlite3.Error, OSError):
            if attempt == DB_ATTEMPTS - 1:
                raise
            time.sleep(2 * (attempt + 1))


def _stage(home: Path, stage: Path) -> tuple[dict, list]:
    """Copy the home into `stage`. Returns (hashes, failed): a database that cannot be copied is a failure,
    never silently left out, so an incomplete checkpoint can never become the latest one."""
    hashes, failed = {}, []
    for source in sorted(home.rglob("*")):
        relative = source.relative_to(home)
        if any(part in EXCLUDE for part in relative.parts) or source.is_symlink() or not source.is_file():
            continue
        if source.name.endswith(SKIP_SUFFIXES):
            continue
        dest = stage / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source.suffix in DB_SUFFIXES:
                _copy_database(source, dest)
            else:
                shutil.copyfile(source, dest)
        except FileNotFoundError:
            continue  # deleted while the checkpoint ran; it is genuinely gone
        except (sqlite3.Error, OSError) as exc:
            failed.append(f"{relative.as_posix()}: {exc}")
            continue
        hashes[relative.as_posix()] = hashlib.sha256(dest.read_bytes()).hexdigest()
    return hashes, failed


def lineage_dir() -> Path:
    return Path(os.environ.get("RGTRIAGE_LINEAGE") or Path(os.environ.get("RGTRIAGE_HOME") or Path.home() / ".rgtriage") / LINEAGE)


def checkpoint(home: str | Path, name: str, store: Backend, force: bool = False) -> dict:
    """Upload a verified archive of `home` unless nothing changed since the last checkpoint.

    Refuses (DIVERGED) when the home does not descend from the latest checkpoint, e.g. a fresh home
    whose restore did not run; otherwise an empty home could replace good state. `force` starts a new lineage.
    """
    home = Path(home)
    if not home.is_dir():
        return {"home": name, "status": "NO_HOME"}
    previous = store.get(f"{name}/latest.json")
    previous = json.loads(previous) if previous else None
    id_file = lineage_dir() / name
    state_id = id_file.read_text().strip() if id_file.exists() else ""
    if previous and previous.get("state_id") and previous["state_id"] != state_id and not force:
        return {"home": name, "status": "DIVERGED",
                "note": "home does not descend from the latest checkpoint; restore it first or checkpoint with --force"}
    if not state_id or force:
        state_id = uuid.uuid4().hex
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(state_id)
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp) / "stage"
        stage.mkdir()
        hashes, failed = _stage(home, stage)
        if failed:
            return {"home": name, "status": "INCOMPLETE", "failed": failed[:5],
                    "note": "not uploaded; the previous checkpoint stays the latest"}
        if not hashes:
            return {"home": name, "status": "EMPTY"}
        if previous and previous.get("files") == hashes:
            return {"home": name, "status": "UNCHANGED", "files": len(hashes)}
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for path in hashes:
                tar.add(stage / path, arcname=path, recursive=False)
        data = buffer.getvalue()
    key = f"{name}/snapshots/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}.tar.gz"
    store.put(key, data)
    manifest = {"schema": SCHEMA, "key": key, "sha256": hashlib.sha256(data).hexdigest(), "files": hashes, "state_id": state_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notice": "Private session, configuration and security data; may contain model keys. Protect access."}
    # The pointer is written last: an interrupted upload never becomes the latest checkpoint.
    store.put(f"{name}/latest.json", json.dumps(manifest).encode())
    for old in store.list(f"{name}/snapshots")[:-KEEP]:
        if old != key:
            store.delete(old)
    return {"home": name, "status": "SAVED", "files": len(hashes), "bytes": len(data), "created_at": manifest["created_at"]}


def restore(home: str | Path, name: str, store: Backend, owner: tuple[int, int] | None = None) -> dict:
    """Restore the latest checkpoint into an empty (or missing) home. Never overwrites live state."""
    home = Path(home)
    # Empty folders (created by setup) hold no state; any file means live state that must win.
    if home.exists() and any(p.is_file() and not EXCLUDE.intersection(p.relative_to(home).parts) for p in home.rglob("*")):
        return {"home": name, "status": "SKIPPED_NOT_EMPTY"}
    raw = store.get(f"{name}/latest.json")
    if raw is None:
        return {"home": name, "status": "NO_CHECKPOINT"}
    manifest = json.loads(raw)
    if not manifest["key"].startswith(f"{name}/snapshots/"):
        raise ValueError("checkpoint key outside its home")
    data = store.get(manifest["key"])
    if data is None or hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise ValueError("checkpoint archive missing or hash mismatch")
    with tempfile.TemporaryDirectory() as temp:
        stage = Path(temp) / "verified"
        stage.mkdir()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            members = tar.getmembers()
            names = {m.name for m in members}
            if len(names) != len(members) or names != set(manifest["files"]):
                raise ValueError("checkpoint contents do not match its manifest")
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or "\\" in member.name or not member.isfile():
                    raise ValueError("unsafe checkpoint entry")
                target = stage / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if hashlib.sha256(target.read_bytes()).hexdigest() != manifest["files"][member.name]:
                    raise ValueError("file hash mismatch")
        home.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, home, dirs_exist_ok=True)
        if manifest.get("state_id"):
            lineage_dir().mkdir(parents=True, exist_ok=True)
            (lineage_dir() / name).write_text(manifest["state_id"])
    if owner and hasattr(os, "chown"):
        for path in [home, *home.rglob("*")]:
            os.chown(path, *owner)
    return {"home": name, "status": "RESTORED", "files": len(manifest["files"]), "created_at": manifest["created_at"]}


def parse_homes(specs: list[str]) -> dict[str, str]:
    homes = {}
    for spec in specs or []:
        name, _, path = spec.partition("=")
        if not name.isidentifier() or not path:
            raise ValueError(f"expected name=path, got {spec!r}")
        homes[name] = path
    return homes
