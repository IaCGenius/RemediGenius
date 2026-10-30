"""Iceberg table schemas for the CE storage release (roadmap CE-24).

Findings are OCSF 1.9.0 rows; desk concepts use CE's own tables. Account, region, class and event day are
top-level columns so they can be partition columns. Schema version 1 is the first released version.

Evolution rules: adding a column is a new optional field with a new field ID and a version bump; existing field
IDs and names never change; only int→long and float→double promotions are allowed. An OCSF version upgrade is an
explicit migration. See docs/SCHEMA.md.
"""
from __future__ import annotations

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import IdentityTransform
from pyiceberg.types import (
    BooleanType, DateType, DoubleType, IntegerType, ListType, LongType, MapType, NestedField, StringType,
    StructType, TimestamptzType,
)

from .ocsf import OCSF_VERSION

TABLE_SCHEMA_VERSION = 1


class SchemaMismatch(RuntimeError):
    """An existing table does not match the expected schema; refuse to read or write it."""


def _f(field_id: int, name: str, kind, required: bool = False, doc: str = "") -> NestedField:
    return NestedField(field_id=field_id, name=name, field_type=kind, required=required, doc=doc or None)


def _strings(field_id: int, name: str, required: bool = False, doc: str = "") -> NestedField:
    return _f(field_id, name, ListType(element_id=field_id + 1000, element_type=StringType(),
                                      element_required=False), required, doc)


def _scope(base: int) -> StructType:
    return StructType(
        _f(base, "account", StringType()), _f(base + 1, "region", StringType()),
        _f(base + 2, "source", StringType()), _f(base + 3, "filter_hash", StringType()))


def _watermark(base: int) -> StructType:
    return StructType(
        _f(base, "installation_id", StringType(), True), _f(base + 1, "namespace", StringType(), True),
        _f(base + 2, "epoch", StringType(), True), _f(base + 3, "sequence", LongType(), True),
        _f(base + 4, "committed_at", TimestamptzType(), True), _f(base + 5, "snapshot_id", LongType()))


def _resource(base: int) -> StructType:
    return StructType(
        _f(base, "uid", StringType()), _f(base + 1, "type", StringType()), _f(base + 2, "name", StringType()),
        _f(base + 3, "region", StringType()), _f(base + 4, "account_uid", StringType()),
        _f(base + 5, "tags", MapType(key_id=base + 6, key_type=StringType(), value_id=base + 7,
                                     value_type=StringType(), value_required=False)),
        _f(base + 8, "data", StringType()))


def _product(base: int) -> StructType:
    return StructType(
        _f(base, "name", StringType()), _f(base + 1, "vendor_name", StringType()), _f(base + 2, "feature_name", StringType()))


def _metadata(base: int) -> StructType:
    return StructType(_f(base, "version", StringType(), True, "Pinned OCSF version"), _f(base + 1, "product", _product(base + 10)))


def _finding_info(base: int) -> StructType:
    return StructType(
        _f(base, "uid", StringType()), _f(base + 1, "title", StringType()), _f(base + 2, "desc", StringType()),
        _f(base + 3, "created_time", TimestamptzType()), _f(base + 4, "modified_time", TimestamptzType()),
        _f(base + 5, "first_seen_time", TimestamptzType()), _f(base + 6, "last_seen_time", TimestamptzType()),
        _strings(base + 7, "types"))


def _cloud(base: int) -> StructType:
    return StructType(_f(base, "provider", StringType()), _f(base + 1, "region", StringType()),
                      _f(base + 2, "account_uid", StringType()))


def _vulnerability(base: int) -> StructType:
    return StructType(
        _f(base, "uid", StringType()), _f(base + 1, "cve_uid", StringType()), _f(base + 2, "cve_desc", StringType()),
        _f(base + 3, "title", StringType()), _f(base + 4, "severity", StringType()),
        _f(base + 5, "is_exploit_available", BooleanType()), _f(base + 6, "epss_score", DoubleType()),
        _f(base + 7, "fix_available", BooleanType()), _f(base + 8, "package_name", StringType()),
        _f(base + 9, "package_version", StringType()), _f(base + 10, "package_manager", StringType()))


def _compliance(base: int) -> StructType:
    return StructType(
        _f(base, "status_id", IntegerType()), _f(base + 1, "status", StringType()),
        _f(base + 2, "control", StringType()), _strings(base + 3, "standards"),
        _strings(base + 4, "requirements"))


