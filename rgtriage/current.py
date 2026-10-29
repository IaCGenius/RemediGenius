"""Current-state tables in Iceberg and cache rebuild (roadmap CE-10).

After a committed scan or human action, small current-state tables are overwritten with the facts and the watermark
they reflect. A new instance reads those tables for a fast rebuild instead of replaying all history. The Hermes home
keeps its existing checkpoint; the desk's facts no longer depend on restoring a desk home.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from . import contracts, ocsf


def _mark(mark, *, string: bool = False) -> dict:
    """Iceberg wants a datetime for the watermark struct; the cache view stores the canonical string."""
    data = mark.as_dict() if isinstance(mark, contracts.Watermark) else dict(mark)
    value = data.get("committed_at")
    if string:
        if isinstance(value, datetime):
            data["committed_at"] = contracts.format_time(value)
    elif isinstance(value, str):
        data["committed_at"] = contracts.parse_time(value)
    return data


def _at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        return contracts.parse_time(str(value))
    except contracts.ContractError:
        return None


def _json(value) -> str:
    return "" if value is None else (value if isinstance(value, str) else contracts.canonical_json(value))


def _plain(value):
    """Iceberg rows carry datetimes; cache views are JSON. Convert them without losing structure."""
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def _resource(finding: dict) -> dict:
    resource = finding.get("resource") or {}
    tags = resource.get("tags") or {}
    if isinstance(tags, list):
        tags = {str(item.get("key")): str(item.get("value")) for item in tags if isinstance(item, dict)}
    return {"uid": str(resource.get("id") or resource.get("name") or ""),
            "type": str(resource.get("type") or ""), "name": str(resource.get("name") or ""),
            "region": str(finding.get("region") or ""), "account_uid": str(finding.get("account") or ""),
            "tags": {str(key): str(value) for key, value in (tags or {}).items()}, "data": None}


def _day(finding: dict, fallback: datetime) -> date:
    seen = _at(finding.get("last_seen")) or _at(finding.get("first_seen")) or fallback
    return seen.date()


class CurrentState:
    def __init__(self, storage, cache):
        self.storage = storage
        self.cache = cache

    def refresh_from_scan(self, scan: dict, decisions: dict, mark) -> dict:
        watermark = _mark(mark)
        now = datetime.now(timezone.utc)
        fallback = _at(watermark.get("committed_at")) or now
        issues = scan.get("issues") or []
        findings = []
        for finding in scan.get("findings") or []:
            issue_key = next((issue.get("issue_key", "") for issue in issues
                              if finding.get("key") in (issue.get("finding_keys") or [])
                              or issue.get("top_key") == finding.get("key")), "")
            findings.append({
                "finding_key": str(finding.get("key") or ""), "account_id": str(finding.get("account") or ""),
                "region": str(finding.get("region") or ""), "class_uid": ocsf.class_for(finding),
                "severity_id": ocsf.severity_id(finding.get("severity", "")),
                "status_id": ocsf.status_id(finding.get("workflow") or "NEW"),
                "priority": finding.get("priority"), "issue_key": issue_key, "title": finding.get("title"),
                "resource": _resource(finding), "event_day": _day(finding, fallback),
                "watermark": watermark, "updated_at": now, "payload": contracts.canonical_json(finding),
            })
        fixes = [{"finding_key": record.get("key", ""), "state": record.get("state"), "owner": record.get("owner"),
                  "pr_url": record.get("pr"), "proof": _json(record.get("proof")),
                  "last_check": _json(record.get("last_check")),
                  "changed_at": _at(record.get("changed_at")), "watermark": watermark, "updated_at": now}
                 for record in (scan.get("fixes") or [])]
        decision_rows = [{"finding_key": key, "status": value.get("status"), "reason": value.get("reason"),
                          "by": value.get("by"), "at": _at(value.get("at")), "watermark": watermark,
                          "updated_at": now}
                         for key, value in decisions.items()]
        operations = self._open_operations(watermark, now)
        return {
            "current_findings": self.storage.overwrite_rows(
                "current_findings", findings, snapshot_properties={"ce.current": "findings"}),
            "current_fixes": self.storage.overwrite_rows(
                "current_fixes", fixes, snapshot_properties={"ce.current": "fixes"}),
            "current_decisions": self.storage.overwrite_rows(
                "current_decisions", decision_rows, snapshot_properties={"ce.current": "decisions"}),
            "current_operations": self.storage.overwrite_rows(
                "current_operations", operations, snapshot_properties={"ce.current": "operations"}),
        }

    def _open_operations(self, watermark: dict, now: datetime) -> list[dict]:
        rows = self.storage.scan_rows("github_ops")
        intents = {}
        results = set()
        for row in rows:
            operation = row.get("operation_id")
            if row.get("phase") == "intent":
                intents[operation] = row
            elif row.get("phase") == "result":
                results.add(operation)
        return [{"operation_id": operation, "finding_key": row.get("finding_key"), "phase": "intent",
                 "state": row.get("state"), "branch": row.get("branch"), "pr_number": row.get("pr_number"),
                 "updated_at": now, "watermark": watermark}
                for operation, row in intents.items() if operation not in results]

    def rebuild_cache(self, mark=None) -> dict:
        """Write the current tables into the SQLite views; the caller starts a new recovery epoch (CE-11)."""
        findings = self.storage.scan_rows("current_findings")
        fixes = self.storage.scan_rows("current_fixes")
        decisions = self.storage.scan_rows("current_decisions")
        operations = self.storage.scan_rows("current_operations")
        if mark is None:
            for row in (*findings, *fixes, *decisions, *operations):
                if row.get("watermark"):
                    mark = row["watermark"]
                    break
        watermark = _mark(mark, string=True) if mark else None
        payloads = {"current_findings": [json.loads(row["payload"]) for row in findings if row.get("payload")],
                    "current_fixes": _plain(fixes), "current_decisions": _plain(decisions),
                    "current_operations": _plain(operations)}
        for name, rows in payloads.items():
            self.cache.put_view(name, {"findings": rows} if name == "current_findings" else rows,
                                watermark=watermark)
        return {"watermark": watermark, "current_findings": len(findings), "current_fixes": len(fixes),
                "current_decisions": len(decisions), "current_operations": len(operations)}