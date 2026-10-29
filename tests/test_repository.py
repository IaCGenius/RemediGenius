"""The durable repository used by scan and decision commands (roadmap CE-09)."""
from __future__ import annotations

import json

import pytest

from rgtriage import cache as cache_module
from rgtriage import collection, commit, contracts, current, iceberg_store, rawstore, repository, store

NOW = "2026-06-15T10:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    profile = {"name": "desk", "storage": {"profile": "local", "namespace": "remedigenius"}}
    storage_profile = contracts.StorageProfile(kind="local", namespace="remedigenius",
                                               warehouse=str(tmp_path / "warehouse"), catalog="sql",
                                               catalog_uri=str(tmp_path / "catalog.db"))
    store_obj = iceberg_store.IcebergStore.open(storage_profile)
    store_obj.ensure_tables()
    cache = cache_module.Cache(tmp_path / "cache" / "desk.sqlite3", timeout=1)
    raw = rawstore.RawStore(rawstore.FolderBackend(tmp_path / "raw"))
    repo = repository.Repository(cache, raw, store_obj, profile, storage_profile)
    return repo, store_obj, cache, raw


def finding(n: int = 1) -> dict:
    return {"key": f"key{n}", "source": "inspector", "native_id": f"n{n}", "product": "Inspector",
            "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}", "description": "d",
            "severity": "HIGH", "category": "vulnerability", "type": "PACKAGE_VULNERABILITY",
            "control_id": "CVE-2024-1", "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {}},
            "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "priority": "P2", "signals": {}, "context": {}}


def scan_payload() -> dict:
    return {"version": "0.5.0", "scanned_at": NOW, "findings": [finding(1)],
            "issues": [{"issue_key": "issue-1", "finding_keys": ["key1"], "top_key": "key1"}],
            "coverage": [{"source": "inspector", "account": "desk", "account_id": "111122223333",
                          "region": "us-east-1", "status": "ok", "count": 1, "total": 1, "truncated": False,
                          "completeness": "ok"}],
            "fixes": [], "changes": {"new": 0}, "knowledge": {}, "onboarding": {}, "footprint": {}}


def test_save_scan_commits_facts_and_never_writes_the_retired_json(tmp_path, monkeypatch):
    repo, iceberg, cache, raw = setup(tmp_path, monkeypatch)
    result = repo.save_scan(scan_payload())
    assert result["status"] == "committed"
    assert len(iceberg.scan_rows("findings")) == 1
    assert len(iceberg.scan_rows("scan_runs")) == 1
    assert len(iceberg.scan_rows("coverage")) == 1
    assert len(iceberg.scan_rows("current_findings")) == 1
    assert cache.get_view("latest_scan")["payload"]["findings"][0]["key"] == "key1"
    assert cache.watermark().sequence == 1
    assert not (tmp_path / "latest.json").exists()
    assert not (tmp_path / "decisions.json").exists()
    assert not (tmp_path / "history").exists()


def test_save_scan_links_the_collection_result_as_raw_evidence(tmp_path, monkeypatch):
    repo, iceberg, cache, raw = setup(tmp_path, monkeypatch)
    run = collection.CollectionRun(cache, raw, "scan-test")
    scope = run.scope({"name": "desk", "account_id": "111122223333"}, "us-east-1", "inspector")
    run.begin_scope(scope)
    ref = run.record_result(scope, [finding(1)], {"truncated": False})
    run.complete_scope(scope, count=1)
    payload = scan_payload()
    payload["findings"][0]["collected_from"] = ["inspector", "111122223333", "us-east-1"]
    repo.save_scan(payload, run)
    row = iceberg.scan_rows("findings")[0]
    assert row["raw_sha256"] == ref.sha256
    assert row["raw_key"] == ref.key


def test_decisions_are_committed_and_visible_in_the_current_view(tmp_path, monkeypatch):
    repo, iceberg, cache, raw = setup(tmp_path, monkeypatch)
    repo.save_scan(scan_payload())
    decision = repo.decide("key1", "fixing", "we are on it", by="owner")
    assert decision["status"] == "fixing"
    assert len(iceberg.scan_rows("decisions")) == 1
    assert repo.load_decisions()["key1"]["status"] == "fixing"
    assert cache.get_view("current_decisions")["payload"][0]["status"] == "fixing"
    assert not (tmp_path / "decisions.json").exists()


def test_legacy_json_is_refused_on_a_fresh_cache(tmp_path, monkeypatch):
    repo, iceberg, cache, raw = setup(tmp_path, monkeypatch)
    store.latest_path().write_text("{}", encoding="utf-8")
    with pytest.raises(repository.LegacyState) as exc:
        repo.refuse_legacy_state()
    assert "fresh-install" in str(exc.value)
    repo.save_scan(scan_payload())
    repo.refuse_legacy_state()  # a durable install never imports the stray file


def test_onboarding_survives_in_the_cache(tmp_path, monkeypatch):
    repo, iceberg, cache, raw = setup(tmp_path, monkeypatch)
    assert repo.load_onboarding() is None
    repo.save_onboarding({"mode": "organization"}, {"accounts": [{"account_id": "111122223333", "name": "desk",
                                                                 "discovered": True}]})
    assert repo.load_onboarding()["readable"] == {"111122223333": "desk"}