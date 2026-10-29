"""The storage contract (roadmap CE-01): identifiers, envelopes, durability, profiles."""
from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from rgtriage import config, contracts

UTC = timezone.utc
NOW = "2026-06-15T10:00:00Z"
LATER = "2026-06-16T09:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
PAYLOAD = {"finding": {"id": "arn:aws:inspector:us-east-1:111122223333:target/1", "severity": "HIGH"}}


def raw_ref(observed_at: str = NOW, data: bytes = b'{"Findings":[]}') -> contracts.RawRef:
    digest = contracts.bytes_sha256(data)
    return contracts.RawRef(sha256=digest, key=contracts.raw_key(SCOPE, observed_at, digest), size=len(data),
                            scope=SCOPE, operation="ListFindings", observed_at=observed_at,
                            parameters_hash=contracts.payload_hash({"severity": "HIGH"}))


def make_event(*, kind: str = "observation", installation_id: str = "installation-1", epoch: str = "epoch-1",
               scope: contracts.Scope = SCOPE, observed_at: str = NOW, ingested_at: str = NOW,
               payload: dict | None = None, sequence: int = 1, with_raw: bool = True) -> contracts.Event:
    payload = PAYLOAD if payload is None else payload
    digest = contracts.payload_hash(payload)
    event_id = (contracts.observation_event_id(installation_id, scope, observed_at, digest, kind)
                if kind in contracts.DETERMINISTIC_KINDS else contracts.operation_event_id())
    return contracts.Event(
        event_id=event_id, kind=kind, installation_id=installation_id, epoch=epoch, sequence=sequence,
        scope=scope, observed_at=observed_at, ingested_at=ingested_at, payload_hash=digest,
        raw_ref=raw_ref(observed_at) if with_raw and kind in contracts.DETERMINISTIC_KINDS else None,
    )


def validator(name: str) -> Draft202012Validator:
    base = contracts.schema_path("")
    schemas = {f"urn:remedigenius-ce:{stem}:1": json.loads((base / f"{stem}.v1.json").read_text(encoding="utf-8"))
               for stem in ("event-envelope", "raw-ref", "watermark")}
    registry = Registry().with_resources(
        [(uri, Resource.from_contents(doc)) for uri, doc in schemas.items()])
    main = next(doc for uri, doc in schemas.items() if uri.endswith(f"{name}:1"))
    return Draft202012Validator(main, registry=registry)


# ------------------------------------------------------------------ canonical bytes and identifiers