def _ocsf(base: int) -> StructType:
    return StructType(
        _f(base, "metadata", _metadata(base + 10), True),
        _f(base + 1, "category_uid", IntegerType(), True),
        _f(base + 2, "class_uid", IntegerType(), True),
        _f(base + 3, "class_name", StringType()),
        _f(base + 4, "activity_id", IntegerType()),
        _f(base + 5, "type_uid", LongType()),
        _f(base + 6, "time", TimestamptzType()),
        _f(base + 7, "severity_id", IntegerType()),
        _f(base + 8, "status_id", IntegerType()),
        _f(base + 9, "finding_info", _finding_info(base + 100)),
        _f(base + 20, "cloud", _cloud(base + 130)),
        _f(base + 21, "resources", ListType(element_id=base + 140, element_type=_resource(base + 150),
                                           element_required=False)),
        _f(base + 22, "vulnerabilities", ListType(element_id=base + 200, element_type=_vulnerability(base + 210),
                                                 element_required=False)),
        _f(base + 23, "compliance", _compliance(base + 260)),
        _f(base + 24, "unmapped", StringType(), doc="JSON object: CE extension and residual source fields"))


def _ce(base: int) -> StructType:
    return StructType(
        _f(base, "finding_key", StringType()), _f(base + 1, "source", StringType()),
        _f(base + 2, "priority", StringType()), _strings(base + 3, "reasons"),
        _f(base + 4, "issue_key", StringType()), _f(base + 5, "scope", _scope(base + 10)),
        _f(base + 6, "raw_sha256", StringType()), _f(base + 7, "raw_key", StringType()),
        _f(base + 8, "observed_at", StringType()), _f(base + 9, "ingested_at", StringType()),
        _f(base + 20, "coverage_status", StringType()), _f(base + 21, "truncated", BooleanType()),
        _f(base + 22, "mapping", StringType()), _f(base + 23, "mapping_error", StringType()))


def findings() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True, "Deterministic observation event ID"),
        _f(2, "installation_id", StringType(), True), _f(3, "epoch", StringType(), True),
        _f(4, "sequence", LongType(), True), _f(5, "account_id", StringType()),
        _f(6, "region", StringType()), _f(7, "class_uid", IntegerType(), True),
        _f(8, "event_day", DateType(), True, "UTC observation day, a partition column"),
        _f(9, "observed_at", TimestamptzType(), True), _f(10, "ingested_at", TimestamptzType(), True),
        _f(11, "payload_hash", StringType(), True), _f(12, "raw_sha256", StringType()),
        _f(13, "raw_key", StringType()), _f(14, "ocsf", _ocsf(100), True), _f(15, "ce", _ce(400), True))


def signals() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True),
        _f(5, "account_id", StringType()), _f(6, "region", StringType()), _f(7, "source", StringType(), True),
        _f(8, "signal_type", StringType()), _f(9, "severity_id", IntegerType()), _f(10, "status", StringType()),
        _f(11, "title", StringType()), _f(12, "first_seen", TimestamptzType()), _f(13, "last_seen", TimestamptzType()),
        _f(14, "observed_at", TimestamptzType(), True), _f(15, "ingested_at", TimestamptzType(), True),
        _f(16, "resource", _resource(200)), _f(17, "detail", StringType(), doc="JSON residual fields"),
        _f(18, "raw_sha256", StringType()), _f(19, "raw_key", StringType()))


def scan_runs() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True), _f(5, "run_id", StringType(), True),
        _f(6, "started_at", TimestamptzType()), _f(7, "completed_at", TimestamptzType()),
        _f(8, "status", StringType(), True), _strings(9, "accounts"), _strings(10, "regions"),
        _strings(11, "sources"), _f(12, "findings_count", LongType()), _f(13, "issues_count", LongType()),
        _f(14, "truncated", BooleanType()), _f(15, "note", StringType()), _f(16, "raw_sha256", StringType()),
        _f(17, "observed_at", TimestamptzType(), True), _f(18, "ingested_at", TimestamptzType(), True),
        _f(19, "payload_hash", StringType()))


