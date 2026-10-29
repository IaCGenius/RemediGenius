"""Map collected findings to OCSF 1.9.0 and build Iceberg rows (roadmap CE-24).

OCSF is the open schema for what AWS reported. Desk concepts that OCSF does not define live in a documented
CE extension under ``unmapped.ce``, next to the residual source fields under ``unmapped.fields``. The raw
object in S3 remains the authoritative bytes; nothing is dropped silently.

Security Hub v2 exposure findings are already OCSF. They are validated and stored as AWS wrote them, with only
the CE extension added. Desks signals that are not findings (CloudWatch alarms, AWS Health events) go to CE's
``signals`` table instead.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from . import contracts

OCSF_VERSION = "1.9.0"
CATEGORY_FINDINGS = 2
CLASS_FINDING = 2001
CLASS_VULNERABILITY_FINDING = 2002
CLASS_COMPLIANCE_FINDING = 2003
CLASS_DETECTION_FINDING = 2004
CLASS_NAMES = {
    CLASS_FINDING: "Finding",
    CLASS_VULNERABILITY_FINDING: "Vulnerability Finding",
    CLASS_COMPLIANCE_FINDING: "Compliance Finding",
    CLASS_DETECTION_FINDING: "Detection Finding",
}

ACTIVITY_UNKNOWN = 0
ACTIVITY_CREATE = 1
ACTIVITY_UPDATE = 2
ACTIVITY_CLOSE = 3

SEVERITY_IDS = {"INFORMATIONAL": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5, "FATAL": 6}
STATUS_IDS = {"NEW": 1, "NOTIFIED": 1, "IN_PROGRESS": 2, "INVESTIGATING": 2, "SUPPRESSED": 3, "RESOLVED": 4, "CLOSED": 4}
COMPLIANCE_UNKNOWN, COMPLIANCE_PASS, COMPLIANCE_WARNING, COMPLIANCE_FAIL, COMPLIANCE_NOT_APPLICABLE = 0, 1, 2, 3, 4

# Reviewed mapping table. Security Hub is refined per finding category below.
SOURCE_CLASS = {
    "inspector": CLASS_VULNERABILITY_FINDING,
    "guardduty": CLASS_DETECTION_FINDING,
    "accessanalyzer": CLASS_DETECTION_FINDING,
    "config": CLASS_COMPLIANCE_FINDING,
    "securityhub": CLASS_COMPLIANCE_FINDING,
}
SIGNAL_SOURCES = frozenset({"cloudwatch", "health"})
PASSTHROUGH_SOURCES = frozenset({"securityhub-exposure"})

MAPPED_KEYS = frozenset({
    "key", "source", "native_id", "product", "account", "region", "title", "description", "severity", "category",
    "type", "control_id", "resource", "first_seen", "last_seen", "workflow", "remediation", "console_url",
    "signals", "context", "collected_from", "priority", "reasons", "issue_key", "new", "ocsf",
})


class MappingError(ValueError):
    """A finding cannot be mapped without guessing."""


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _epoch_ms(value: Any) -> int | None:
    parsed = _dt(value)
    return int(parsed.timestamp() * 1000) if parsed else None


def _bounded(value: Any, limit: int = 4000) -> Any:
    try:
        text = json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return {"unserializable": str(value)[:limit]}
    return value if len(text) <= limit else {"truncated": text[:limit]}


def severity_id(severity: str) -> int:
    return SEVERITY_IDS.get(str(severity).upper(), 0)


def status_id(workflow: str) -> int:
    return STATUS_IDS.get(str(workflow).upper(), 0)


def class_for(finding: dict) -> int:
    source = str(finding.get("source", ""))
    if source in PASSTHROUGH_SOURCES:
        return int((finding.get("ocsf") or {}).get("class_uid") or CLASS_FINDING)
    if source == "securityhub":
        category = str(finding.get("category", ""))
        if category == "threat":
            return CLASS_DETECTION_FINDING
        if category == "vulnerability":
            return CLASS_VULNERABILITY_FINDING
    return SOURCE_CLASS.get(source, CLASS_FINDING)


def _account_uid(finding: dict) -> str:
    return str(finding.get("account") or (finding.get("resource") or {}).get("account") or "")


def _resources(finding: dict, region: str) -> list[dict]:
    resource = finding.get("resource") or {}
    uid = str(resource.get("id") or resource.get("name") or _account_uid(finding) or "unknown")
    tags = resource.get("tags") or {}
    if isinstance(tags, list):
        tags = {str(t.get("key")): str(t.get("value")) for t in tags if isinstance(t, dict)}
    item = {
        "uid": uid, "type": str(resource.get("type") or "AwsResource"),
        "name": str(resource.get("name") or uid), "region": region,
        "account_uid": _account_uid(finding), "tags": {str(k): str(v) for k, v in (tags or {}).items()},
        "data": _bounded(resource.get("details")) if resource.get("details") else None,
    }
    return [item]


def _finding_info(finding: dict) -> dict:
    return {
        "uid": str(finding.get("native_id") or finding.get("key") or ""),
        "title": str(finding.get("title") or "")[:1000],
        "desc": str(finding.get("description") or "")[:4000],
        "created_time": _epoch_ms(finding.get("first_seen")),
        "modified_time": _epoch_ms(finding.get("last_seen")),
        "first_seen_time": _epoch_ms(finding.get("first_seen")),
        "last_seen_time": _epoch_ms(finding.get("last_seen")),
        "types": [str(finding["type"])] if finding.get("type") else [],
    }


def _vulnerabilities(finding: dict, klass: int) -> list[dict]:
    if klass != CLASS_VULNERABILITY_FINDING:
        return []
    signals = finding.get("signals") or {}
    context = finding.get("context") or {}
    packages = context.get("packages") or []
    cve = str(finding.get("control_id") or "")
    rollup = context.get("rollup") or {}
    if not packages and not rollup and not cve.startswith("CVE-"):
        return []
    rows = []
    for package in packages or ([{}] if (rollup or cve.startswith("CVE-")) else []):
        rows.append({
            "uid": cve or str(finding.get("native_id") or ""),
            "cve_uid": cve if cve.startswith("CVE-") else "",
            "cve_desc": str(finding.get("title") or "")[:1000] if cve.startswith("CVE-") else "",
            "title": str(finding.get("title") or "")[:1000],
            "severity": str(finding.get("severity") or "MEDIUM"),
            "is_exploit_available": bool(signals.get("exploit_available")),
            "epss_score": float(signals["epss"]) if isinstance(signals.get("epss"), (int, float)) else None,
            "fix_available": bool(signals.get("fix_available")),
            "package_name": str(package.get("name") or ""),
            "package_version": str(package.get("installed") or package.get("version") or ""),
            "package_manager": str(package.get("manager") or ""),
        })
    return rows


def _compliance(finding: dict, klass: int) -> dict | None:
    if klass != CLASS_COMPLIANCE_FINDING:
        return None
    context = finding.get("context") or {}
    standards = context.get("standards") or []
    return {
        "status_id": COMPLIANCE_FAIL, "status": "Failed",
        "control": str(finding.get("control_id") or ""),
        "standards": [str(s) for s in standards],
        "requirements": [],
    }


def _residual_fields(finding: dict) -> dict:
    return {key: _bounded(value) for key, value in finding.items() if key not in MAPPED_KEYS}


def ce_extension(finding: dict, *, raw_ref: contracts.RawRef | None = None, priority: str | None = None,
                 reasons: list[str] | None = None, issue_key: str = "", coverage_status: str = "",
                 truncated: bool = False, mapping: str = "native", mapping_error: str = "") -> dict:
    return {
        "finding_key": str(finding.get("key") or ""),
        "source": str(finding.get("source") or ""),
        "priority": priority or finding.get("priority"),
        "reasons": list(reasons if reasons is not None else (finding.get("reasons") or [])),
        "issue_key": issue_key,
        "scope": {"account": _account_uid(finding), "region": str(finding.get("region") or ""),
                  "source": str(finding.get("source") or ""), "filter_hash": ""},
        "raw_sha256": raw_ref.sha256 if raw_ref else "",
        "raw_key": raw_ref.key if raw_ref else "",
        "observed_at": raw_ref.observed_at if raw_ref else "",
        "ingested_at": raw_ref.observed_at if raw_ref else "",
        "coverage_status": coverage_status,
        "truncated": bool(truncated),
        "mapping": mapping,
        "mapping_error": mapping_error,
    }


def passthrough(finding: dict, ce: dict) -> dict:
    original = finding.get("ocsf")
    if not isinstance(original, dict) or not original.get("class_uid"):
        raise MappingError("the original OCSF record was not retained; refusing to re-map an exposure finding")
    record = deepcopy(original)
    record.setdefault("metadata", {})
    record["metadata"]["version"] = record["metadata"].get("version") or OCSF_VERSION
    record.setdefault("category_uid", CATEGORY_FINDINGS)
    record.setdefault("severity_id", severity_id(finding.get("severity")))
    record.setdefault("status_id", status_id(finding.get("workflow") or "NEW"))
    record.setdefault("activity_id", ACTIVITY_UNKNOWN)
    record.setdefault("type_uid", int(record["class_uid"]) * 100 + int(record["activity_id"]))
    record.setdefault("finding_info", _finding_info(finding))
    record.setdefault("resources", _resources(finding, str(finding.get("region") or "")))
    record.setdefault("cloud", {"provider": "AWS", "region": str(finding.get("region") or ""),
                                "account_uid": _account_uid(finding)})
    record.setdefault("time", _epoch_ms(finding.get("last_seen") or finding.get("first_seen")))
    unmapped = record.get("unmapped")
    if not isinstance(unmapped, dict):
        unmapped = {"original": unmapped} if unmapped else {}
    unmapped["ce"] = ce
    record["unmapped"] = unmapped
    return record


def map_finding(finding: dict, ce: dict | None = None) -> dict:
    """Return an OCSF finding record. Unknown sources fall back to the base Finding class, never a guess."""
    source = str(finding.get("source") or "")
    if source in PASSTHROUGH_SOURCES:
        return passthrough(finding, ce or ce_extension(finding, mapping="passthrough"))
    klass = class_for(finding)
    mapping, error = "native", ""
    if source not in SOURCE_CLASS and source != "securityhub":
        klass, mapping, error = CLASS_FINDING, "fallback", f"no reviewed OCSF class for source {source!r}"
    if ce is None:
        ce = ce_extension(finding, mapping=mapping, mapping_error=error)
    else:
        ce = {**ce, "mapping": mapping, "mapping_error": error}
    region = str(finding.get("region") or "")
    activity = ACTIVITY_UNKNOWN
    record = {
        "metadata": {
            "version": OCSF_VERSION,
            "product": {"name": str(finding.get("product") or source), "vendor_name": "Amazon Web Services",
                        "feature_name": source},
        },
        "category_uid": CATEGORY_FINDINGS,
        "class_uid": klass,
        "class_name": CLASS_NAMES[klass],
        "activity_id": activity,
        "type_uid": klass * 100 + activity,
        "time": _epoch_ms(finding.get("last_seen") or finding.get("first_seen")),
        "severity_id": severity_id(finding.get("severity")),
        "status_id": status_id(finding.get("workflow") or "NEW"),
        "finding_info": _finding_info(finding),
        "cloud": {"provider": "AWS", "region": region, "account_uid": _account_uid(finding)},
        "resources": _resources(finding, region),
        "vulnerabilities": _vulnerabilities(finding, klass),
        "compliance": _compliance(finding, klass),
        "unmapped": {"ce": ce, "fields": _residual_fields(finding), "source_keys": sorted(finding.keys())},
    }
    return record


def validate_mapped(record: dict) -> list[str]:
    """Structural and enumerated checks for the pinned OCSF subset. Returns every problem, not the first."""
    problems = []
    for key in ("metadata", "category_uid", "class_uid", "activity_id", "type_uid", "time", "severity_id",
                "status_id", "finding_info", "cloud", "resources"):
        if key not in record:
            problems.append(f"missing {key}")
    if record.get("category_uid") != CATEGORY_FINDINGS:
        problems.append("category_uid must be 2 (Findings)")
    klass = record.get("class_uid")
    if klass not in CLASS_NAMES:
        problems.append(f"class_uid {klass!r} is not a pinned finding class")
    if record.get("metadata", {}).get("version") != OCSF_VERSION:
        problems.append(f"metadata.version must be {OCSF_VERSION}")
    if record.get("type_uid") != (klass or 0) * 100 + int(record.get("activity_id") or 0):
        problems.append("type_uid must be class_uid * 100 + activity_id")
    if not isinstance(record.get("severity_id"), int) or record["severity_id"] not in (0, 1, 2, 3, 4, 5, 6, 99):
        problems.append("severity_id is not a valid OCSF severity")
    if not isinstance(record.get("status_id"), int) or record["status_id"] not in (0, 1, 2, 3, 4, 5, 99):
        problems.append("status_id is not a valid OCSF status")
    info = record.get("finding_info") or {}
    if not info.get("uid") or not info.get("title"):
        problems.append("finding_info needs uid and title")
    for key in ("created_time", "modified_time", "first_seen_time", "last_seen_time"):
        value = info.get(key)
        if value is not None and not isinstance(value, int):
            problems.append(f"finding_info.{key} must be epoch milliseconds")
    if not isinstance(record.get("resources"), list) or not record["resources"]:
        problems.append("resources must be a non-empty list")
    return problems


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def finding_row(finding: dict, event: contracts.Event, raw_ref: contracts.RawRef | None = None, *,
                priority: str | None = None, reasons: list[str] | None = None, issue_key: str = "",
                coverage_status: str = "", truncated: bool = False) -> dict:
    """One row in the Iceberg ``findings`` table, shaped exactly like rgtriage.schemas.findings()."""
    ce = ce_extension(finding, raw_ref=raw_ref, priority=priority, reasons=reasons, issue_key=issue_key,
                      coverage_status=coverage_status, truncated=truncated, mapping="native")
    record = map_finding(finding, ce)
    if not record.get("time"):
        record["time"] = _epoch_ms(event.observed_at)
    observed = contracts.parse_time(event.observed_at)
    ocsf = _jsonable(record)
    ocsf["unmapped"] = contracts.canonical_json(ocsf.get("unmapped") or {})
    return {
        "event_id": event.event_id, "installation_id": event.installation_id, "epoch": event.epoch,
        "sequence": event.sequence, "account_id": _account_uid(finding), "region": str(finding.get("region") or ""),
        "class_uid": int(record["class_uid"]), "event_day": observed.date(),
        "observed_at": observed, "ingested_at": contracts.parse_time(event.ingested_at),
        "payload_hash": event.payload_hash, "raw_sha256": raw_ref.sha256 if raw_ref else "",
        "raw_key": raw_ref.key if raw_ref else "", "ocsf": ocsf,
        "ce": _jsonable(ce),
    }


def signal_row(finding: dict, event: contracts.Event, raw_ref: contracts.RawRef | None = None) -> dict:
    observed = contracts.parse_time(event.observed_at)
    return {
        "event_id": event.event_id, "installation_id": event.installation_id, "epoch": event.epoch,
        "sequence": event.sequence, "account_id": _account_uid(finding), "region": str(finding.get("region") or ""),
        "source": str(finding.get("source") or ""), "signal_type": str(finding.get("type") or ""),
        "severity_id": severity_id(finding.get("severity")),
        "status": str(finding.get("workflow") or ""), "title": str(finding.get("title") or "")[:1000],
        "first_seen": _dt(finding.get("first_seen")), "last_seen": _dt(finding.get("last_seen")),
        "observed_at": observed, "ingested_at": contracts.parse_time(event.ingested_at),
        "resource": _resources(finding, str(finding.get("region") or ""))[0],
        "detail": contracts.canonical_json(_residual_fields(finding)),
        "raw_sha256": raw_ref.sha256 if raw_ref else "", "raw_key": raw_ref.key if raw_ref else "",
    }


def row_for(finding: dict, event: contracts.Event, raw_ref: contracts.RawRef | None = None, **kwargs) -> tuple[str, dict]:
    """Which CE table this finding belongs to and its row."""
    if str(finding.get("source") or "") in SIGNAL_SOURCES:
        return "signals", signal_row(finding, event, raw_ref)
    return "findings", finding_row(finding, event, raw_ref, **kwargs)