"""The commit loop: raw-before-facts, idempotent batches, durable decisions and intents (CE-13)."""
from __future__ import annotations

import os

import pytest

from rgtriage import cache as cache_module
from rgtriage import commit, contracts, iceberg_store, ocsf, rawstore

NOW = "2026-06-15T10:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")


class FailingStorage:
    def ensure_tables(self):
        raise iceberg_store.IcebergUnavailable("Glue is unreachable")

    def batch_in_history(self, name, batch_id):
        raise iceberg_store.IcebergUnavailable("Glue is unreachable")

    def append_many(self, rows, *, batch_id="", content_hash=""):
        raise iceberg_store.IcebergUnavailable("Glue is unreachable")


def setup(tmp_path, storage=None):
    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = storage or iceberg_store.IcebergStore.open(profile)
    cache = cache_module.Cache(tmp_path / "desk.sqlite3", timeout=1)
    raw = rawstore.RawStore(rawstore.FolderBackend(tmp_path / "raw"), buffer=None)
    return cache, raw, store, commit.Committer(cache, raw, store)


def finding(n: int = 1) -> dict:
    return {
        "key": f"key{n}", "source": "inspector", "native_id": f"native-{n}", "product": "Inspector",
        "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}", "description": "d",
        "severity": "HIGH", "category": "vulnerability", "type": "PACKAGE_VULNERABILITY",
        "control_id": "CVE-2024-1234", "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {}},
        "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "remediation": {}, "console_url": "",
        "signals": {}, "context": {}, "priority": "P2", "reasons": ["severity HIGH"],
    }


def observation(cache, raw, n: int = 1, *, page=None) -> tuple[contracts.Event, dict]:
    payload = finding(n)
    put = raw.put_json(page or {"Findings": [n]}, scope=SCOPE, operation="ListFindings", observed_at=NOW)
    digest = contracts.payload_hash(payload)
    event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, digest), kind="observation",
        installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=digest, raw_ref=put.ref)
    return event, payload


def operation(cache, kind: str, payload: dict) -> contracts.Event:
    return contracts.Event(
        event_id=contracts.operation_event_id(), kind=kind, installation_id=cache.installation_id(),
        epoch=cache.epoch(), sequence=0, scope=contracts.Scope(account="111122223333", region="us-east-1",
                                                               source="desk"),
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(payload))