def coverage() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True), _f(5, "run_id", StringType()),
        _f(6, "account_id", StringType()), _f(7, "region", StringType()), _f(8, "source", StringType(), True),
        _f(9, "status", StringType(), True), _f(10, "count", LongType()), _f(11, "total", LongType()),
        _f(12, "truncated", BooleanType()), _f(13, "completeness", StringType()), _f(14, "note", StringType()),
        _f(15, "raw_sha256", StringType()), _f(16, "observed_at", TimestamptzType(), True))


def decisions() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True, "UUIDv7 human event"), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True), _f(5, "finding_key", StringType(), True),
        _f(6, "status", StringType(), True), _f(7, "reason", StringType()), _f(8, "by", StringType()),
        _f(9, "decided_at", TimestamptzType(), True), _f(10, "fix", StringType(), doc="JSON fix record"),
        _f(11, "raw_sha256", StringType()), _f(12, "observed_at", TimestamptzType(), True),
        _f(13, "ingested_at", TimestamptzType(), True))


def fix_events() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True), _f(5, "finding_key", StringType(), True),
        _f(6, "state", StringType(), True), _f(7, "previous_state", StringType()),
        _f(8, "changed_at", TimestamptzType(), True), _f(9, "source", StringType()),
        _f(10, "evidence", StringType(), doc="JSON evidence"), _f(11, "owner", StringType()),
        _f(12, "raw_sha256", StringType()), _f(13, "observed_at", TimestamptzType(), True),
        _f(14, "ingested_at", TimestamptzType(), True))


def verification_attempts() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True), _f(5, "finding_key", StringType()),
        _f(6, "attempt_at", TimestamptzType(), True), _f(7, "outcome", StringType(), True),
        _f(8, "passed", BooleanType()), _f(9, "observed", StringType(), doc="JSON observed values"),
        _f(10, "error", StringType()), _f(11, "target",
                                          StructType(_f(12, "account_id", StringType()), _f(13, "region", StringType()),
                                                     _f(14, "resource_type", StringType()), _f(15, "resource_id", StringType()))),
        _f(16, "rule_version", StringType()), _f(17, "raw_sha256", StringType()),
        _f(18, "observed_at", TimestamptzType(), True), _f(19, "ingested_at", TimestamptzType(), True),
        _f(20, "visibility", StringType()), _f(21, "target_state", StringType()))


def github_ops() -> Schema:
    return Schema(
        _f(1, "event_id", StringType(), True), _f(2, "installation_id", StringType(), True),
        _f(3, "epoch", StringType(), True), _f(4, "sequence", LongType(), True), _f(5, "operation_id", StringType(), True),
        _f(6, "phase", StringType(), True, "intent or result"), _f(7, "finding_key", StringType()),
        _f(8, "repo", StringType()), _f(9, "base_branch", StringType()), _f(10, "branch", StringType()),
        _f(11, "proposal_digest", StringType()), _f(12, "pr_number", LongType()), _f(13, "state", StringType()),
        _f(14, "at", TimestamptzType(), True), _f(15, "error", StringType()), _f(16, "raw_sha256", StringType()),
        _f(17, "observed_at", TimestamptzType(), True), _f(18, "ingested_at", TimestamptzType(), True))


def current_findings() -> Schema:
    return Schema(
        _f(1, "finding_key", StringType(), True), _f(2, "account_id", StringType()), _f(3, "region", StringType()),
        _f(4, "class_uid", IntegerType()), _f(5, "severity_id", IntegerType()), _f(6, "status_id", IntegerType()),
        _f(7, "priority", StringType()), _f(8, "issue_key", StringType()), _f(9, "title", StringType()),
        _f(10, "resource", _resource(100)), _f(11, "event_day", DateType()),
        _f(12, "watermark", _watermark(200), True), _f(13, "updated_at", TimestamptzType(), True),
        _f(14, "payload", StringType(), doc="Canonical CE finding JSON for the board view"))


def current_fixes() -> Schema:
    return Schema(
        _f(1, "finding_key", StringType(), True), _f(2, "state", StringType()), _f(3, "owner", StringType()),
        _f(4, "pr_url", StringType()), _f(5, "proof", StringType()), _f(6, "last_check", StringType()),
        _f(7, "changed_at", TimestamptzType()), _f(8, "watermark", _watermark(100), True),
        _f(9, "updated_at", TimestamptzType(), True))


