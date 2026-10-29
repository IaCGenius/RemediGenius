"""Local cache, outbox and controller lock (roadmap CE-05)."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from rgtriage import cache as cache_module
from rgtriage import contracts

ROOT = Path(__file__).resolve().parents[1]
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
NOW = "2026-06-15T10:00:00Z"


@pytest.fixture
def store(tmp_path):
    item = cache_module.Cache(tmp_path / "desk.sqlite3", timeout=1, busy_ms=3000)
    yield item
    item.close()


def observation(item: cache_module.Cache, payload: dict, *, observed_at: str = NOW, scope: contracts.Scope = SCOPE,
                raw_bytes: bytes = b'{"Findings":[]}') -> contracts.Event:
    digest = contracts.payload_hash(payload)
    raw_sha = contracts.bytes_sha256(raw_bytes)
    raw = contracts.RawRef(sha256=raw_sha, key=contracts.raw_key(scope, observed_at, raw_sha), size=len(raw_bytes),
                           scope=scope, operation="ListFindings", observed_at=observed_at)
    return contracts.Event(
        event_id=contracts.observation_event_id(item.installation_id(), scope, observed_at, digest),
        kind="observation", installation_id=item.installation_id(), epoch=item.epoch(), sequence=0,
        scope=scope, observed_at=observed_at, ingested_at=observed_at, payload_hash=digest, raw_ref=raw)


def run_child(tmp_path: Path, code: str, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT), RGTRIAGE_CACHE=str(tmp_path / "desk.sqlite3"))
    return subprocess.run([sys.executable, "-c", code, *args], env=env, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def test_schema_migrates_and_identity_survives_reopen(tmp_path):
    path = tmp_path / "desk.sqlite3"
    with cache_module.Cache(path) as first:
        assert first.conn.execute("PRAGMA user_version").fetchone()[0] == cache_module.CACHE_SCHEMA_VERSION
        installation, epoch = first.installation_id(), first.epoch()
        assert installation and epoch
    with cache_module.Cache(path) as second:
        assert (second.installation_id(), second.epoch()) == (installation, epoch)
        assert second.watermark() is None


def test_stage_then_commit_promotes_events_and_views(store):
    facts = [(observation(store, {"n": n}), {"n": n}) for n in range(3)]
    result = store.stage_facts(facts, views={"board": {"findings": 3}})
    assert result["new"] == 3 and result["identical"] == 0
    assert store.pending_count() == 3
    staged = store.pending_batch()
    plan = contracts.plan_batch([item.event for item in staged])
    store.start_batch(plan, max(item.rowid for item in staged))
    assert store.batch(plan.batch_id).state == "committing"
    mark = store.complete_batch(plan.batch_id, snapshot_id=101, sequence=1)
    assert (mark.snapshot_id, mark.sequence) == (101, 1)
    assert store.watermark() == mark
    assert store.pending_count() == 0
    view = store.get_view("board")
    assert view["payload"] == {"findings": 3}
    assert view["watermark"]["snapshot_id"] == 101
    assert store.batch(plan.batch_id).state == "committed"
    assert store.event(facts[0][0].event_id).event.payload_hash == facts[0][0].payload_hash
    health = store.health()
    assert health["outbox_events"] == 0 and health["commit_watermark"]["sequence"] == 1


def test_identical_replay_is_a_noop_and_conflict_is_quarantined(store):
    event = observation(store, {"n": 1})
    assert store.stage_event(event, {"n": 1}) == "new"
    assert store.stage_event(event, {"n": 1}) == "identical"
    assert store.pending_count() == 1
    conflict = replace(event, payload_hash="f" * 64)
    assert store.stage_event(conflict, {"n": 2}) == "conflict"
    assert store.pending_count() == 0
    assert len(store.conflicts()) == 1
    assert store.conn.execute("SELECT state FROM events_local WHERE event_id = ?",
                              (event.event_id,)).fetchone()["state"] == "quarantined"
    assert store.stage_event(observation(store, {"n": 3}), {"n": 3}) == "new"
    assert store.pending_count() == 1


def test_stage_facts_is_all_or_nothing_when_a_view_cannot_be_encoded(store):
    facts = [(observation(store, {"n": n}), {"n": n}) for n in range(2)]
    with pytest.raises(contracts.ContractError):
        store.stage_facts(facts, views={"bad": {"value": float("nan")}})
    assert store.pending_count() == 0
    assert store.get_view("bad") is None
    with pytest.raises(contracts.ContractError):
        store.stage_facts([(observation(store, {"n": 9}), {"n": float("inf")})])
    assert store.pending_count() == 0


def test_oversized_fact_is_refused(store):
    with pytest.raises(cache_module.CacheError):
        store.stage_event(observation(store, {"blob": "x"}), {"blob": "x" * (cache_module.MAX_PAYLOAD_BYTES + 1)})
    assert store.pending_count() == 0


def test_progress_round_trip_and_validation(store):
    assert store.load_progress("111122223333/us-east-1/inspector") is None
    store.save_progress("111122223333/us-east-1/inspector", run_id="run-1", account="111122223333",
                        region="us-east-1", source="inspector", page_token="token", pages=2, items=30,
                        status="in_progress", completeness="partial")
    record = store.load_progress("111122223333/us-east-1/inspector")
    assert (record["pages"], record["items"], record["status"], record["completeness"]) == (2, 30, "in_progress", "partial")
    store.save_progress("111122223333/us-east-1/inspector", run_id="run-1", account="111122223333",
                        region="us-east-1", source="inspector", status="complete", completeness="ok")
    assert [r["status"] for r in store.progress_for_run("run-1")] == ["complete"]
    with pytest.raises(cache_module.CacheError):
        store.save_progress("x", run_id="r", account="a", region="r", source="s", status="done")
    with pytest.raises(cache_module.CacheError):
        store.save_progress("x", run_id="r", account="a", region="r", source="s", completeness="maybe")


def test_batches_are_idempotent(store):
    event = observation(store, {"n": 1})
    store.stage_facts([(event, {"n": 1})])
    staged = store.pending_batch()
    plan = contracts.plan_batch([staged[0].event])
    store.start_batch(plan, staged[0].rowid)
    store.start_batch(plan, staged[0].rowid)
    assert store.batch(plan.batch_id).state == "committing"
    first = store.complete_batch(plan.batch_id, 7, 1)
    second = store.complete_batch(plan.batch_id, 7, 1)
    assert first == second
    assert store.pending_count() == 0


def test_subprocess_kill_before_commit_leaves_nothing(tmp_path):
    path = tmp_path / "desk.sqlite3"
    cache_module.Cache(path).close()
    child = """