def test_observation_commits_rows_and_the_current_view(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    event, payload = observation(cache, raw)
    cache.stage_facts([(event, payload)], views={"board": {"findings": 1}})
    result = committer.commit_pending()
    assert result.status == "committed" and result.durable
    assert result.events == 1 and result.tables == {"findings": "appended"}
    assert len(store.scan_rows("findings")) == 1
    assert store.batch_in_history("findings", result.batch_id)
    assert store.snapshot_for_batch("findings", result.batch_id) == result.snapshot_id
    assert cache.pending_count() == 0
    assert cache.get_view("board")["watermark"]["snapshot_id"] == result.snapshot_id
    assert cache.watermark().sequence == 1


def test_lost_acknowledgement_does_not_duplicate_the_batch(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    event, payload = observation(cache, raw)
    cache.stage_facts([(event, payload)])
    first = committer.commit_pending(ack=False)
    assert first.status == "committed-not-acked"
    assert len(store.scan_rows("findings")) == 1
    assert cache.pending_count() == 1
    second = committer.commit_pending()
    assert second.status == "committed" and second.batch_id == first.batch_id
    assert len(store.scan_rows("findings")) == 1
    assert cache.pending_count() == 0


def test_raw_must_be_confirmed_before_any_fact(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    event, payload = observation(cache, raw)
    raw.backend.delete(event.raw_ref.key)
    cache.stage_facts([(event, payload)])
    result = committer.commit_pending()
    assert result.status == "blocked-raw"
    assert result.raw_problems and result.raw_problems[0]["sha256"] == event.raw_ref.sha256
    assert store.scan_rows("findings") == []
    assert cache.pending_count() == 1


def test_decision_is_durable_only_after_the_iceberg_commit(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    payload = {"finding_key": "key1", "status": "acknowledged", "reason": "we know", "by": "owner", "decided_at": NOW}
    result = committer.commit_decision(operation(cache, "decision", payload), payload)
    assert result.durable
    decisions = store.scan_rows("decisions")
    assert len(decisions) == 1 and decisions[0]["finding_key"] == "key1" and decisions[0]["by"] == "owner"
    assert cache.undurable_decisions() == 0


def test_decision_reports_not_durable_when_storage_is_down_and_retries(tmp_path):
    cache, raw, store, _ = setup(tmp_path)
    broken = commit.Committer(cache, raw, FailingStorage())
    payload = {"finding_key": "key1", "status": "acknowledged", "reason": "we know", "by": "owner", "decided_at": NOW}
    event = operation(cache, "decision", payload)
    result = broken.commit_decision(event, payload)
    assert not result.durable and result.status == "not-durable"
    assert cache.undurable_decisions() == 1
    assert cache.health()["undurable_decisions"] == 1
    recovered = commit.Committer(cache, raw, store)
    assert recovered.commit_pending(kinds=("decision",)).status == "committed"
    assert cache.undurable_decisions() == 0
    assert len(store.scan_rows("decisions")) == 1


def test_github_intent_commits_before_the_call_and_the_result_after(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    intent = {"operation_id": "op-1", "finding_key": "key1", "repo": "owner/repo", "base_branch": "dev",
              "branch": "feature/remedigenius/key1", "proposal_digest": "abc", "at": NOW}
    started = committer.begin_github(operation(cache, "github_intent", intent), intent)
    assert started.durable
    rows = store.scan_rows("github_ops")
    assert len(rows) == 1 and rows[0]["phase"] == "intent" and rows[0]["state"] is None
    result = {**intent, "phase": "result", "pr_number": 7, "state": "open"}
    finished = committer.finish_github(operation(cache, "github_result", result), result)
    assert finished.durable
    rows = store.scan_rows("github_ops")
    assert len(rows) == 2 and {row["phase"] for row in rows} == {"intent", "result"}


def test_no_github_call_without_a_committed_intent(tmp_path):
    cache, raw, store, _ = setup(tmp_path)
    broken = commit.Committer(cache, raw, FailingStorage())
    intent = {"operation_id": "op-2", "finding_key": "key1", "repo": "owner/repo", "branch": "b", "at": NOW}
    result = broken.begin_github(operation(cache, "github_intent", intent), intent)
    assert not result.durable
    assert cache.pending_count(kinds=("github_intent",)) == 1


def test_scan_run_and_coverage_rows(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    page = raw.put_json({"coverage": []}, scope=SCOPE, operation="ListFindings", observed_at=NOW)
    run_payload = {"run_id": "run-1", "started_at": NOW, "completed_at": NOW, "status": "complete",
                   "accounts": ["111122223333"], "regions": ["us-east-1"], "sources": ["inspector"],
                   "findings_count": 1, "issues_count": 1, "truncated": False}
    run_event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, contracts.payload_hash(run_payload), "scan_run"),
        kind="scan_run", installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(run_payload), raw_ref=page.ref)
    cov_payload = {"run_id": "run-1", "account_id": "111122223333", "region": "us-east-1", "source": "inspector",
                   "status": "ok", "count": 1, "total": 1, "truncated": False, "completeness": "ok"}
    cov_event = contracts.Event(
        event_id=contracts.observation_event_id(cache.installation_id(), SCOPE, NOW, contracts.payload_hash(cov_payload), "coverage"),
        kind="coverage", installation_id=cache.installation_id(), epoch=cache.epoch(), sequence=0, scope=SCOPE,
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(cov_payload), raw_ref=page.ref)
    obs_event, obs_payload = observation(cache, raw)
    cache.stage_facts([(run_event, run_payload), (cov_event, cov_payload), (obs_event, obs_payload)])
    result = committer.commit_pending()
    assert result.status == "committed"
    assert set(result.tables) == {"scan_runs", "coverage", "findings"}
    assert store.scan_rows("scan_runs")[0]["run_id"] == "run-1"
    assert store.scan_rows("coverage")[0]["completeness"] == "ok"


def test_conflicting_event_id_is_quarantined_and_not_committed(tmp_path):
    cache, raw, store, committer = setup(tmp_path)
    event, payload = observation(cache, raw)
    cache.stage_event(event, payload)
    from dataclasses import replace

    conflict = replace(event, payload_hash="f" * 64)
    cache.stage_event(conflict, payload)
    assert cache.conflicts()
    result = committer.commit_pending()
    assert result.status in ("empty", "committed")
    assert store.scan_rows("findings") == []


@pytest.mark.skipif(not os.environ.get("RGTRIAGE_AWS_STORAGE_TEST"),
                    reason="set RGTRIAGE_AWS_STORAGE_TEST=1 after creating a disposable Glue database and S3 warehouse")
def test_aws_profile_round_trip_is_real_when_enabled(tmp_path):
    """Not cloud validation unless this is explicitly run against a disposable stack."""
    from rgtriage import config

    store = iceberg_store.from_env(config.load())
    store.ensure_tables()
    assert store.profile.kind == "aws"