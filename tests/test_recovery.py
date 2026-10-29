"""Rebuild on new compute and read-only operation reconciliation (roadmap CE-11)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from rgtriage import cache as cache_module
from rgtriage import commit, contracts, current, iceberg_store, ocsf, rawstore, recovery

NOW = "2026-06-15T10:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")


class FailingStorage:
    def ensure_tables(self):
        raise iceberg_store.IcebergUnavailable("Glue is unreachable")


def setup(tmp_path):
    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = iceberg_store.IcebergStore.open(profile)
    store.ensure_tables()
    cache = cache_module.Cache(tmp_path / "desk.sqlite3", timeout=1)
    raw = rawstore.RawStore(rawstore.FolderBackend(tmp_path / "raw"))
    committer = commit.Committer(cache, raw, store)
    state = current.CurrentState(store, cache)
    return cache, raw, store, committer, state


def finding(n: int = 1) -> dict:
    return {"key": f"key{n}", "source": "inspector", "native_id": f"n{n}", "product": "Inspector",
            "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}", "description": "d",
            "severity": "HIGH", "category": "vulnerability", "type": "PACKAGE_VULNERABILITY",
            "control_id": "CVE-2024-1", "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {}},
            "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "priority": "P2", "signals": {}, "context": {}}


def commit_finding(cache, raw, committer) -> None:
    payload = finding(1)
    page = raw.put_json({"Findings": [1]}, scope=SCOPE, operation="ListFindings", observed_at=NOW)
    digest = contracts.payload_hash(payload)
    event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, digest), kind="observation",
        installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=digest, raw_ref=page.ref)
    run = {"run_id": "run-1", "started_at": NOW, "completed_at": NOW, "status": "complete",
           "accounts": ["111122223333"], "regions": ["us-east-1"], "sources": ["inspector"],
           "findings_count": 1, "issues_count": 1, "truncated": False}
    run_event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, contracts.payload_hash(run), "scan_run"),
        kind="scan_run", installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(run), raw_ref=page.ref)
    cov = {"run_id": "run-1", "account_id": "111122223333", "region": "us-east-1", "source": "inspector",
           "status": "ok", "count": 1, "total": 1, "truncated": False, "completeness": "ok"}
    cov_event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, contracts.payload_hash(cov), "coverage"),
        kind="coverage", installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(cov), raw_ref=page.ref)
    cache.stage_facts([(run_event, run), (cov_event, cov), (event, payload)])
    assert committer.commit_pending().status == "committed"


def scan_payload() -> dict:
    return {"findings": [finding(1)], "issues": [{"issue_key": "issue-1", "finding_keys": ["key1"], "top_key": "key1"}],
            "fixes": []}


def test_intact_disk_is_healthy_and_keeps_the_watermark(tmp_path):
    cache, raw, store, committer, state = setup(tmp_path)
    commit_finding(cache, raw, committer)
    state.refresh_from_scan(scan_payload(), {}, cache.watermark())
    report = recovery.Recovery(cache, store, state, committer, raw).recover()
    assert report.state == "healthy" and report.watermark.sequence == 1
    assert report.outbox_events == 0 and report.needs_scan is False
    health = report.health(raw_backlog={"objects": 0}, checkpoint_age_seconds=42)
    assert health["installation_id"] == cache.installation_id()
    assert health["checkpoint_age_seconds"] == 42


def test_empty_disk_rebuilds_from_current_tables_and_starts_a_new_epoch(tmp_path):
    cache, raw, store, committer, state = setup(tmp_path)
    commit_finding(cache, raw, committer)
    state.refresh_from_scan(scan_payload(), {}, cache.watermark())
    old_id, old_epoch = cache.installation_id(), cache.epoch()
    path = cache.path
    cache.close()
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)

    fresh = cache_module.Cache(path, timeout=1)
    fresh_state = current.CurrentState(store, fresh)
    report = recovery.Recovery(fresh, store, fresh_state, commit.Committer(fresh, raw, store), raw).recover(
        empty_disk=True, installation_id=old_id, namespace="remedigenius")
    assert report.state == "recovering" and report.rebuilt["current_findings"] == 1
    assert report.needs_scan is True
    assert fresh.installation_id() == old_id and fresh.epoch() != old_epoch
    view = fresh.get_view("current_findings")
    assert view["payload"]["findings"][0]["key"] == "key1"
    assert view["watermark"]["sequence"] == 1


def test_wrong_installation_or_missing_storage_is_blocked(tmp_path):
    cache, raw, store, committer, state = setup(tmp_path)
    commit_finding(cache, raw, committer)
    other = contracts.Watermark("installation-other", "remedigenius", "epoch-x", 1, NOW, snapshot_id=1)
    state.refresh_from_scan(scan_payload(), {}, other)
    blocked = recovery.Recovery(cache, store, state, committer, raw).recover()
    assert blocked.state == "blocked" and "installation" in blocked.reason

    down = recovery.Recovery(cache, FailingStorage(), state, committer, raw).recover()
    assert down.state == "blocked" and "storage is not ready" in down.reason


def test_recovery_drains_the_outbox(tmp_path):
    cache, raw, store, committer, state = setup(tmp_path)
    commit_finding(cache, raw, committer)
    state.refresh_from_scan(scan_payload(), {}, cache.watermark())
    payload = {"finding_key": "key1", "status": "acknowledged", "reason": "seen", "by": "owner", "decided_at": NOW}
    event = contracts.Event(event_id=contracts.operation_event_id(), kind="decision",
                            installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0,
                            scope=contracts.Scope(account="111122223333", region="us-east-1", source="desk"),
                            observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(payload))
    cache.stage_event(event, payload)
    report = recovery.Recovery(cache, store, state, committer, raw).recover()
    assert report.outbox_events == 0
    assert cache.pending_count() == 0
    assert len(store.scan_rows("decisions")) == 1


def test_a_merged_pr_is_reconciled_without_a_numbered_follow_up(tmp_path):
    cache, raw, store, committer, state = setup(tmp_path)
    commit_finding(cache, raw, committer)
    intent = {"operation_id": "op-1", "finding_key": "key1", "repo": "owner/repo", "base_branch": "dev",
              "branch": "feature/remedigenius/key1", "proposal_digest": "abc", "at": NOW}
    event = contracts.Event(event_id=contracts.operation_event_id(), kind="github_intent",
                            installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
                            observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(intent))
    assert committer.begin_github(event, intent).durable
    state.refresh_operations(cache.watermark())
    manager = recovery.Recovery(cache, store, state, committer, raw)
    before = manager.recover()
    assert before.unresolved_operations == 1 and before.state == "degraded"

    calls = []

    def reconcile(operation):
        calls.append(operation["operation_id"])
        return {"found": True, "state": "merged", "number": 7}

    result = manager.reconcile_operations(reconcile)
    assert calls == ["op-1"]
    assert result["resolved"][0]["state"] == "merged"
    rows = store.scan_rows("github_ops")
    assert len(rows) == 2 and {row["phase"] for row in rows} == {"intent", "result"}
    assert all("-r2" not in str(row.get("branch") or "") for row in rows)
    assert state._open_operations(cache.watermark().as_dict(), datetime.now(timezone.utc)) == []