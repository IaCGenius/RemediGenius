"""Versioned storage contract for RemediGenius-CE (roadmap CE-01).

Authority is deliberately narrow:

* every collected AWS response is written once to object storage, content-addressed by SHA-256,
  before a fact derived from it is committed;
* facts are Apache Iceberg tables on object storage and are the system of record;
* local SQLite is a rebuildable cache and a commit outbox, never the only copy of a fact;
* the Hermes home keeps its existing archive checkpoint, and the OKF bundle stays reviewed knowledge.

The desk process is the only writer of raw objects, facts and the cache. Hermes never writes them.
This module holds the identifiers, the event envelope, the durability rules and the two documented
storage profiles. Iceberg table schemas live in ``rgtriage/schemas.py`` (CE-24); the decision record
is ``docs/STORAGE.md``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

CONTRACT_VERSION = "remedigenius-ce-storage/1"
EVENT_SCHEMA_VERSION = 1
CLOCK_SKEW = timedelta(minutes=5)

# A batch is committed once per completed scan run. A decision is durable before it is acknowledged.
# A GitHub call is never made without a committed intent, and its result is committed afterwards.
DURABILITY_BATCH = "batch"
DURABILITY_BEFORE_ACK = "facts_before_ack"
DURABILITY_BEFORE_CALL = "facts_before_call"
DURABILITY_AFTER_CALL = "facts_after_call"

EVENT_KINDS = {
    "observation": DURABILITY_BATCH,
    "coverage": DURABILITY_BATCH,
    "scan_run": DURABILITY_BATCH,
    "signal": DURABILITY_BATCH,
    "verification_attempt": DURABILITY_BATCH,
    "fix_event": DURABILITY_BATCH,
    "decision": DURABILITY_BEFORE_ACK,
    "github_intent": DURABILITY_BEFORE_CALL,
    "github_result": DURABILITY_AFTER_CALL,
}
DETERMINISTIC_KINDS = frozenset(k for k, v in EVENT_KINDS.items() if v == DURABILITY_BATCH)
OPERATION_KINDS = frozenset({"decision", "github_intent", "github_result"})

# Table families. OCSF covers what AWS reported; CE's own tables cover desk concepts.
FACT_TABLES = {
    "findings": "observation",
    "coverage": "coverage",
    "scan_runs": "scan_run",
    "signals": "signal",
    "verification_attempts": "verification_attempt",
    "fix_events": "fix_event",
    "decisions": "decision",
    "github_ops": "github_result",
}
CURRENT_STATE_TABLES = ("current_findings", "current_fixes", "current_decisions", "current_operations")

# Who may write each store. A test asserts the agent never appears as a writer.
AUTHORITY = {
    "raw": {"store": "S3 (or the workstation durable folder)", "writer": "desk", "reader": "desk"},
    "facts": {"store": "Apache Iceberg", "writer": "desk", "reader": "desk"},
    "cache": {"store": "local SQLite", "writer": "desk", "reader": "desk"},
    "knowledge": {"store": "OKF bundle", "writer": "people through the desk", "reader": "desk and agent"},
    "agent_state": {"store": "Hermes home checkpoint", "writer": "desk", "reader": "Hermes"},
}
AGENT_MUST_NOT_WRITE = ("raw", "facts", "cache")

# Storage health is exposed by doctor/status. CE-15 fills these in; the names are part of the contract.
HEALTH_STATES = ("healthy", "degraded", "recovering", "blocked")
HEALTH_FIELDS = (
    "installation_id", "namespace", "epoch", "state", "commit_watermark", "commit_age_seconds",
    "outbox_events", "undurable_decisions", "raw_backlog", "last_maintenance", "checkpoint_age_seconds",
    "unresolved_operations", "reason",
)

_ID_RE = re.compile(r"^evt_[0-9a-f]{32}$")
_BATCH_RE = re.compile(r"^batch_[0-9a-f]{32}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class ContractError(ValueError):
    """A value does not satisfy the storage contract."""


class ConflictError(ContractError):
    """The same event ID was reused with different bytes."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_time(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContractError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractError("timestamp must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"invalid timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"timestamp {value!r} has no timezone")
    return parsed.astimezone(timezone.utc)