def current_decisions() -> Schema:
    return Schema(
        _f(1, "finding_key", StringType(), True), _f(2, "status", StringType()), _f(3, "reason", StringType()),
        _f(4, "by", StringType()), _f(5, "at", TimestamptzType()), _f(6, "watermark", _watermark(100), True),
        _f(7, "updated_at", TimestamptzType(), True))


def current_operations() -> Schema:
    return Schema(
        _f(1, "operation_id", StringType(), True), _f(2, "finding_key", StringType()), _f(3, "phase", StringType()),
        _f(4, "state", StringType()), _f(5, "branch", StringType()), _f(6, "pr_number", LongType()),
        _f(7, "updated_at", TimestamptzType(), True), _f(8, "watermark", _watermark(100), True),
        _f(9, "repo", StringType()), _f(10, "base_branch", StringType()), _f(11, "proposal_digest", StringType()))


def campaigns() -> Schema:
    """One row per campaign version: the scope is the digest, the approval names the person who froze it."""
    return Schema(
        _f(1, "campaign_id", StringType(), True), _f(2, "version", LongType(), True), _f(3, "title", StringType()),
        _f(4, "status", StringType(), True), _f(5, "membership_digest", StringType(), True),
        _f(6, "member_count", LongType(), True), _f(7, "derivation_version", StringType()),
        _f(8, "approved_by", StringType()), _f(9, "approved_at", TimestamptzType()),
        _f(10, "approval_digest", StringType()), _f(11, "created_at", TimestamptzType(), True),
        _f(12, "updated_at", TimestamptzType(), True))


def campaign_members() -> Schema:
    """Complete membership, one row per target per version. `ordinal` is the pagination cursor."""
    return Schema(
        _f(1, "campaign_id", StringType(), True), _f(2, "version", LongType(), True),
        _f(3, "ordinal", LongType(), True, "stable position inside this version"),
        _f(4, "target_id", StringType(), True), _f(5, "finding_key", StringType()),
        _f(6, "target_kind", StringType(), True), _f(7, "account_id", StringType()), _f(8, "region", StringType()),
        _f(9, "resource_id", StringType()), _f(10, "resource_generation", StringType()),
        _f(11, "state", StringType(), True), _f(12, "evidence_sha256", StringType()),
        _f(13, "added_at", TimestamptzType(), True))


def deployment_receipts() -> Schema:
    """Receipts from existing CI/CD: separate facts per kind, with the producer and evidence that vouched for them."""
    return Schema(
        _f(1, "receipt_id", StringType(), True), _f(2, "identity", StringType(), True),
        _f(3, "kind", StringType(), True), _f(4, "producer", StringType(), True),
        _f(5, "external_id", StringType(), True), _f(6, "status", StringType(), True), _f(7, "reason", StringType()),
        _f(8, "plan_digest", StringType()), _f(9, "proposal", StringType()), _f(10, "campaign_id", StringType()),
        _f(11, "campaign_version", LongType()), _f(12, "target_id", StringType()),
        _f(13, "target_generation", StringType()), _f(14, "account_id", StringType()), _f(15, "repo", StringType()),
        _f(16, "commit", StringType()), _f(17, "artifact_digest", StringType()),
        _f(18, "deployment_revision", StringType()), _f(19, "actor", StringType()),
        _f(20, "payload_digest", StringType(), True), _f(21, "evidence_sha256", StringType()),
        _f(22, "observed_at", TimestamptzType(), True), _f(23, "received_at", TimestamptzType(), True),
        _f(24, "payload", StringType(), doc="Canonical receipt payload as the producer sent it"))


def relationships() -> Schema:
    """Typed subject/predicate/object assertions with validity, evidence and how they were learned."""
    return Schema(
        _f(1, "assertion_id", StringType(), True), _f(2, "subject_key", StringType(), True),
        _f(3, "subject_kind", StringType(), True), _f(4, "subject_scope", StringType()),
        _f(5, "subject_identity", StringType(), True), _f(6, "predicate", StringType(), True),
        _f(7, "object_key", StringType(), True), _f(8, "object_kind", StringType(), True),
        _f(9, "object_scope", StringType()), _f(10, "object_identity", StringType(), True),
        _f(11, "status", StringType(), True), _f(12, "valid_from", TimestamptzType()),
        _f(13, "valid_to", TimestamptzType()), _f(14, "recorded_at", TimestamptzType(), True),
        _f(15, "evidence", StringType()), _f(16, "derivation", StringType()), _f(17, "supersedes", StringType()))


