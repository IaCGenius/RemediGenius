"""Local state: the latest scan, scan history and operator decisions (plain JSON files)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

DECISION_STATUSES = ("acknowledged", "investigating", "fixing", "accepted_risk", "false_positive", "suppressed", "resolved")

_REPOSITORY = None


def use(repository) -> None:
    """Route reads and writes through the durable repository (v0.5.0)."""
    global _REPOSITORY
    _REPOSITORY = repository


def repository():
    return _REPOSITORY


def _write(path: Path, data, compact: bool = False) -> None:
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")  # concurrent scans must not share a temp file
    text = json.dumps(data, separators=(",", ":"), default=str) if compact else json.dumps(data, indent=1, default=str)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def latest_path() -> Path:
    return config.home() / "latest.json"


def load_latest() -> dict | None:
    return _REPOSITORY.load_latest() if _REPOSITORY is not None else _read(latest_path(), None)


def load_decisions() -> dict:
    return _REPOSITORY.load_decisions() if _REPOSITORY is not None else _read(config.home() / "decisions.json", {})


def save_decision(key: str, status: str, reason: str, by: str = "operator", fix: dict | None = None) -> dict:
    if status not in DECISION_STATUSES:
        raise ValueError(f"status must be one of {', '.join(DECISION_STATUSES)}")
    if _REPOSITORY is not None:
        return _REPOSITORY.decide(key, status, reason, by, fix)
    decisions = load_decisions()
    previous = decisions.get(key) or {}
    decisions[key] = {"status": status, "reason": reason, "by": by,
                      "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if fix or previous.get("fix"):  # a fix record survives later decisions on the same finding
        decisions[key]["fix"] = fix or previous["fix"]
    _write(config.home() / "decisions.json", decisions)
    return decisions[key]


NEW_GRACE = timedelta(hours=2)


def _origin(f: dict) -> tuple:
    src = f.get("collected_from") or [f["source"], f["account"], f["region"]]
    return tuple(src)


def _coverage(scan: dict | None) -> dict:
    return {(c["source"], c.get("account_id"), c["region"]): c for c in (scan or {}).get("coverage", [])}


def coverage_complete(entry: dict | None) -> bool:
    """One predicate for "this read could have seen the finding".

    Status must be ok, the page must not be truncated or capped, and a recorded completeness must say ok. A legacy
    entry without a completeness field falls back to status + truncation; an explicit unknown is not complete.
    """
    if not entry or entry.get("status") != "ok" or entry.get("truncated"):
        return False
    completeness = entry.get("completeness")
    if completeness is not None:
        return str(completeness) in ("ok", "complete")
    return True


def _time(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def mark_changes(scan: dict) -> dict:
    """Mark findings new since the previous scan and record those no longer active.

    Stays truthful at volume: a source that just became readable is a baseline, not N "new" findings;
    for capped (truncated) sources a finding is new only if it was first seen after the previous scan,
    and nothing is called "no longer active" unless both scans read that source completely.
    """
    previous = load_latest()
    prev_keys = {f["key"]: f for f in (previous or {}).get("findings", [])}
    prev_cov, cur_cov = _coverage(previous), _coverage(scan)
    prev_time = _time((previous or {}).get("scanned_at"))
    cur_keys = {f["key"] for f in scan["findings"]}
    for f in scan["findings"]:
        before = prev_cov.get(_origin(f))
        if previous is None or f["key"] in prev_keys or not before or before.get("status") != "ok":
            f["new"] = False
        elif before.get("truncated") or previous.get("stored_overflow"):
            seen = _time(f.get("first_seen"))
            f["new"] = bool(seen and prev_time and seen >= prev_time - NEW_GRACE)
        else:
            f["new"] = True
    resolved = []
    for k, f in prev_keys.items():
        origin = _origin(f)
        now, before = cur_cov.get(origin, {}), prev_cov.get(origin, {})
        if (k not in cur_keys and coverage_complete(now) and coverage_complete(before)
                and not scan.get("stored_overflow")):
            resolved.append({"key": k, "title": f["title"], "priority": f.get("priority"), "resource": f["resource"].get("name")})
    baselines = [{"source": c["source"], "account": c["account"], "region": c["region"],
                  "total": c.get("total", c.get("count", 0))}
                 for key, c in cur_cov.items()
                 if previous is not None and c["status"] == "ok" and (prev_cov.get(key) or {}).get("status") != "ok"]
    scan["changes"] = {
        "previous_scan": (previous or {}).get("scanned_at"),
        "new": sum(1 for f in scan["findings"] if f["new"]),
        "new_urgent": sum(1 for f in scan["findings"] if f["new"] and f["priority"] in ("P1", "P2")),
        "no_longer_active": resolved[:50],
        "no_longer_active_count": len(resolved),
        "new_sources": baselines,
    }
    return scan


def cap_findings(scan: dict, limit: int) -> None:
    """Keep the top `limit` ranked findings on disk; count the rest (findings must already be sorted)."""
    overflow = len(scan["findings"]) - limit
    if overflow > 0:
        scan["findings"] = scan["findings"][:limit]
    scan["stored_overflow"] = max(0, overflow)


def save_scan(scan: dict, run=None) -> dict:
    """Commit the scan to durable storage, or (legacy/test path only) write latest.json."""
    if _REPOSITORY is not None:
        return _REPOSITORY.save_scan(scan, run)
    # Legacy path: latest.json (compact), a small status file and a history of key->priority snapshots.
    history = config.home() / "history"
    history.mkdir(exist_ok=True)
    stamp = scan["scanned_at"].replace(":", "").replace("-", "")
    _write(history / f"scan-{stamp}.json", {
        "scanned_at": scan["scanned_at"], "changes": scan.get("changes"),
        "priorities": {f["key"]: f["priority"] for f in scan["findings"]},
        "coverage": [{k: c.get(k) for k in ("source", "account", "region", "status", "count", "total", "truncated")}
                     for c in scan["coverage"]]}, compact=True)
    for old in sorted(history.glob("scan-*.json"))[:-60]:
        old.unlink()
    _write(latest_path(), scan, compact=True)
    return scan


def write_latest(scan: dict) -> None:
    if _REPOSITORY is not None:
        return _REPOSITORY.write_latest(scan)
    _write(latest_path(), scan, compact=True)


def persist_decisions(decisions: dict) -> None:
    if _REPOSITORY is not None:
        return _REPOSITORY.persist_decisions(decisions)
    _write(config.home() / "decisions.json", decisions)


def find(scan: dict, ref: str) -> dict | None:
    """Look up a finding by key, key prefix, native id or issue key."""
    for f in scan.get("findings", []):
        if ref in (f["key"], f["native_id"]):
            return f
    for issue in scan.get("issues", []):
        if ref == issue["issue_key"]:
            return next((f for f in scan["findings"] if f["key"] == issue["top_key"]), None)
    matches = [f for f in scan.get("findings", []) if f["key"].startswith(ref)]
    return matches[0] if len(matches) == 1 else None


def load_onboarding() -> dict | None:
    return _REPOSITORY.load_onboarding() if _REPOSITORY is not None else _read(config.home() / "onboarding.json", None)


def save_onboarding(report: dict, profile: dict) -> None:
    """Keep the last onboarding report; `readable` lets investigations reach discovered accounts between scans."""
    if _REPOSITORY is not None:
        return _REPOSITORY.save_onboarding(report, profile)
    readable = {a["account_id"]: a["name"] for a in profile["accounts"] if a.get("discovered")}
    _write(config.home() / "onboarding.json", {**report, "readable": readable})


def discovered_accounts(profile: dict) -> list[dict]:
    report = load_onboarding() or {}
    org, primary = profile["organization"], (profile["accounts"] or [{}])[0]
    return [{"name": name, "account_id": account_id, "regions": profile["regions"], "criticality": org["criticality"],
             "role_arn": f"arn:aws:iam::{account_id}:role/{org['member_role_name']}", "aws_profile": primary.get("aws_profile")}
            for account_id, name in (report.get("readable") or {}).items()]