import os, sys
from rgtriage import cache, contracts
c = cache.Cache(sys.argv[1])
scope = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
payload = {"x": 1}
digest = contracts.payload_hash(payload)
event = contracts.Event(
    event_id=contracts.observation_event_id(c.installation_id(), scope, "2026-06-15T10:00:00Z", digest),
    kind="observation", installation_id=c.installation_id(), epoch=c.epoch(), sequence=0, scope=scope,
    observed_at="2026-06-15T10:00:00Z", ingested_at="2026-06-15T10:00:00Z", payload_hash=digest)
with c.transaction() as conn:
    c._stage(conn, event, contracts.canonical_json(payload))
    c._put_view(conn, "board", {"x": 1}, 1)
    os._exit(9)
"""
    result = run_child(tmp_path, child, str(path))
    assert result.returncode == 9, result.stderr
    with cache_module.Cache(path) as reopened:
        assert reopened.pending_count() == 0
        assert reopened.get_view("board") is None
        assert reopened.conn.execute("SELECT COUNT(*) FROM events_local").fetchone()[0] == 0


def test_subprocess_kill_after_commit_keeps_rows_and_view(tmp_path):
    path = tmp_path / "desk.sqlite3"
    cache_module.Cache(path).close()
    child = """
import os, sys
from rgtriage import cache, contracts
c = cache.Cache(sys.argv[1])
scope = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
payload = {"x": 1}
digest = contracts.payload_hash(payload)
event = contracts.Event(
    event_id=contracts.observation_event_id(c.installation_id(), scope, "2026-06-15T10:00:00Z", digest),
    kind="observation", installation_id=c.installation_id(), epoch=c.epoch(), sequence=0, scope=scope,
    observed_at="2026-06-15T10:00:00Z", ingested_at="2026-06-15T10:00:00Z", payload_hash=digest)
c.stage_facts([(event, payload)], views={"board": {"x": 1}})
os._exit(0)
"""
    result = run_child(tmp_path, child, str(path))
    assert result.returncode == 0, result.stderr
    with cache_module.Cache(path) as reopened:
        assert reopened.pending_count() == 1
        assert reopened.get_view("board")["payload"] == {"x": 1}


def test_controller_lock_excludes_a_second_process(tmp_path):
    lock = tmp_path / "desk.sqlite3.lock"
    child = """
import sys, time
from rgtriage.cache import ControllerLock
lock = ControllerLock(sys.argv[1], timeout=0).acquire()
print("ready", flush=True)
time.sleep(30)
"""
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    proc = subprocess.Popen([sys.executable, "-c", child, str(lock)], env=env, cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
        with pytest.raises(cache_module.ControllerBusy) as busy:
            cache_module.ControllerLock(lock, timeout=0.3).acquire()
        assert "another desk process" in str(busy.value)
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            held = cache_module.ControllerLock(lock, timeout=0).acquire()
            held.release()
            return
        except cache_module.ControllerBusy:
            time.sleep(0.2)
    pytest.fail("the lock was not released when its process died")


def test_concurrent_writers_do_not_drop_events(tmp_path):
    import threading

    path = tmp_path / "desk.sqlite3"
    cache_module.Cache(path).close()
    failures = []

    def writer(index: int):
        try:
            item = cache_module.Cache(path, timeout=10, busy_ms=10000)
            for n in range(10):
                payload = {"writer": index, "n": n}
                item.stage_event(observation(item, payload), payload)
            item.close()
        except Exception as exc:  # surfaced by the assertion below
            failures.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not failures, failures
    with cache_module.Cache(path) as reopened:
        assert reopened.pending_count() == 40
        assert reopened.conn.execute("SELECT COUNT(*) FROM events_local").fetchone()[0] == 40


def test_disk_full_is_an_explicit_error(store):
    free_pages = store.conn.execute("PRAGMA max_page_count").fetchone()[0]
    used = store.conn.execute("PRAGMA page_count").fetchone()[0]
    store.conn.execute(f"PRAGMA max_page_count = {max(used + 1, 2)}")
    try:
        with pytest.raises(sqlite3.OperationalError):
            store.stage_event(observation(store, {"blob": "x"}), {"blob": "x" * 400_000})
    finally:
        store.conn.execute(f"PRAGMA max_page_count = {free_pages}")
    assert store.pending_count() == 0