def target_verifications() -> Schema:
    """One row per proof attempt, bound to its target generation, artifact, predicate version and verifier."""
    return Schema(
        _f(1, "attempt_id", StringType(), True), _f(2, "predicate_id", StringType(), True),
        _f(3, "predicate_version", StringType(), True), _f(4, "predicate_digest", StringType(), True),
        _f(5, "rule", StringType(), True), _f(6, "installation_id", StringType(), True),
        _f(7, "target_id", StringType(), True), _f(8, "account_id", StringType()), _f(9, "region", StringType()),
        _f(10, "resource_generation", StringType()), _f(11, "artifact_digest", StringType()),
        _f(12, "verifier", StringType(), True), _f(13, "outcome", StringType(), True),
        _f(14, "verified", BooleanType(), True), _f(15, "reason", StringType()),
        _f(16, "evidence_sha256", StringType()), _f(17, "truncated", BooleanType()), _f(18, "partial", BooleanType()),
        _f(19, "clock_skew_seconds", LongType()), _f(20, "provider_acknowledged", BooleanType()),
        _f(21, "observed_at", TimestamptzType(), True), _f(22, "received_at", TimestamptzType(), True))


def computation_receipts() -> Schema:
    """One row per run of an approved computation: bindings, pinned inputs, output and the attestation verdict."""
    return Schema(
        _f(1, "receipt_id", StringType(), True), _f(2, "computation", StringType(), True),
        _f(3, "computation_version", StringType(), True), _f(4, "contract_digest", StringType(), True),
        _f(5, "code_digest", StringType(), True), _f(6, "knowledge_version", StringType()),
        _f(7, "installation_id", StringType()), _f(8, "campaign_id", StringType()),
        _f(9, "campaign_version", LongType()), _f(10, "params", StringType(), doc="JSON typed parameters"),
        _f(11, "snapshot_id", LongType(), True, "Pinned input snapshot"),
        _f(12, "output", StringType(), doc="JSON structured output"),
        _f(13, "output_digest", StringType(), True), _f(14, "attested", BooleanType(), True),
        _f(15, "result", StringType(), True, "authoritative or failed_attestation"),
        _f(16, "problems", StringType(), doc="JSON reasons the attestation failed"),
        _f(17, "counts", StringType(), doc="JSON counts as computed, authoritative only when attested"),
        _f(18, "executed_at", TimestamptzType()), _f(19, "recorded_at", TimestamptzType(), True))


TABLES = {
    "findings": findings,
    "signals": signals,
    "scan_runs": scan_runs,
    "coverage": coverage,
    "decisions": decisions,
    "fix_events": fix_events,
    "verification_attempts": verification_attempts,
    "github_ops": github_ops,
    "current_findings": current_findings,
    "current_fixes": current_fixes,
    "current_decisions": current_decisions,
    "current_operations": current_operations,
    "campaigns": campaigns,
    "campaign_members": campaign_members,
    "deployment_receipts": deployment_receipts,
    "relationships": relationships,
    "target_verifications": target_verifications,
    "computation_receipts": computation_receipts,
}
TABLE_DOCS = {
    "findings": "OCSF 1.9.0 findings, one row per observation; authority for what AWS reported",
    "signals": "CloudWatch alarms and AWS Health events that are not findings",
    "scan_runs": "One row per completed scan run: scope, counts, truncation",
    "coverage": "What was inspected per account, region and source, and what was not",
    "decisions": "Human decisions, committed before they are acknowledged",
    "fix_events": "Fix lifecycle changes derived from scans and proof attempts",
    "verification_attempts": "Every proof attempt, including failures and inconclusive results",
    "github_ops": "GitHub operation intents and results",
    "current_findings": "Small current-state table for fast rebuild",
    "current_fixes": "Current fix records for fast rebuild",
    "current_decisions": "Current decisions for fast rebuild",
    "current_operations": "Open GitHub operations for recovery",
    "campaigns": "Campaign versions: scope digest, member count and the approval that froze them",
    "campaign_members": "Complete campaign membership per version; ordinal is the pagination cursor",
    "deployment_receipts": "PR, merge, build, deploy and verification receipts from existing CI/CD, kept as separate facts",
    "relationships": "Typed, scoped, time-aware edges with evidence or an approved derivation",
    "target_verifications": "Every proof attempt bound to its target generation, artifact, rule version and verifier",
    "computation_receipts": "One row per approved computation run: code and contract digest, pinned input snapshot, output and attestation verdict",
}
PARTITION_COLUMNS = {
    "findings": ("account_id", "region", "class_uid", "event_day"),
    "signals": ("account_id", "source"),
    "coverage": ("account_id", "source"),
    "current_findings": ("account_id",),
    "campaign_members": ("account_id",),
}


