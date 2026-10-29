"""Crash, rebuild and outage proofs on a real local Iceberg catalog (roadmap CE-15).

These are on-disk tests against the local profile. They are not a claim about AWS: the optional AWS profile test is
skipped unless RGTRIAGE_AWS_STORAGE_TEST is set and a disposable Glue database and warehouse are configured.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from rgtriage import cache as cache_module
from rgtriage import commit, contracts, current, health, iceberg_store, rawstore, recovery, repository

NOW = "2026-06-15T10:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    profile = {"name": "desk", "regions": ["us-east-1"],
               "storage": {"profile": "local", "namespace": "remedigenius", "installation_id": "installation-test"}}
    storage_profile = contracts.StorageProfile(kind="local", namespace="remedigenius",
                                               warehouse=str(tmp_path / "warehouse"), catalog="sql",
                                               catalog_uri=str(tmp_path / "catalog.db"))
    storage = iceberg_store.IcebergStore.open(storage_profile)
    storage.ensure_tables()
    cache_path = tmp_path / "cache" / "desk.sqlite3"
    cache = cache_module.Cache(cache_path, timeout=1)
    cache.set_identity("installation-test", "remedigenius", epoch="epoch-1")
    raw = rawstore.RawStore(rawstore.FolderBackend(tmp_path / "raw"))
    repo = repository.Repository(cache, raw, storage, profile, storage_profile, cache_existed=True)
    return repo, storage, cache, raw, storage_profile, cache_path


def finding(n: int = 1) -> dict:
    return {"key": f"key{n}", "source": "inspector", "native_id": f"n{n}", "product": "Inspector",
            "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}", "description": "d",
            "severity": "HIGH", "category": "vulnerability", "type": "PACKAGE_VULNERABILITY",
            "control_id": "CVE-2024-1", "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {}},
            "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "priority": "P2", "signals": {}, "context": {}}


def scan(n: int = 1, at: str = NOW) -> dict:
    item = finding(n)
    return {"version": "0.5.0", "scanned_at": at, "findings": [item],
            "issues": [{"issue_key": f"issue-{n}", "finding_keys": [item["key"]], "top_key": item["key"]}],
            "coverage": [{"source": "inspector", "account": "desk", "account_id": "111122223333",
                          "region": "us-east-1", "status": "ok", "count": 1, "total": 1, "truncated": False,
                          "completeness": "ok"}],
            "fixes": [], "changes": {"new": 0}}


def test_committed_scan_and_decision_survive_deleting_the_cache(tmp_path, monkeypatch):
    repo, storage, cache, raw, storage_profile, path = setup(tmp_path, monkeypatch)
    repo.save_scan(scan(1))
    repo.decide("key1", "fixing", "on it", by="owner")
    installation = cache.installation_id()
    cache.close()
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)

    fresh = cache_module.Cache(path, timeout=1)
    fresh_repo = repository.Repository(fresh, raw, storage, repo.profile, storage_profile, cache_existed=False)
    report = fresh_repo.recover(empty_disk=True, installation_id=installation)
    assert report.state in ("recovering", "healthy")
    assert len(storage.scan_rows("current_findings")) == 1
    assert len(storage.scan_rows("current_decisions")) == 1
    rebuilt = fresh_repo.load_latest()
    assert rebuilt["findings"][0]["key"] == "key1"
    assert fresh_repo.load_decisions()["key1"]["status"] == "fixing"


def test_an_uncommitted_scan_is_reported_as_needing_a_rerun(tmp_path, monkeypatch):
    repo, storage, cache, raw, storage_profile, path = setup(tmp_path, monkeypatch)
    payload = finding(1)
    page = raw.put_json({"Findings": []}, scope=SCOPE, operation="ListFindings", observed_at=NOW)
    event = contracts.Event(event_id=contracts.observation_event_id("installation-test", SCOPE, NOW,
                                                                     contracts.payload_hash(payload)),
                            kind="observation", installation_id="installation-test", epoch="epoch-1", sequence=0,
                            scope=SCOPE, observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(payload),
                            raw_ref=page.ref)
    cache.stage_facts([(event, payload)])
    assert cache.pending_count() == 1
    assert storage.scan_rows("current_findings") == []
    cache.close()
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    fresh = cache_module.Cache(path, timeout=1)
    fresh_repo = repository.Repository(fresh, raw, storage, repo.profile, storage_profile, cache_existed=False)
    report = fresh_repo.recover(empty_disk=True, installation_id="installation-test")
    assert report.needs_scan is True
    assert storage.scan_rows("current_findings") == []


def test_a_commit_without_acknowledgement_is_not_duplicated(tmp_path, monkeypatch):
    repo, storage, cache, raw, storage_profile, path = setup(tmp_path, monkeypatch)
    repo.save_scan(scan(1))
    payload = finding(2)
    page = raw.put_json({"Findings": []}, scope=SCOPE, operation="ListFindings", observed_at=NOW)
    event = contracts.Event(event_id=contracts.observation_event_id("installation-test", SCOPE, NOW,
                                                                     contracts.payload_hash(payload)),
                            kind="observation", installation_id="installation-test", epoch="epoch-1", sequence=0,
                            scope=SCOPE, observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash(payload),
                            raw_ref=page.ref)
    cache.stage_facts([(event, payload)])
    first = repo.committer.commit_pending(ack=False)
    assert first.status == "committed-not-acked"
    assert len(storage.scan_rows("findings")) == 2
    report = repo.recover()
    assert report.state in ("healthy", "degraded")
    assert len(storage.scan_rows("findings")) == 2  # no duplicate
    assert cache.pending_count() == 0


def test_maintenance_during_commits_keeps_every_row(tmp_path, monkeypatch):
    repo, storage, cache, raw, storage_profile, path = setup(tmp_path, monkeypatch)
    repo.save_scan(scan(1))
    before = len(storage.scan_rows("findings"))
    maintenance = storage.maintenance()
    assert maintenance["at"]
    repo.save_scan(scan(2, at="2026-06-15T11:00:00Z"))
    assert len(storage.scan_rows("findings")) == before + 1


def test_health_names_the_state_and_every_contract_field(tmp_path, monkeypatch):
    repo, storage, cache, raw, storage_profile, path = setup(tmp_path, monkeypatch)
    repo.save_scan(scan(1))
    value = health.snapshot(repo, checkpoint_age_seconds=12)
    assert value["state"] == "healthy"
    assert value["outbox_events"] == 0 and value["unresolved_operations"] == 0
    assert health.fields_ok(value) == []
    cache.stage_event(contracts.Event(
        event_id=contracts.operation_event_id(), kind="decision", installation_id="installation-test",
        epoch="epoch-1", sequence=0, scope=contracts.Scope(account="", region="", source="desk"),
        observed_at=NOW, ingested_at=NOW, payload_hash=contracts.payload_hash({"x": 1})), {"x": 1})
    assert health.snapshot(repo)["state"] == "degraded"


class DownStorage:
    def scan_rows(self, *args, **kwargs):
        raise RuntimeError("Glue is unreachable")


def test_an_unreachable_store_is_blocked_not_healthy(tmp_path, monkeypatch):
    repo, storage, cache, raw, storage_profile, path = setup(tmp_path, monkeypatch)
    repo.save_scan(scan(1))
    repo.storage = DownStorage()
    value = health.snapshot(repo)
    assert value["state"] == "blocked" and "unreachable" in value["reason"]


@pytest.mark.skipif(not os.environ.get("RGTRIAGE_AWS_STORAGE_TEST"),
                    reason="set RGTRIAGE_AWS_STORAGE_TEST=1 with a disposable Glue database and warehouse")
def test_optional_aws_profile_is_a_real_run_only_when_enabled(tmp_path):
    from rgtriage import config

    store = iceberg_store.from_env(config.load())
    store.ensure_tables()
    assert store.profile.kind == "aws"