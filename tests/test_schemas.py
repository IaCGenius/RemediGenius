"""Iceberg schemas, partitions and evolution (roadmap CE-24)."""
from __future__ import annotations

import pyarrow as pa
import pytest
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.schema import Schema
from pyiceberg.types import IntegerType, ListType, MapType, StructType

from rgtriage import contracts, ocsf, schemas

NOW = "2026-06-15T10:00:00Z"


def field_ids(field_type):
    if isinstance(field_type, StructType):
        for field in field_type.fields:
            yield field.field_id
            yield from field_ids(field.field_type)
    elif isinstance(field_type, ListType):
        yield field_type.element_field.field_id
        yield from field_ids(field_type.element_field.field_type)
    elif isinstance(field_type, MapType):
        yield field_type.key_field.field_id
        yield from field_ids(field_type.key_field.field_type)
        yield field_type.value_field.field_id
        yield from field_ids(field_type.value_field.field_type)


def catalog(tmp_path) -> SqlCatalog:
    # PyIceberg's PyArrow file IO needs a plain path on Windows; a file:// URI becomes /C:/... and fails.
    return SqlCatalog("ce", **{"uri": f"sqlite:///{(tmp_path / 'catalog.db').as_posix()}",
                               "warehouse": str(tmp_path / "warehouse")})


def finding_row() -> dict:
    finding = {
        "key": "abc123def456", "source": "inspector", "native_id": "native-1", "product": "Inspector",
        "account": "111122223333", "region": "us-east-1", "title": "CVE-2024-1234 in openssl",
        "description": "A vulnerable package", "severity": "HIGH", "category": "vulnerability",
        "type": "PACKAGE_VULNERABILITY", "control_id": "CVE-2024-1234",
        "resource": {"type": "AwsEc2Instance", "id": "i-0123456789abcdef0", "name": "web-1", "tags": {"env": "prod"}},
        "first_seen": NOW, "last_seen": NOW, "workflow": "NEW", "remediation": {}, "console_url": "",
        "signals": {"exploit_available": True, "epss": 0.4, "fix_available": True},
        "context": {"packages": [{"name": "openssl", "installed": "1.0.1", "manager": "OS"}]},
    }
    scope = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
    payload = contracts.payload_hash({"finding": finding["key"]})
    event = contracts.Event(
        event_id=contracts.observation_event_id("installation-1", scope, NOW, payload), kind="observation",
        installation_id="installation-1", epoch="epoch-1", sequence=1, scope=scope,
        observed_at=NOW, ingested_at=NOW, payload_hash=payload)
    body = b'{"Findings":[]}'
    sha = contracts.bytes_sha256(body)
    ref = contracts.RawRef(sha256=sha, key=contracts.raw_key(scope, NOW, sha), size=len(body), scope=scope,
                           operation="ListFindings", observed_at=NOW)
    return ocsf.finding_row(finding, event, ref, priority="P2", reasons=["severity HIGH"], coverage_status="ok")


def test_every_table_has_unique_field_ids_and_a_documented_partition():
    for name, factory in schemas.TABLES.items():
        table_schema = factory()
        ids = list(field_ids(table_schema))
        assert len(ids) == len(set(ids)), f"duplicate field ids in {name}"
        for column in schemas.PARTITION_COLUMNS.get(name, ()):
            assert column in {f.name for f in table_schema.fields}
        spec = schemas.partition_spec(name)
        assert [field.name for field in spec.fields] == list(schemas.PARTITION_COLUMNS.get(name, ()))
    assert set(schemas.TABLES) == {
        "findings", "signals", "scan_runs", "coverage", "decisions", "fix_events", "verification_attempts",
        "github_ops", "current_findings", "current_fixes", "current_decisions", "current_operations",
        "campaigns", "campaign_members"}


def test_local_catalog_creates_tables_writes_and_reads_a_finding(tmp_path):
    cat = catalog(tmp_path)
    result = schemas.create_tables(cat)
    assert set(result["created"]) == set(schemas.TABLES) and not result["verified"]
    again = schemas.create_tables(cat)
    assert set(again["verified"]) == set(schemas.TABLES) and not again["created"]
    table = cat.load_table("remedigenius.findings")
    assert table.properties["ce.ocsf.version"] == ocsf.OCSF_VERSION
    assert table.properties["ce.schema_version"] == str(schemas.TABLE_SCHEMA_VERSION)
    assert [field.name for field in table.spec().fields] == list(schemas.PARTITION_COLUMNS["findings"])
    arrow = pa.Table.from_pylist([finding_row()], schema=schemas.pyarrow_schema("findings", table.schema()))
    table.append(arrow)
    read = table.scan().to_arrow()
    assert read.num_rows == 1
    assert read.column("class_uid").to_pylist() == [ocsf.CLASS_VULNERABILITY_FINDING]
    assert read.column("raw_sha256").to_pylist() == [finding_row()["raw_sha256"]]
    assert read.column("ce").to_pylist()[0]["finding_key"] == "abc123def456"


def test_schema_evolution_adds_an_optional_column(tmp_path):
    cat = catalog(tmp_path)
    schemas.create_tables(cat, namespace="evolve")
    table = cat.load_table("evolve.findings")
    with table.update_schema() as update:
        update.add_column("ce_note", IntegerType())
    assert "ce_note" in {field.name for field in cat.load_table("evolve.findings").schema().fields}
    assert not [field for field in cat.load_table("evolve.findings").schema().fields if field.name == "ce_note"][0].required


def test_create_tables_refuses_an_incompatible_existing_table(tmp_path):
    cat = catalog(tmp_path)
    cat.create_namespace_if_not_exists("broken")
    without_ocsf = Schema(*[field for field in schemas.findings().fields if field.name != "ocsf"])
    cat.create_table("broken.findings", schema=without_ocsf)
    with pytest.raises(schemas.SchemaMismatch) as mismatch:
        schemas.create_tables(cat, namespace="broken")
    assert "ocsf" in str(mismatch.value)


def test_unknown_table_and_partition_are_explicit():
    with pytest.raises(KeyError):
        schemas.schema("not_a_table")
    assert schemas.partition_spec("decisions").fields == ()