def schema(name: str) -> Schema:
    try:
        return TABLES[name]()
    except KeyError as exc:
        raise KeyError(f"unknown CE table {name!r}") from exc


def partition_spec(name: str) -> PartitionSpec:
    table_schema = schema(name)
    by_name = {field.name: field for field in table_schema.fields}
    fields = []
    for index, column in enumerate(PARTITION_COLUMNS.get(name, ())):
        if column not in by_name:
            raise SchemaMismatch(f"{name} has no partition column {column!r}")
        fields.append(PartitionField(source_id=by_name[column].field_id, field_id=1000 + index,
                                     transform=IdentityTransform(), name=column))
    return PartitionSpec(*fields)


def expected_properties() -> dict:
    return {"ce.schema_version": str(TABLE_SCHEMA_VERSION), "ce.ocsf.version": OCSF_VERSION}


def _type_problems(existing, expected) -> list[str]:
    """Compare types structurally: PyIceberg may renumber field IDs when a table is created."""
    if type(existing) is not type(expected):
        return [f"{existing} is not {expected}"]
    if isinstance(expected, StructType):
        problems = []
        have = {field.name: field for field in existing.fields}
        for field in expected.fields:
            if field.name not in have:
                if field.required:
                    problems.append(f"missing required field {field.name}")
                continue
            current = have[field.name]
            problems.extend(f"{field.name}.{item}" for item in _type_problems(current.field_type, field.field_type))
            if field.required and not current.required:
                problems.append(f"{field.name} must be required")
        return problems
    if isinstance(expected, ListType):
        return _type_problems(existing.element_field.field_type, expected.element_field.field_type)
    if isinstance(expected, MapType):
        return (_type_problems(existing.key_field.field_type, expected.key_field.field_type) +
                _type_problems(existing.value_field.field_type, expected.value_field.field_type))
    return []


def schema_problems(existing: Schema, expected: Schema) -> list[str]:
    """Required fields exist with a compatible type; extra optional fields are accepted evolution."""
    problems = []
    have = {field.name: field for field in existing.fields}
    for field in expected.fields:
        if field.name not in have:
            if field.required:
                problems.append(f"missing required column {field.name}")
            continue
        current = have[field.name]
        problems.extend(f"{field.name}.{item}" for item in _type_problems(current.field_type, field.field_type))
        if field.required and not current.required:
            problems.append(f"{field.name} must be required")
    return problems


def create_tables(catalog, namespace: str = "remedigenius", *, dry_run: bool = False) -> dict:
    """Create missing tables and verify existing ones. Never overwrite a table or a schema."""
    from pyiceberg.exceptions import NoSuchNamespaceError

    if dry_run:
        return {"namespace": namespace, "tables": {name: "planned" for name in TABLES}}
    try:
        catalog.load_namespace_properties(namespace)
    except NoSuchNamespaceError:
        catalog.create_namespace(namespace)
    existing = set(catalog.list_tables(namespace))
    result = {"namespace": namespace, "created": [], "verified": []}
    for name in TABLES:
        identifier = f"{namespace}.{name}"
        if identifier in existing or (namespace, name) in existing:
            problems = schema_problems(catalog.load_table(identifier).schema(), schema(name))
            if problems:
                raise SchemaMismatch(f"{identifier}: {'; '.join(problems)}")
            result["verified"].append(name)
        else:
            catalog.create_table_if_not_exists(identifier, schema=schema(name),
                                               partition_spec=partition_spec(name),
                                               properties=expected_properties())
            result["created"].append(name)
    return result


def pyarrow_schema(name: str, table_schema: Schema | None = None):
    """The Arrow schema for writing rows.

    Pass the schema loaded from the table: Iceberg assigns its own field IDs on create, and an Arrow table
    built from the declared schema would not match them.
    """
    from pyiceberg.io.pyarrow import schema_to_pyarrow

    return schema_to_pyarrow(table_schema or schema(name))