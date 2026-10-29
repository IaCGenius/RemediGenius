"""Local Iceberg profile, batches and maintenance (roadmap CE-12)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rgtriage import contracts, iceberg_store, ocsf, schemas


def profile(tmp_path) -> contracts.StorageProfile:
    return contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                    catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))


def finding_row(n: int = 1) -> dict:
    finding = {
        "key": f"key{n}", "source": "inspector", "native_id": f"native-{n}", "product": "Inspector",
        "account": "111122223333", "region": "us-east-1", "title": f"Finding {n}",
        "description": "d", "severity": "HIGH", "category": "vulnerability", "type": "PACKAGE_VULNERABILITY",
        "control_id": "CVE-2024-1234", "resource": {"type": "AwsEc2Instance", "id": f"i-{n}", "name": f"i-{n}", "tags": {}},
        "first_seen": "2026-06-15T09:00:00Z", "last_seen": "2026-06-15T09:30:00Z", "workflow": "NEW",
        "remediation": {}, "console_url": "", "signals": {}, "context": {},
    }
    scope = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
    payload = contracts.payload_hash({"n": n})
    event = contracts.Event(
        event_id=contracts.observation_event_id("installation-1", scope, "2026-06-15T10:00:00Z", payload),
        kind="observation", installation_id="installation-1", epoch="epoch-1", sequence=n, scope=scope,
        observed_at="2026-06-15T10:00:00Z", ingested_at="2026-06-15T10:00:00Z", payload_hash=payload)
    body = b"{}"
    sha = contracts.bytes_sha256(body)
    ref = contracts.RawRef(sha256=sha, key=contracts.raw_key(scope, "2026-06-15T10:00:00Z", sha), size=len(body),
                           scope=scope, operation="ListFindings", observed_at="2026-06-15T10:00:00Z")
    return ocsf.finding_row(finding, event, ref)


def test_local_profile_creates_writes_reconnects_and_scans(tmp_path):
    store = iceberg_store.IcebergStore.open(profile(tmp_path))
    created = store.ensure_tables()
    assert set(created["created"]) == set(schemas.TABLES)
    assert store.append_rows("findings", [finding_row(1)], batch_id="batch_" + "a" * 32, content_hash="h") == "appended"
    assert store.append_rows("findings", [finding_row(2)], batch_id="batch_" + "b" * 32) == "appended"
    assert store.batch_in_history("findings", "batch_" + "a" * 32) is True
    assert store.batch_in_history("findings", "batch_" + "c" * 32) is False
    assert store.append_rows("findings", [finding_row(1)], batch_id="batch_" + "a" * 32) == "already-committed"
    assert len(store.scan_rows("findings")) == 2

    reopened = iceberg_store.IcebergStore.open(profile(tmp_path))
    reopened.ensure_tables()
    assert len(reopened.scan_rows("findings")) == 2
    assert reopened.batch_in_history("findings", "batch_" + "b" * 32) is True
    assert reopened.last_batch("findings") == "batch_" + "b" * 32


def test_append_many_and_snapshot_history(tmp_path):
    store = iceberg_store.IcebergStore.open(profile(tmp_path))
    store.ensure_tables()
    batch = "batch_" + "d" * 32
    result = store.append_many({"findings": [finding_row(1)], "coverage": [], "scan_runs": []}, batch_id=batch)
    assert result == {"findings": "appended"}
    assert store.batch_in_history("findings", batch)
    assert store.status()["tables"]["findings"]["snapshots"] == 1


def test_maintenance_compacts_small_files_and_keeps_recent_snapshots(tmp_path):
    store = iceberg_store.IcebergStore.open(
        profile(tmp_path), maintenance={"target_file_size_mb": 1, "min_snapshots": 2,
                                        "snapshot_retention_days": 0, "orphan_retention_hours": 0})
    store.ensure_tables()
    for n in range(4):
        store.append_rows("findings", [finding_row(n)], batch_id=f"batch_{n:032x}")
    assert store.status()["tables"]["findings"]["data_files"] == 4
    report = store.maintenance()
    assert report["tables"]["findings"]["compacted_files"] == 4
    assert report["tables"]["findings"]["expired_snapshots"] >= 1
    assert store.status()["tables"]["findings"]["data_files"] == 1
    assert len(store.snapshots("findings")) >= 2
    assert len(store.scan_rows("findings")) == 4
    report = store.maintenance(now=datetime.now(timezone.utc))
    assert report["tables"]["findings"]["compacted_files"] == 0
    assert len(store.scan_rows("findings")) == 4


def test_dry_run_and_unknown_profile(tmp_path):
    store = iceberg_store.IcebergStore.open(profile(tmp_path))
    store.ensure_tables()
    store.append_rows("findings", [finding_row(1)], batch_id="batch_" + "e" * 32)
    before = store.status()["tables"]["findings"]
    report = store.maintenance(dry_run=True)
    assert report["dry_run"] is True
    assert store.status()["tables"]["findings"] == before
    with pytest.raises(KeyError):
        store.table("not_a_table")