"""Local SQLite cache, commit outbox and the single-desk controller lock (roadmap CE-05).

The cache is deliberately disposable: it holds current views, collection pages in progress and the facts
waiting for an Iceberg commit. It is never the only copy of a fact. Deleting it and rebuilding from Iceberg
must produce the same current views (CE-11).

Every staged fact carries the payload hash and the Iceberg watermark it reflects, or ``NULL`` while it is not
yet durable. A second writer cannot own the same cache: the controller lock is an OS file lock, and short
commands either take it or fail with an explicit message.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config, contracts

CACHE_SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 512 * 1024  # raw AWS pages belong in S3; a fact payload stays small
PROGRESS_STATES = ("in_progress", "complete", "failed", "abandoned")
COMPLETENESS = ("ok", "partial", "unknown", "denied", "not_enabled", "error")
BATCH_STATES = ("planned", "committing", "committed", "uncertain", "failed")


class CacheError(RuntimeError):
    """The cache cannot be opened, written or migrated as requested."""


class ControllerBusy(CacheError):
    """Another desk process owns this cache."""


def default_path() -> Path:
    override = os.environ.get("RGTRIAGE_CACHE")
    return Path(override) if override else config.home() / "cache" / "desk.sqlite3"


def lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


@dataclass(frozen=True, slots=True)
class StagedEvent:
    event: contracts.Event
    payload: Any
    rowid: int


@dataclass(frozen=True, slots=True)
class BatchStatus:
    batch_id: str
    content_hash: str
    event_ids: tuple[str, ...]
    raw_hashes: tuple[str, ...]
    state: str
    snapshot_id: int | None
    sequence: int | None
    error: str = ""


class ControllerLock:
    """One active desk per cache directory. The lock dies with its process; the owner file is diagnostic only."""

    def __init__(self, path: Path, timeout: float = 5.0):
        self.path = Path(path)
        self.timeout = max(0.0, timeout)
        self._fd: int | None = None

    def acquire(self) -> "ControllerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._lock(fd)
                self._fd = fd
                self._write_owner()
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise ControllerBusy(self._busy_message()) from None
                time.sleep(0.1)

    def _lock(self, fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(self, fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)

    def _owner_file(self) -> Path:
        return self.path.with_name(self.path.name + ".owner")

    def _write_owner(self) -> None:
        try:
            self._owner_file().write_text(json.dumps({
                "pid": os.getpid(), "started_at": contracts.format_time(contracts.utc_now()),
            }), encoding="utf-8")
        except OSError:
            pass  # diagnostics only

    def _busy_message(self) -> str:
        owner = ""
        try:
            data = json.loads(self._owner_file().read_text(encoding="utf-8"))
            owner = f" (pid {data.get('pid')}, started {data.get('started_at')})"
        except (OSError, ValueError):
            pass
        return f"another desk process holds {self.path.name}{owner}; stop it before starting another"

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            self._unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None
            try:
                self._owner_file().unlink()
            except OSError:
                pass

    def __enter__(self) -> "ControllerLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events_local (
  event_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload TEXT NOT NULL,
  scope_account TEXT NOT NULL,
  scope_region TEXT NOT NULL,
  scope_source TEXT NOT NULL,
  scope_filter_hash TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  raw_sha256 TEXT,
  raw_key TEXT,
  raw_ref TEXT,
  state TEXT NOT NULL CHECK (state IN ('pending', 'committed', 'quarantined')),
  batch_id TEXT,
  sequence INTEGER,
  recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_local_state ON events_local(state);
CREATE TABLE IF NOT EXISTS outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE REFERENCES events_local(event_id) ON DELETE CASCADE,
  enqueued_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
  batch_id TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL,
  event_ids TEXT NOT NULL,
  raw_hashes TEXT NOT NULL,
  max_rowid INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('planned', 'committing', 'committed', 'uncertain', 'failed')),
  snapshot_id INTEGER,
  sequence INTEGER,
  created_at TEXT NOT NULL,
  committed_at TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS collection_progress (
  scope_key TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  account TEXT NOT NULL,
  region TEXT NOT NULL,
  source TEXT NOT NULL,
  filter_hash TEXT NOT NULL,
  page_token TEXT NOT NULL DEFAULT '',
  pages INTEGER NOT NULL DEFAULT 0,
  items INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('in_progress', 'complete', 'failed', 'abandoned')),
  completeness TEXT NOT NULL CHECK (completeness IN ('ok', 'partial', 'unknown', 'denied', 'not_enabled', 'error')),
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS collection_progress_run ON collection_progress(run_id, status);
CREATE TABLE IF NOT EXISTS views (
  name TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  staged_rowid INTEGER NOT NULL,
  watermark TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine (
  event_id TEXT PRIMARY KEY,
  existing_payload_hash TEXT NOT NULL,
  incoming_payload_hash TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
"""


