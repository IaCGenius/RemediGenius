"""Scoped current/history queries and evidence resolution (roadmap CE-14)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from rgtriage import cache as cache_module
from rgtriage import commit, contracts, iceberg_store, queries, rawstore

NOW = "2026-06-15T10:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")


def setup(tmp_path):
    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = iceberg_store.IcebergStore.open(profile)
    cache = cache_module.Cache(tmp_path / "desk.sqlite3", timeout=1)
    raw = rawstore.RawStore(rawstore.FolderBackend(tmp_path / "raw"))
    committer = commit.Committer(cache, raw, store)
    return cache, raw, store, committer


def finding(n: int) -> dict:
    return {"key": f"key{n}", "source": "inspector", "native_id": f"native-{n}", "product": "Inspector",
            "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}", "description": "d",
            "severity": "HIGH", "category": "vulnerability", "type": "PACKAGE_VULNERABILITY",
            "control_id": "CVE-2024-1234", "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {}},
            "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "remediation": {}, "console_url": "",
            "signals": {}, "context": {}, "priority": "P2", "reasons": ["severity HIGH"]}


def commit_batch(cache, raw, committer, n: int, *, run_id: str, truncated: bool = False) -> contracts.RawRef:
    payload = finding(n)
    page = raw.put_json({"Findings": [n]}, scope=SCOPE, operation="ListFindings", observed_at=NOW)
    digest = contracts.payload_hash(payload)
    event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, digest), kind="observation",
        installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=digest, raw_ref=page.ref)
    run = {"run_id": run_id, "started_at": NOW, "completed_at": NOW, "status": "complete",
           "accounts": ["111122223333"], "regions": ["us-east-1"], "sources": ["inspector"],
           "findings_count": 1, "issues_count": 1, "truncated": False}
    run_event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, contracts.payload_hash(run), "scan_run"),
        kind="scan_run", installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(run), raw_ref=page.ref)
    cov = {"run_id": run_id, "account_id": "111122223333", "region": "us-east-1", "source": "inspector",
           "status": "ok", "count": 1, "total": 1, "truncated": truncated,
           "completeness": "partial" if truncated else "ok"}
    cov_event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, contracts.payload_hash(cov), "coverage"),
        kind="coverage", installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(cov), raw_ref=page.ref)
    cache.stage_facts([(run_event, run), (cov_event, cov), (event, payload)],
                      views={"current_findings": {"findings": [payload]}})
    result = committer.commit_pending()
    assert result.status == "committed", result.error
    return page.ref


def test_current_labels_durability_and_filters(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    commit_batch(cache, raw, committer, 1, run_id="run-1")
    service = queries.QueryService(cache, store, raw)
    result = service.current()
    assert result["query"] == "current"
    assert result["count"] == 1 and result["rows"][0]["key"] == "key1"
    assert result["durability"]["watermark"]["sequence"] == 1
    assert result["durability"]["outbox_events"] == 0
    assert result["view_watermark"]["snapshot_id"] is not None
    assert service.current(account="999999999999")["count"] == 0
    # a staged decision is enough to show the not-durable label without faking a raw object
    decision_payload = {"finding_key": "key1", "status": "acknowledged", "reason": "r", "by": "owner",
                        "decided_at": NOW}
    decision = contracts.Event(
        event_id=contracts.operation_event_id(), kind="decision", installation_id=cache.installation_id(),
        epoch=cache.epoch(), sequence=0, scope=SCOPE, observed_at=NOW, ingested_at=NOW,
        payload_hash=contracts.payload_hash(decision_payload))
    cache.stage_event(decision, decision_payload)
    assert service.current()["durability"]["undurable_decisions"] == 1


def test_history_latest_and_as_of_a_snapshot(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    commit_batch(cache, raw, committer, 1, run_id="run-1")
    first = store.snapshots("findings")[-1]
    time.sleep(0.01)  # make the second snapshot strictly later than the as-of cutoff
    commit_batch(cache, raw, committer, 2, run_id="run-2")
    service = queries.QueryService(cache, store, raw)
    latest = service.history()
    assert latest["count"] == 2 and latest["evidence_set_complete"] is True
    assert latest["manifest"]["run_id"] == "run-2"
    assert latest["uncommitted_rows_included"] is False
    when = datetime.fromtimestamp(first.timestamp_ms / 1000, tz=timezone.utc).isoformat()
    earlier = service.history(as_of=when)
    assert earlier["count"] == 1
    assert earlier["rows"][0]["ce"]["finding_key"] == "key1"
    assert earlier["manifest"]["run_id"] == "run-1"
    assert service.history(account="999999999999")["count"] == 0
    again = service.history(as_of=when)
    assert [row["event_id"] for row in again["rows"]] == [row["event_id"] for row in earlier["rows"]]


def test_incomplete_coverage_is_not_presented_as_a_complete_evidence_set(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    commit_batch(cache, raw, committer, 1, run_id="run-1", truncated=True)
    service = queries.QueryService(cache, store, raw)
    result = service.history()
    assert result["evidence_set_complete"] is False
    assert result["manifest"]["complete"] is False
    assert result["manifest"]["blind_spots"]


def test_evidence_ids_are_resolved_or_rejected_without_returning_bytes(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    ref = commit_batch(cache, raw, committer, 1, run_id="run-1")
    service = queries.QueryService(cache, store, raw)
    known = service.evidence(ref.sha256)
    assert known["exists"] and known["verified"] and known["key"] == ref.key
    assert "body" not in known and "bytes" not in known
    forged = service.evidence("a" * 64)
    assert forged["exists"] is False and forged["verified"] is False
    with pytest.raises(queries.QueryError):
        service.evidence("not-a-hash")


def test_dispatch_contract_rejects_unknown_and_extra_parameters(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    service = queries.QueryService(cache, store, raw)
    assert service.dispatch("campaign")["status"] == "unsupported"
    with pytest.raises(queries.QueryError):
        service.dispatch("not-a-handler")
    with pytest.raises(queries.QueryError):
        service.dispatch("history", {"sql": "select * from findings"})