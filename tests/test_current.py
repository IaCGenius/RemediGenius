"""Current-state tables and cache rebuild (roadmap CE-10)."""
from __future__ import annotations

from datetime import datetime, timezone

from rgtriage import cache as cache_module
from rgtriage import contracts, current, iceberg_store, ocsf

NOW = "2026-06-15T10:00:00Z"


def setup(tmp_path):
    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = iceberg_store.IcebergStore.open(profile)
    store.ensure_tables()
    return store, cache_module.Cache(tmp_path / "desk.sqlite3", timeout=1)


def mark(sequence: int = 5) -> contracts.Watermark:
    return contracts.Watermark("installation-1", "remedigenius", "epoch-1", sequence, NOW, snapshot_id=100 + sequence)


def finding(n: int) -> dict:
    return {"key": f"key{n}", "source": "inspector", "native_id": f"n{n}", "product": "Inspector",
            "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}", "severity": "HIGH",
            "category": "vulnerability", "type": "PACKAGE_VULNERABILITY", "control_id": "CVE-2024-1",
            "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {"env": "prod"}},
            "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "priority": "P2", "signals": {}, "context": {}}


def scan() -> dict:
    return {"findings": [finding(1), finding(2)],
            "issues": [{"issue_key": "issue-1", "finding_keys": ["key1", "key2"], "top_key": "key1"}],
            "fixes": [{"key": "key1", "state": "deployed", "owner": "team", "pr": "https://example/pull/1",
                       "proof": {"service": "s3", "operation": "get"}, "last_check": {"passed": True},
                       "changed_at": NOW}]}


def github_ops(store):
    store.overwrite_rows("github_ops", [
        {"event_id": "op-1", "installation_id": "installation-1", "epoch": "epoch-1", "sequence": 1,
         "operation_id": "op-1", "phase": "intent", "finding_key": "key1", "repo": "owner/repo",
         "base_branch": "dev", "branch": "feature/x", "proposal_digest": "abc", "pr_number": None,
         "state": None, "at": datetime.now(timezone.utc), "error": None, "raw_sha256": "",
         "observed_at": datetime.now(timezone.utc), "ingested_at": datetime.now(timezone.utc)},
        {"event_id": "op-2", "installation_id": "installation-1", "epoch": "epoch-1", "sequence": 2,
         "operation_id": "op-2", "phase": "intent", "finding_key": "key2", "repo": "owner/repo",
         "base_branch": "dev", "branch": "feature/y", "proposal_digest": "def", "pr_number": None,
         "state": None, "at": datetime.now(timezone.utc), "error": None, "raw_sha256": "",
         "observed_at": datetime.now(timezone.utc), "ingested_at": datetime.now(timezone.utc)},
        {"event_id": "op-2-result", "installation_id": "installation-1", "epoch": "epoch-1", "sequence": 3,
         "operation_id": "op-2", "phase": "result", "finding_key": "key2", "repo": "owner/repo",
         "base_branch": "dev", "branch": "feature/y", "proposal_digest": "def", "pr_number": 7,
         "state": "open", "at": datetime.now(timezone.utc), "error": None, "raw_sha256": "",
         "observed_at": datetime.now(timezone.utc), "ingested_at": datetime.now(timezone.utc)},
    ])


def decisions() -> dict:
    return {"key1": {"status": "fixing", "reason": "we are on it", "by": "owner", "at": NOW}}


def test_refresh_writes_current_tables_and_rebuilds_the_cache(tmp_path):
    store, cache = setup(tmp_path)
    github_ops(store)
    state = current.CurrentState(store, cache)
    counts = state.refresh_from_scan(scan(), decisions(), mark())
    assert counts == {"current_findings": 2, "current_fixes": 1, "current_decisions": 1, "current_operations": 1}
    rows = store.scan_rows("current_findings")
    assert {row["finding_key"] for row in rows} == {"key1", "key2"}
    assert rows[0]["watermark"]["sequence"] == 5
    assert rows[0]["issue_key"] == "issue-1"
    assert store.scan_rows("current_operations")[0]["operation_id"] == "op-1"

    rebuilt = state.rebuild_cache()
    assert rebuilt["current_findings"] == 2 and rebuilt["watermark"]["sequence"] == 5
    view = cache.get_view("current_findings")
    assert {row["key"] for row in view["payload"]["findings"]} == {"key1", "key2"}
    assert view["watermark"]["snapshot_id"] == 105
    assert len(cache.get_view("current_fixes")["payload"]) == 1
    assert cache.get_view("current_decisions")["payload"][0]["status"] == "fixing"


def test_an_empty_scan_clears_the_current_tables(tmp_path):
    store, cache = setup(tmp_path)
    state = current.CurrentState(store, cache)
    state.refresh_from_scan(scan(), decisions(), mark())
    assert store.scan_rows("current_findings")
    state.refresh_from_scan({"findings": [], "issues": [], "fixes": []}, {}, mark(6))
    assert store.scan_rows("current_findings") == []
    rebuilt = state.rebuild_cache(mark(6))
    assert rebuilt["current_findings"] == 0
    assert cache.get_view("current_findings")["payload"]["findings"] == []


def test_rebuild_uses_the_current_table_not_a_newer_unrefreshed_event(tmp_path):
    store, cache = setup(tmp_path)
    state = current.CurrentState(store, cache)
    state.refresh_from_scan(scan(), decisions(), mark())
    # A newer finding exists in the event table but the current table was not refreshed before the crash.
    scope = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
    payload = contracts.payload_hash({"n": 3})
    event = contracts.Event(
        event_id=contracts.observation_event_id("installation-1", scope, NOW, payload), kind="observation",
        installation_id="installation-1", epoch="epoch-1", sequence=9, scope=scope, observed_at=NOW,
        ingested_at=NOW, payload_hash=payload)
    body = b"{}"
    sha = contracts.bytes_sha256(body)
    ref = contracts.RawRef(sha256=sha, key=contracts.raw_key(scope, NOW, sha), size=len(body), scope=scope,
                           operation="ListFindings", observed_at=NOW)
    store.append_rows("findings", [ocsf.finding_row(finding(3), event, ref)], batch_id="batch_" + "9" * 32)
    assert len(store.scan_rows("findings")) == 1
    rebuilt = state.rebuild_cache()
    assert rebuilt["current_findings"] == 2  # current table, not the unrefreshed event
    assert {row["key"] for row in cache.get_view("current_findings")["payload"]["findings"]} == {"key1", "key2"}