class Cache:
    def __init__(self, path: Path | str | None = None, *, timeout: float = 5.0, busy_ms: int = 5000):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._busy_ms = busy_ms
        self._conn: sqlite3.Connection | None = None
        self._lock = ControllerLock(lock_path(self.path), timeout)
        try:
            self._conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=busy_ms / 1000)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute(f"PRAGMA busy_timeout = {int(busy_ms)}")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = FULL")
            self._migrate()
            self.installation_id()
            self.epoch()
        except sqlite3.Error as exc:
            raise CacheError(f"cannot open cache {self.path}: {exc}") from exc

    # ---------------------------------------------------------------- lifecycle
    def _migrate(self) -> None:
        assert self._conn is not None
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > CACHE_SCHEMA_VERSION:
            raise CacheError(f"cache schema {version} is newer than this release ({CACHE_SCHEMA_VERSION})")
        if version < 1:
            self._conn.executescript(f"BEGIN;\n{SCHEMA}\nPRAGMA user_version = {CACHE_SCHEMA_VERSION};\nCOMMIT;")
        missing = {"meta", "events_local", "outbox", "batches", "collection_progress", "views", "quarantine"} - {
            row[0] for row in self._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if missing:
            raise CacheError(f"cache is missing tables: {', '.join(sorted(missing))}")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise CacheError("cache is closed")
        return self._conn

    @contextmanager
    def transaction(self):
        """One local transaction: outbox rows, staged facts and views are all-or-nothing."""
        conn = self.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def acquire_controller(self) -> ControllerLock:
        return self._lock.acquire()

    def release_controller(self) -> None:
        self._lock.release()

    # ---------------------------------------------------------------- meta and watermark
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            self._set_meta(conn, key, value)

    def _set_meta(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, value))

    def installation_id(self, create: bool = True) -> str | None:
        value = self.get_meta("installation_id")
        if value is None and create:
            value = contracts.new_installation_id()
            self.set_meta("installation_id", value)
        return value

    def epoch(self, create: bool = True) -> str | None:
        value = self.get_meta("epoch")
        if value is None and create:
            value = contracts.new_recovery_epoch()
            self.set_meta("epoch", value)
        return value

    def namespace(self) -> str:
        return self.get_meta("namespace") or "remedigenius"

    def watermark(self) -> contracts.Watermark | None:
        raw = self.get_meta("watermark")
        if not raw:
            return None
        try:
            return contracts.Watermark.from_dict(json.loads(raw))
        except (ValueError, KeyError) as exc:
            raise CacheError(f"stored watermark is invalid: {exc}") from exc

    def _write_watermark(self, conn: sqlite3.Connection, watermark: contracts.Watermark) -> None:
        self._set_meta(conn, "watermark", json.dumps(watermark.as_dict(), sort_keys=True))

    # ---------------------------------------------------------------- staging facts
    def stage_facts(self, facts: Iterable[tuple[contracts.Event, Any]], *,
                    views: dict[str, Any] | None = None) -> dict:
        """Stage facts, their outbox rows and optional current views in one local transaction."""
        total = {"new": 0, "identical": 0, "conflict": 0, "conflicts": []}
        encoded = []
        for event, payload in facts:
            text = contracts.canonical_json(payload)
            if len(text.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                raise CacheError(f"fact payload for {event.event_id} exceeds {MAX_PAYLOAD_BYTES} bytes; "
                                 "raw responses belong in S3")
            encoded.append((event, text))
        with self.transaction() as conn:
            rowids = []
            for event, text in encoded:
                outcome, rowid = self._stage(conn, event, text)
                total[outcome] += 1
                if outcome == "conflict":
                    total["conflicts"].append(event.event_id)
                elif rowid is not None:
                    rowids.append(rowid)
            if views:
                staged_rowid = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM events_local").fetchone()[0]
                for name, payload in views.items():
                    self._put_view(conn, name, payload, staged_rowid)
        return total

    def stage_event(self, event: contracts.Event, payload: Any) -> str:
        return self._one(event, payload)

    def _one(self, event: contracts.Event, payload: Any) -> str:
        text = contracts.canonical_json(payload)
        if len(text.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise CacheError(f"fact payload for {event.event_id} exceeds {MAX_PAYLOAD_BYTES} bytes")
        with self.transaction() as conn:
            return self._stage(conn, event, text)[0]

    def _stage(self, conn: sqlite3.Connection, event: contracts.Event, text: str) -> tuple[str, int | None]:
        existing = conn.execute("SELECT payload_hash, state FROM events_local WHERE event_id = ?",
                                (event.event_id,)).fetchone()
        if existing is not None:
            outcome = contracts.classify_replay(existing["payload_hash"], event)
            if outcome == "identical":
                return "identical", None
            conn.execute("INSERT INTO quarantine(event_id, existing_payload_hash, incoming_payload_hash, detected_at, detail) "
                         "VALUES(?, ?, ?, ?, ?) ON CONFLICT(event_id) DO UPDATE SET "
                         "incoming_payload_hash = excluded.incoming_payload_hash, detected_at = excluded.detected_at",
                         (event.event_id, existing["payload_hash"], event.payload_hash,
                          contracts.format_time(contracts.utc_now()), "same event ID with different bytes"))
            conn.execute("UPDATE events_local SET state = 'quarantined' WHERE event_id = ?", (event.event_id,))
            conn.execute("DELETE FROM outbox WHERE event_id = ?", (event.event_id,))
            return "conflict", None
        raw = event.raw_ref
        cursor = conn.execute(
            "INSERT INTO events_local(event_id, kind, payload_hash, payload, scope_account, scope_region, scope_source, "
            "scope_filter_hash, observed_at, ingested_at, raw_sha256, raw_key, raw_ref, state, recorded_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (event.event_id, event.kind, event.payload_hash, text, event.scope.account, event.scope.region,
             event.scope.source, event.scope.filter_hash, event.observed_at, event.ingested_at,
             raw.sha256 if raw else None, raw.key if raw else None,
             contracts.canonical_json(raw.as_dict()) if raw else None, contracts.format_time(contracts.utc_now())))
        conn.execute("INSERT INTO outbox(event_id, enqueued_at) VALUES(?, ?)",
                     (event.event_id, contracts.format_time(contracts.utc_now())))
        return "new", int(cursor.lastrowid)

    def pending_batch(self, limit: int = 500) -> list[StagedEvent]:
        rows = self.conn.execute(
            "SELECT e.rowid AS rowid, e.* FROM outbox o JOIN events_local e ON e.event_id = o.event_id "
            "WHERE e.state = 'pending' ORDER BY o.seq LIMIT ?", (limit,)).fetchall()
        return [StagedEvent(event=self._event(row), payload=json.loads(row["payload"]), rowid=int(row["rowid"]))
                for row in rows]

    def pending_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM outbox o JOIN events_local e ON e.event_id = o.event_id "
                                     "WHERE e.state = 'pending'").fetchone()[0])

    def undurable_decisions(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM outbox o JOIN events_local e ON e.event_id = o.event_id "
                                     "WHERE e.kind = 'decision' AND e.state = 'pending'").fetchone()[0])

    def _event(self, row: sqlite3.Row) -> contracts.Event:
        raw = contracts.RawRef.from_dict(json.loads(row["raw_ref"])) if row["raw_ref"] else None
        return contracts.Event(
            event_id=row["event_id"], kind=row["kind"], installation_id=self.get_meta("installation_id") or "",
            epoch=self.get_meta("epoch") or "", sequence=int(row["sequence"] or 0),
            scope=contracts.Scope(account=row["scope_account"], region=row["scope_region"],
                                  source=row["scope_source"], filter_hash=row["scope_filter_hash"]),
            observed_at=row["observed_at"], ingested_at=row["ingested_at"], payload_hash=row["payload_hash"],
            raw_ref=raw, batch_id=None)

    def event(self, event_id: str) -> StagedEvent | None:
        row = self.conn.execute("SELECT rowid AS rowid, * FROM events_local WHERE event_id = ?", (event_id,)).fetchone()
        return StagedEvent(self._event(row), json.loads(row["payload"]), int(row["rowid"])) if row else None

    def conflicts(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM quarantine ORDER BY detected_at")]

    # ---------------------------------------------------------------- batches
    def start_batch(self, plan: contracts.BatchPlan, max_rowid: int) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT INTO batches(batch_id, content_hash, event_ids, raw_hashes, max_rowid, state, created_at) "
                         "VALUES(?, ?, ?, ?, ?, 'committing', ?) ON CONFLICT(batch_id) DO UPDATE SET "
                         "state = CASE WHEN batches.state = 'committed' THEN 'committed' ELSE 'committing' END, "
                         "max_rowid = MAX(batches.max_rowid, excluded.max_rowid)",
                         (plan.batch_id, plan.content_hash, json.dumps(list(plan.event_ids)),
                          json.dumps(list(plan.raw_hashes)), int(max_rowid), contracts.format_time(contracts.utc_now())))

    def complete_batch(self, batch_id: str, snapshot_id: int | None, sequence: int) -> contracts.Watermark:
        """Promote events and views only after the Iceberg commit is known to have succeeded."""
        now = contracts.format_time(contracts.utc_now())
        with self.transaction() as conn:
            batch = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if batch is None:
                raise CacheError(f"unknown batch {batch_id}")
            if batch["state"] == "committed":
                mark = self.watermark()
                if mark is not None:
                    return mark
            ids = json.loads(batch["event_ids"])
            conn.executemany("UPDATE events_local SET state = 'committed', batch_id = ?, sequence = ? WHERE event_id = ?",
                             [(batch_id, int(sequence), event_id) for event_id in ids])
            conn.executemany("DELETE FROM outbox WHERE event_id = ?", [(event_id,) for event_id in ids])
            mark = contracts.Watermark(self.get_meta("installation_id") or "", self.namespace(),
                                       self.get_meta("epoch") or "", int(sequence), now, snapshot_id)
            self._write_watermark(conn, mark)
            conn.execute("UPDATE views SET watermark = ? WHERE watermark IS NULL AND staged_rowid <= ?",
                         (json.dumps(mark.as_dict(), sort_keys=True), int(batch["max_rowid"])))
            conn.execute("UPDATE batches SET state = 'committed', snapshot_id = ?, sequence = ?, committed_at = ?, error = NULL "
                         "WHERE batch_id = ?", (snapshot_id, int(sequence), now, batch_id))
            return mark

    def fail_batch(self, batch_id: str, error: str, *, uncertain: bool = False) -> None:
        state = "uncertain" if uncertain else "failed"
        with self.transaction() as conn:
            conn.execute("UPDATE batches SET state = ?, error = ? WHERE batch_id = ?", (state, error[:500], batch_id))

    def batch(self, batch_id: str) -> BatchStatus | None:
        row = self.conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
        if row is None:
            return None
        return BatchStatus(batch_id=row["batch_id"], content_hash=row["content_hash"],
                           event_ids=tuple(json.loads(row["event_ids"])), raw_hashes=tuple(json.loads(row["raw_hashes"])),
                           state=row["state"], snapshot_id=row["snapshot_id"], sequence=row["sequence"],
                           error=row["error"] or "")

    def batches(self, state: str | None = None) -> list[BatchStatus]:
        sql, args = "SELECT batch_id FROM batches", ()
        if state:
            sql, args = sql + " WHERE state = ?", (state,)
        return [b for b in (self.batch(row["batch_id"]) for row in self.conn.execute(sql + " ORDER BY created_at", args)) if b]

    def next_sequence(self) -> int:
        mark = self.watermark()
        return (mark.sequence + 1) if mark else 1

    # ---------------------------------------------------------------- collection progress
    def save_progress(self, scope_key: str, *, run_id: str, account: str, region: str, source: str,
                      filter_hash: str = "", page_token: str = "", pages: int = 0, items: int = 0,
                      status: str = "in_progress", completeness: str = "unknown") -> None:
        if status not in PROGRESS_STATES:
            raise CacheError(f"unknown progress status {status!r}")
        if completeness not in COMPLETENESS:
            raise CacheError(f"unknown completeness {completeness!r}")
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO collection_progress(scope_key, run_id, account, region, source, filter_hash, page_token, "
                "pages, items, status, completeness, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(scope_key) DO UPDATE SET run_id = excluded.run_id, page_token = excluded.page_token, "
                "pages = excluded.pages, items = excluded.items, status = excluded.status, "
                "completeness = excluded.completeness, updated_at = excluded.updated_at",
                (scope_key, run_id, account, region, source, filter_hash, page_token, int(pages), int(items),
                 status, completeness, contracts.format_time(contracts.utc_now())))

    def load_progress(self, scope_key: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM collection_progress WHERE scope_key = ?", (scope_key,)).fetchone()
        return dict(row) if row else None

    def progress_for_run(self, run_id: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            "SELECT * FROM collection_progress WHERE run_id = ? ORDER BY account, region, source", (run_id,))]

    # ---------------------------------------------------------------- views
    def put_view(self, name: str, payload: Any, staged_rowid: int | None = None) -> None:
        text = contracts.canonical_json(payload)
        with self.transaction() as conn:
            rowid = int(staged_rowid if staged_rowid is not None else
                        conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM events_local").fetchone()[0])
            self._put_view(conn, name, payload, rowid)

    def _put_view(self, conn: sqlite3.Connection, name: str, payload: Any, staged_rowid: int) -> None:
        conn.execute("INSERT INTO views(name, payload, staged_rowid, watermark, updated_at) VALUES(?, ?, ?, NULL, ?) "
                     "ON CONFLICT(name) DO UPDATE SET payload = excluded.payload, staged_rowid = excluded.staged_rowid, "
                     "watermark = NULL, updated_at = excluded.updated_at",
                     (name, contracts.canonical_json(payload), int(staged_rowid),
                      contracts.format_time(contracts.utc_now())))

    def get_view(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM views WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return {"payload": json.loads(row["payload"]), "staged_rowid": int(row["staged_rowid"]),
                "watermark": json.loads(row["watermark"]) if row["watermark"] else None,
                "updated_at": row["updated_at"]}

    def health(self) -> dict:
        mark = self.watermark()
        return {
            "installation_id": self.installation_id(create=False), "namespace": self.namespace(),
            "epoch": self.epoch(create=False),
            "commit_watermark": mark.as_dict() if mark else None,
            "commit_age_seconds": mark.lag_seconds() if mark else None,
            "outbox_events": self.pending_count(), "undurable_decisions": self.undurable_decisions(),
            "conflicts": len(self.conflicts()),
            "batches": {state: len(self.batches(state)) for state in BATCH_STATES},
        }