def canonical_json(value: Any) -> str:
    """Stable bytes for hashing: sorted keys, no whitespace, no NaN/Infinity."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"value is not canonical JSON: {exc}") from exc


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(value: Any) -> str:
    return _sha256_text(canonical_json(value))


def bytes_sha256(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise ContractError("raw payload must be bytes")
    return hashlib.sha256(bytes(data)).hexdigest()


def _safe_token(value: str, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{name} must be a string")
    if not value:
        if empty:
            return value
        raise ContractError(f"{name} must not be empty")
    if len(value) > 128 or not _SAFE_RE.fullmatch(value):
        raise ContractError(f"{name} must match {_SAFE_RE.pattern}: {value!r}")
    return value


# ------------------------------------------------------------------ identifiers

_UUID7_LOCK = threading.Lock()
_UUID7_LAST_MS = -1
_UUID7_SEQUENCE = 0


def uuid7(now: datetime | None = None) -> uuid.UUID:
    """RFC 9562 UUIDv7, monotonic within this process (a 12-bit counter per millisecond)."""
    global _UUID7_LAST_MS, _UUID7_SEQUENCE
    stamp = now or utc_now()
    millis = int(stamp.timestamp() * 1000)
    with _UUID7_LOCK:
        if millis > _UUID7_LAST_MS:
            _UUID7_LAST_MS, _UUID7_SEQUENCE = millis, 0
        else:
            millis = _UUID7_LAST_MS
            _UUID7_SEQUENCE += 1
            if _UUID7_SEQUENCE > 0xFFF:
                _UUID7_LAST_MS += 1
                millis, _UUID7_SEQUENCE = _UUID7_LAST_MS, 0
        sequence = _UUID7_SEQUENCE
    random_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (millis << 80) | (0x7 << 76) | (sequence << 64) | (0b10 << 62) | random_b
    return uuid.UUID(int=value)


def new_installation_id() -> str:
    return str(uuid7())


def new_recovery_epoch() -> str:
    return str(uuid7())


def operation_event_id() -> str:
    return str(uuid7())


def is_event_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if _ID_RE.fullmatch(value):
        return True
    try:
        return uuid.UUID(value).version == 7
    except (ValueError, AttributeError):
        return False


def observation_event_id(installation_id: str, scope: "Scope", observed_at: str,
                         content_sha256: str, kind: str = "observation") -> str:
    """Deterministic ID for an observed fact: same installation, scope, time and bytes -> same ID."""
    if kind not in DETERMINISTIC_KINDS:
        raise ContractError(f"{kind!r} is not a deterministic event kind")
    if not _HEX64_RE.fullmatch(content_sha256 or ""):
        raise ContractError("content_sha256 must be 64 lowercase hex characters")
    if not installation_id:
        raise ContractError("installation_id must not be empty")
    material = canonical_json({
        "contract": CONTRACT_VERSION, "schema_version": EVENT_SCHEMA_VERSION, "kind": kind,
        "installation_id": installation_id, "scope": scope.as_dict(),
        "observed_at": format_time(parse_time(observed_at)), "content_sha256": content_sha256,
    })
    return f"evt_{_sha256_text(material)[:32]}"


# ------------------------------------------------------------------ value objects

@dataclass(frozen=True, slots=True)
class Scope:
    account: str = ""
    region: str = ""
    source: str = ""
    filter_hash: str = ""

    def __post_init__(self) -> None:
        _safe_token(self.account, "scope.account", empty=True)
        _safe_token(self.region, "scope.region", empty=True)
        _safe_token(self.source, "scope.source", empty=True)
        if self.filter_hash and not _HEX64_RE.fullmatch(self.filter_hash):
            raise ContractError("scope.filter_hash must be empty or 64 lowercase hex characters")

    def as_dict(self) -> dict:
        return {"account": self.account, "region": self.region, "source": self.source,
                "filter_hash": self.filter_hash}

    @classmethod
    def from_dict(cls, data: dict) -> "Scope":
        return cls(**{k: data.get(k, "") for k in ("account", "region", "source", "filter_hash")})


@dataclass(frozen=True, slots=True)
class RawRef:
    """One collected API response, addressed by the SHA-256 of its stored bytes."""
    sha256: str
    key: str
    size: int
    scope: Scope
    operation: str
    observed_at: str
    parameters_hash: str = ""

    def __post_init__(self) -> None:
        if not _HEX64_RE.fullmatch(self.sha256 or ""):
            raise ContractError("raw.sha256 must be 64 lowercase hex characters")
        if not isinstance(self.size, int) or self.size < 0:
            raise ContractError("raw.size must be a non-negative integer")
        if not self.key or self.key.startswith("/") or ".." in self.key.split("/"):
            raise ContractError(f"raw.key must be a relative key without '..': {self.key!r}")
        _safe_token(self.operation, "raw.operation")
        object.__setattr__(self, "observed_at", format_time(parse_time(self.observed_at)))
        if self.parameters_hash and not _HEX64_RE.fullmatch(self.parameters_hash):
            raise ContractError("raw.parameters_hash must be empty or 64 lowercase hex characters")

    def as_dict(self) -> dict:
        return {"sha256": self.sha256, "key": self.key, "bytes": self.size, "scope": self.scope.as_dict(),
                "operation": self.operation, "observed_at": self.observed_at,
                "parameters_hash": self.parameters_hash}

    @classmethod
    def from_dict(cls, data: dict) -> "RawRef":
        return cls(sha256=data["sha256"], key=data["key"], size=int(data["bytes"]),
                   scope=Scope.from_dict(data["scope"]), operation=data["operation"],
                   observed_at=data["observed_at"], parameters_hash=data.get("parameters_hash", ""))


def raw_key(scope: Scope, observed_at: str, sha256: str) -> str:
    """Content-addressed, day-partitioned key for one response page."""
    if not _HEX64_RE.fullmatch(sha256 or ""):
        raise ContractError("sha256 must be 64 lowercase hex characters")
    stamp = parse_time(observed_at)
    account = _safe_token(scope.account or "installation", "scope.account")
    region = _safe_token(scope.region or "global", "scope.region")
    source = _safe_token(scope.source or "desk", "scope.source")
    return f"raw/{account}/{region}/{source}/{stamp:%Y}/{stamp:%m}/{stamp:%d}/{sha256}.json.gz"


@dataclass(frozen=True, slots=True)
class Watermark:
    installation_id: str
    namespace: str
    epoch: str
    sequence: int
    committed_at: str
    snapshot_id: int | None = None

    def __post_init__(self) -> None:
        if not self.installation_id or not self.epoch:
            raise ContractError("watermark needs an installation and an epoch")
        _safe_token(self.namespace, "watermark.namespace")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ContractError("watermark.sequence must be a non-negative integer")
        object.__setattr__(self, "committed_at", format_time(parse_time(self.committed_at)))

    def as_dict(self) -> dict:
        return {"installation_id": self.installation_id, "namespace": self.namespace, "epoch": self.epoch,
                "sequence": self.sequence, "committed_at": self.committed_at, "snapshot_id": self.snapshot_id}

    @classmethod
    def from_dict(cls, data: dict) -> "Watermark":
        return cls(installation_id=data["installation_id"], namespace=data["namespace"], epoch=data["epoch"],
                   sequence=int(data["sequence"]), committed_at=data["committed_at"],
                   snapshot_id=data.get("snapshot_id"))

    def covers(self, other: "Watermark") -> bool:
        """True when this watermark includes everything the other one does (same install and epoch)."""
        return ((self.installation_id, self.namespace, self.epoch) ==
                (other.installation_id, other.namespace, other.epoch) and self.sequence >= other.sequence)

    def lag_seconds(self, now: datetime | None = None) -> float:
        return max(0.0, ((now or utc_now()) - parse_time(self.committed_at)).total_seconds())

    def next(self, committed_at: str | None = None, snapshot_id: int | None = None) -> "Watermark":
        return replace(self, sequence=self.sequence + 1,
                       committed_at=committed_at or format_time(utc_now()),
                       snapshot_id=snapshot_id if snapshot_id is not None else self.snapshot_id)


def clock_skew(observed_at: str, ingested_at: str) -> timedelta:
    """How far the source clock is ahead of the ingestion clock (negative when behind)."""
    return parse_time(observed_at) - parse_time(ingested_at)


def clock_skewed(observed_at: str, ingested_at: str) -> bool:
    """A source clock ahead by more than the tolerated skew is recorded and flagged, never reordered."""
    return clock_skew(observed_at, ingested_at) > CLOCK_SKEW


def known_at(observed_at: str, ingested_at: str, as_of: str) -> bool:
    """What a person could have known at ``as_of`` depends on when the evidence was ingested."""
    return parse_time(ingested_at) <= parse_time(as_of)


# ------------------------------------------------------------------ event envelope

@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    kind: str
    installation_id: str
    epoch: str
    sequence: int
    scope: Scope
    observed_at: str
    ingested_at: str
    payload_hash: str
    raw_ref: RawRef | None = None
    corrects: tuple[str, ...] = ()
    retracts: tuple[str, ...] = ()
    batch_id: str | None = None
    schema_version: int = EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ContractError(f"unsupported event schema version {self.schema_version}")
        if self.kind not in EVENT_KINDS:
            raise ContractError(f"unknown event kind {self.kind!r}")
        if not is_event_id(self.event_id):
            raise ContractError(f"invalid event id {self.event_id!r}")
        deterministic = self.kind in DETERMINISTIC_KINDS
        if deterministic and not _ID_RE.fullmatch(self.event_id):
            raise ContractError(f"{self.kind} events use deterministic evt_ IDs")
        if self.kind in OPERATION_KINDS and _ID_RE.fullmatch(self.event_id):
            raise ContractError(f"{self.kind} events use UUIDv7 IDs")
        if not self.installation_id or not self.epoch:
            raise ContractError("event needs an installation and an epoch")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ContractError("event.sequence must be a non-negative integer")
        if not _HEX64_RE.fullmatch(self.payload_hash or ""):
            raise ContractError("event.payload_hash must be 64 lowercase hex characters")
        observed, ingested = parse_time(self.observed_at), parse_time(self.ingested_at)
        object.__setattr__(self, "observed_at", format_time(observed))
        object.__setattr__(self, "ingested_at", format_time(ingested))
        if observed > ingested + timedelta(days=1):
            raise ContractError("observed_at is more than a day ahead of ingested_at")
        for link in (*self.corrects, *self.retracts):
            if not is_event_id(link):
                raise ContractError(f"invalid correction/retraction link {link!r}")
        if self.batch_id is not None and not _BATCH_RE.fullmatch(self.batch_id):
            raise ContractError(f"invalid batch id {self.batch_id!r}")

    @property
    def durability(self) -> str:
        return EVENT_KINDS[self.kind]

    def is_clock_skewed(self) -> bool:
        return clock_skewed(self.observed_at, self.ingested_at)

    def known_at(self, as_of: str) -> bool:
        return known_at(self.observed_at, self.ingested_at, as_of)

    def conflict_with(self, other: "Event") -> bool:
        return self.event_id == other.event_id and self.payload_hash != other.payload_hash

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT_VERSION, "schema_version": self.schema_version,
            "event_id": self.event_id, "kind": self.kind, "installation_id": self.installation_id,
            "epoch": self.epoch, "sequence": self.sequence, "scope": self.scope.as_dict(),
            "observed_at": self.observed_at, "ingested_at": self.ingested_at,
            "payload_hash": self.payload_hash,
            "raw_ref": self.raw_ref.as_dict() if self.raw_ref else None,
            "corrects": list(self.corrects), "retracts": list(self.retracts), "batch_id": self.batch_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        if data.get("contract", CONTRACT_VERSION) != CONTRACT_VERSION:
            raise ContractError(f"unsupported contract {data.get('contract')!r}")
        raw = data.get("raw_ref")
        return cls(
            event_id=data["event_id"], kind=data["kind"], installation_id=data["installation_id"],
            epoch=data["epoch"], sequence=int(data["sequence"]), scope=Scope.from_dict(data["scope"]),
            observed_at=data["observed_at"], ingested_at=data["ingested_at"],
            payload_hash=data["payload_hash"], raw_ref=RawRef.from_dict(raw) if raw else None,
            corrects=tuple(data.get("corrects") or ()), retracts=tuple(data.get("retracts") or ()),
            batch_id=data.get("batch_id"), schema_version=int(data.get("schema_version", EVENT_SCHEMA_VERSION)),
        )


def classify_replay(existing_payload_hash: str, incoming: Event) -> str:
    """``identical`` for the same event ID and bytes; ``conflict`` for reused IDs with other bytes."""
    if existing_payload_hash == incoming.payload_hash:
        return "identical"
    return "conflict"


def check_event_set(events: Iterable[Event]) -> tuple[Event, ...]:
    """Reject a batch that reuses an event ID with different bytes; return it de-duplicated by ID."""
    unique: dict[str, Event] = {}
    for event in events:
        previous = unique.get(event.event_id)
        if previous is None:
            unique[event.event_id] = event
        elif previous.payload_hash != event.payload_hash:
            raise ConflictError(f"event {event.event_id} appears with different payloads")
    return tuple(unique[key] for key in sorted(unique))


@dataclass(frozen=True, slots=True)
class BatchPlan:
    batch_id: str
    content_hash: str
    event_ids: tuple[str, ...]
    raw_hashes: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"batch_id": self.batch_id, "content_hash": self.content_hash,
                "event_ids": list(self.event_ids), "raw_hashes": list(self.raw_hashes)}


def plan_batch(events: Iterable[Event]) -> BatchPlan:
    """Deterministic batch identity, recorded in the Iceberg snapshot summary for retry detection."""
    ordered = check_event_set(events)
    if not ordered:
        raise ContractError("a batch needs at least one event")
    content_hash = payload_hash([{"event_id": e.event_id, "payload_hash": e.payload_hash} for e in ordered])
    batch_id = f"batch_{_sha256_text(canonical_json({'v': EVENT_SCHEMA_VERSION, 'content': content_hash, 'ids': [e.event_id for e in ordered]}))[:32]}"
    raw_hashes = tuple(sorted({e.raw_ref.sha256 for e in ordered if e.raw_ref}))
    return BatchPlan(batch_id=batch_id, content_hash=content_hash,
                     event_ids=tuple(e.event_id for e in ordered), raw_hashes=raw_hashes)


# ------------------------------------------------------------------ storage profiles

@dataclass(frozen=True, slots=True)
class StorageProfile:
    kind: str
    namespace: str
    warehouse: str
    catalog: str
    catalog_uri: str = ""
    raw_prefix: str = "raw"

    def __post_init__(self) -> None:
        if self.kind not in ("aws", "local"):
            raise ContractError(f"unknown storage profile {self.kind!r}")
        _safe_token(self.namespace, "storage.namespace")
        if self.kind == "aws":
            if not self.warehouse.startswith("s3://") or len(self.warehouse) <= 5:
                raise ContractError("the aws profile needs an s3:// warehouse")
            if self.catalog != "glue":
                raise ContractError("the aws profile uses the Glue catalog")
        else:
            if self.catalog != "sql":
                raise ContractError("the local profile uses the SQL catalog")
            if not self.catalog_uri:
                raise ContractError("the local profile needs a catalog file")
        if not self.raw_prefix or self.raw_prefix.startswith("/") or ".." in self.raw_prefix.split("/"):
            raise ContractError(f"invalid raw prefix {self.raw_prefix!r}")

    def as_dict(self) -> dict:
        return {"kind": self.kind, "namespace": self.namespace, "warehouse": self.warehouse,
                "catalog": self.catalog, "catalog_uri": self.catalog_uri, "raw_prefix": self.raw_prefix}


def storage_profile(data: dict | None = None, home: Path | str | None = None) -> StorageProfile:
    """Resolve the documented profile from the triage profile.

    ``profile: auto`` picks AWS when a warehouse URI is set (Spot), otherwise the local profile
    (Docker workstation). Both are authoritative for their installation.
    """
    data = data or {}
    storage = data.get("storage") or {}
    kind = str(storage.get("profile") or "auto")
    namespace = str(storage.get("namespace") or "remedigenius")
    raw_prefix = str(storage.get("raw_prefix") or "raw")
    warehouse_uri = str(storage.get("warehouse_uri") or "")
    if kind not in ("auto", "aws", "local"):
        raise ContractError(f"unknown storage profile {kind!r}")
    if kind == "auto":
        kind = "aws" if warehouse_uri.startswith("s3://") else "local"
    if kind == "aws":
        return StorageProfile(kind="aws", namespace=namespace, warehouse=warehouse_uri,
                              catalog="glue", catalog_uri=str(storage.get("catalog_database") or ""),
                              raw_prefix=raw_prefix)
    base = Path(home or os.environ.get("RGTRIAGE_HOME") or Path.home() / ".rgtriage")
    return StorageProfile(kind="local", namespace=namespace, warehouse=str(base / "warehouse"),
                          catalog="sql", catalog_uri=str(base / "catalog.db"), raw_prefix=raw_prefix)


def schema_path(name: str) -> Path:
    return Path(__file__).with_name("schemas") / name