def test_canonical_json_is_stable_and_strict():
    assert contracts.canonical_json({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
    assert contracts.payload_hash({"a": 1, "b": 2}) == contracts.payload_hash({"b": 2, "a": 1})
    assert contracts.payload_hash({"a": 1}) != contracts.payload_hash({"a": 2})
    with pytest.raises(contracts.ContractError):
        contracts.canonical_json({"a": float("nan")})


def test_observation_event_id_is_deterministic_per_installation_and_instant():
    digest = contracts.payload_hash(PAYLOAD)
    base = contracts.observation_event_id("installation-1", SCOPE, NOW, digest)
    assert base.startswith("evt_") and len(base) == 36
    assert base == contracts.observation_event_id("installation-1", SCOPE, "2026-06-15T12:00:00+02:00", digest)
    assert base != contracts.observation_event_id("installation-2", SCOPE, NOW, digest)
    assert base != contracts.observation_event_id("installation-1", SCOPE, LATER, digest)
    assert base != contracts.observation_event_id("installation-1", SCOPE, NOW, contracts.payload_hash({"other": 1}))
    with pytest.raises(contracts.ContractError):
        contracts.observation_event_id("installation-1", SCOPE, NOW, digest, kind="decision")


def test_operation_ids_are_monotonic_uuid7():
    ids = [str(contracts.uuid7()) for _ in range(500)]
    assert all(uuid.UUID(value).version == 7 for value in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert contracts.is_event_id(ids[0])
    assert contracts.is_event_id(contracts.observation_event_id("i", SCOPE, NOW, contracts.payload_hash({})))
    assert not contracts.is_event_id("not-an-event")


def test_timestamps_must_carry_a_timezone():
    assert contracts.format_time(contracts.parse_time("2026-06-15T10:00:00Z")) == "2026-06-15T10:00:00.000000Z"
    with pytest.raises(contracts.ContractError):
        contracts.parse_time("2026-06-15T10:00:00")
    with pytest.raises(contracts.ContractError):
        contracts.format_time(datetime(2026, 6, 15))


# ------------------------------------------------------------------ raw evidence

def test_raw_key_is_content_addressed_and_day_partitioned():
    ref = raw_ref()
    assert ref.key == f"raw/111122223333/us-east-1/inspector/2026/06/15/{ref.sha256}.json.gz"
    assert contracts.RawRef.from_dict(ref.as_dict()) == ref
    with pytest.raises(contracts.ContractError):
        contracts.raw_key(SCOPE, NOW, "not-a-hash")
    with pytest.raises(contracts.ContractError):
        contracts.RawRef(sha256="0" * 64, key="/etc/passwd", size=1, scope=SCOPE, operation="Get", observed_at=NOW)
    with pytest.raises(contracts.ContractError):
        contracts.RawRef(sha256="0" * 64, key="raw/../secret", size=1, scope=SCOPE, operation="Get", observed_at=NOW)
    with pytest.raises(contracts.ContractError):
        contracts.Scope(account="1111/2222")


# ------------------------------------------------------------------ events and durability

def test_event_round_trips_and_validates_against_the_json_schema():
    event = make_event()
    assert contracts.Event.from_dict(event.as_dict()) == event
    validator("event-envelope").validate(event.as_dict())
    validator("raw-ref").validate(event.raw_ref.as_dict())
    assert event.durability == contracts.DURABILITY_BATCH
    assert make_event(kind="decision", with_raw=False).durability == contracts.DURABILITY_BEFORE_ACK


def test_event_rejects_wrong_id_shapes_and_unknown_kinds():
    event = make_event()
    with pytest.raises(contracts.ContractError):
        replace(event, kind="guess")
    with pytest.raises(contracts.ContractError):
        contracts.Event(event_id=str(contracts.uuid7()), kind="observation", installation_id="i", epoch="e",
                        sequence=1, scope=SCOPE, observed_at=NOW, ingested_at=NOW,
                        payload_hash=contracts.payload_hash({}))
    with pytest.raises(contracts.ContractError):
        contracts.Event(event_id=event.event_id, kind="decision", installation_id="i", epoch="e",
                        sequence=1, scope=SCOPE, observed_at=NOW, ingested_at=NOW,
                        payload_hash=contracts.payload_hash({}))


def test_conflicting_reuse_is_not_a_replay():
    event = make_event()
    replay = make_event()
    conflict = make_event(payload={**PAYLOAD, "finding": {"severity": "LOW"}})
    assert conflict.event_id != event.event_id  # payload is part of the deterministic ID
    assert contracts.classify_replay(event.payload_hash, replay) == "identical"
    assert contracts.classify_replay(event.payload_hash, conflict) == "conflict"
    same_id = replace(event, payload_hash="f" * 64)
    with pytest.raises(contracts.ConflictError):
        contracts.check_event_set([event, same_id])


def test_event_set_deduplicates_identical_events_and_sorts_ids():
    first, second = make_event(sequence=1), make_event(payload={"b": 2}, sequence=2)
    events = contracts.check_event_set([second, first, first])
    assert [e.event_id for e in events] == sorted({first.event_id, second.event_id})


def test_late_arrival_and_clock_skew_policy():
    late = make_event(observed_at=NOW, ingested_at=LATER)
    assert not late.known_at("2026-06-15T23:59:59Z")
    assert late.known_at(LATER)
    assert late.is_clock_skewed() is False
    ahead = make_event(observed_at="2026-06-15T10:10:00Z", ingested_at=NOW)
    assert ahead.is_clock_skewed() is True
    assert contracts.clock_skewed("2026-06-15T10:03:00Z", NOW) is False
    assert contracts.clock_skew( "2026-06-15T10:03:00Z", NOW) == timedelta(minutes=3)


# ------------------------------------------------------------------ batches and watermarks

def test_batch_plan_is_deterministic_and_covers_raw_evidence():
    first, second = make_event(sequence=1), make_event(payload={"b": 2}, sequence=2)
    plan = contracts.plan_batch([second, first])
    assert plan == contracts.plan_batch([first, second])
    assert plan.batch_id.startswith("batch_") and len(plan.batch_id) == 38
    assert plan.event_ids == tuple(sorted((first.event_id, second.event_id)))
    assert plan.raw_hashes == tuple(sorted({first.raw_ref.sha256, second.raw_ref.sha256}))
    assert contracts.plan_batch([first]).content_hash != contracts.plan_batch([second]).content_hash
    with pytest.raises(contracts.ContractError):
        contracts.plan_batch([])


def test_watermark_covers_only_its_own_installation_epoch_and_namespace():
    mark = contracts.Watermark("installation-1", "remedigenius", "epoch-1", 7, NOW, snapshot_id=42)
    same = contracts.Watermark("installation-1", "remedigenius", "epoch-1", 6, NOW)
    assert mark.covers(same) and not same.covers(mark)
    assert not mark.covers(contracts.Watermark("installation-1", "remedigenius", "epoch-2", 1, NOW))
    assert mark.next().sequence == 8
    assert mark.lag_seconds(contracts.parse_time("2026-06-15T10:01:00Z")) == 60
    validator("watermark").validate(mark.as_dict())


# ------------------------------------------------------------------ profiles, authority and recovery

def test_storage_profiles(tmp_path):
    local = contracts.storage_profile({}, tmp_path)
    assert (local.kind, local.catalog, local.catalog_uri) == ("local", "sql", str(tmp_path / "catalog.db"))
    assert local.warehouse == str(tmp_path / "warehouse")
    aws = contracts.storage_profile({"storage": {"warehouse_uri": "s3://bucket/warehouse"}}, tmp_path)
    assert (aws.kind, aws.catalog, aws.warehouse) == ("aws", "glue", "s3://bucket/warehouse")
    with pytest.raises(contracts.ContractError):
        contracts.storage_profile({"storage": {"profile": "aws"}}, tmp_path)
    with pytest.raises(contracts.ContractError):
        contracts.storage_profile({"storage": {"profile": "cloud"}}, tmp_path)


def test_authority_matrix_keeps_the_agent_out_of_authoritative_stores():
    for store in contracts.AGENT_MUST_NOT_WRITE:
        assert "agent" not in contracts.AUTHORITY[store]["writer"]
        assert contracts.AUTHORITY[store]["writer"] == "desk"
    for table, kind in contracts.FACT_TABLES.items():
        assert kind in contracts.EVENT_KINDS, table
    assert contracts.CURRENT_STATE_TABLES
    assert {"installation_id", "commit_watermark", "outbox_events", "undurable_decisions", "raw_backlog"} <= set(contracts.HEALTH_FIELDS)
    assert "healthy" in contracts.HEALTH_STATES


def test_config_normalizes_storage_and_exposes_the_profile(tmp_path, monkeypatch):
    profile = config.normalize({"name": "t"})
    assert profile["storage"]["profile"] == "auto"
    assert profile["storage"]["maintenance"]["snapshot_retention_days"] == 14
    merged = config.normalize({"storage": {"maintenance": {"interval_hours": 6}}})
    assert merged["storage"]["maintenance"]["interval_hours"] == 6
    assert merged["storage"]["maintenance"]["min_snapshots"] == 5
    with pytest.raises(ValueError):
        config.normalize({"storage": "s3"})
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    (tmp_path / "triage.yaml").write_text("name: t\n", encoding="utf-8")
    assert config.storage().kind == "local"