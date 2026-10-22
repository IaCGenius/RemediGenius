"""Fix records: a decision to fix, carried to verified closure by evidence.

A record exists only when the user decides to fix (decide status=fixing). It holds the owner, the PR link and a
**proof of done** defined before the fix: one read-only AWS call and the values it must return. At every scan the
desk advances the record from evidence: decided → PR linked → deployed (proof passes, AWS finding still open) →
verified (proof passes and the AWS finding is gone or passed); a verified fix whose finding returns is reopened;
a record without progress for STALL_DAYS is stalled. The desk never applies a change.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from . import aws, store

STALL_DAYS = 7
STATES = ("decided", "pr", "deployed", "verified", "reopened", "stalled")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(data, path: str):
    """`PublicAccessBlockConfiguration.BlockPublicPolicy` or `Items.0.Name` inside an API response."""
    for part in path.split("."):
        if isinstance(data, list):
            data = data[int(part)] if part.isdigit() and int(part) < len(data) else None
        elif isinstance(data, dict):
            data = data.get(part)
        else:
            return None
    return data


def check_proof(proof: dict, account: dict, region: str) -> dict:
    """Run the proof read and compare. Returns {passed, observed, error}."""
    service, op = proof["service"], proof["operation"].replace("-", "_")
    if not aws.is_read_operation(aws.snake_to_pascal(op)):
        return {"passed": False, "error": f"{op} is not a read-only operation"}
    recorded = os.environ.get("RGTRIAGE_EVAL_AWS")
    try:
        if recorded:
            path = Path(recorded) / f"{service}.{op}.json"
            result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        else:
            client = aws.client(aws.session_for(account, region), service, region)
            result = getattr(client, op)(**(proof.get("parameters") or {}))
    except (ClientError, BotoCoreError, aws.WriteBlocked, AttributeError) as exc:
        return {"passed": False, "error": str(exc)[:240]}
    observed = {k: _get(result, k) for k in (proof.get("expect") or {})}
    return {"passed": bool(observed) and all(observed[k] == v for k, v in proof["expect"].items()), "observed": observed}


def advance(scan: dict, profile: dict, decisions: dict | None = None, check=check_proof) -> list[dict]:
    """Move every fix record forward from the evidence in this scan. Returns the records (for the board)."""
    decisions = store.load_decisions() if decisions is None else decisions
    by_key = {f["key"]: f for f in scan.get("findings", [])}
    accounts = {str(a.get("account_id")): a for a in profile.get("accounts", [])}
    changed, records = False, []
    now = datetime.now(timezone.utc)
    for key, d in decisions.items():
        fix = d.get("fix")
        if not fix:
            continue
        finding = by_key.get(key)
        if finding is not None:
            active = str(finding.get("workflow", "NEW")).upper() not in ("RESOLVED", "SUPPRESSED")
        else:  # gone from the scan counts as fixed only if that source was actually read there this time
            active = not any(c["status"] == "ok" and c["source"] == fix.get("source") and c["region"] == fix.get("region")
                             and str(c.get("account_id")) == str(fix.get("account")) for c in scan.get("coverage", []))
        state = fix.get("state", "decided")
        if d["status"] == "resolved" and state == "verified" and active:
            fix.update(state="reopened", reopened_at=_now())
            d["status"] = "fixing"
            changed = True
        elif d["status"] == "fixing":
            result = None
            if fix.get("proof"):
                account = accounts.get(str((finding or {}).get("account") or fix.get("account"))) or \
                    (profile.get("accounts") or [{}])[0]
                result = check(fix["proof"], account, (finding or {}).get("region") or fix.get("region") or "us-east-1")
                fix["last_check"] = {"at": _now(), **result}
            new = state
            if result and result.get("passed"):
                new = "verified" if not active else "deployed"
            elif fix.get("pr") and state in ("decided", "stalled"):
                new = "pr"
            since = fix.get("changed_at") or d.get("at")
            if new == state and state not in ("verified",) and since and \
                    now - datetime.fromisoformat(since.replace("Z", "+00:00")) > timedelta(days=STALL_DAYS):
                new = "stalled"
            if new != state:
                fix.update(state=new, changed_at=_now())
                changed = True
            if new == "verified":
                d.update(status="resolved", reason=f"verified: proof of done passed at {fix['last_check']['at']} "
                                                   f"and the finding is no longer active ({d.get('reason', '')})"[:500])
        records.append({"key": key, "status": d["status"], **fix,
                        "title": (finding or {}).get("title") or fix.get("title", ""),
                        "resource": ((finding or {}).get("resource") or {}).get("name") or fix.get("resource", "")})
    if changed:
        store._write(store.config.home() / "decisions.json", decisions)
    return records


def board_line(records: list[dict]) -> str:
    if not records:
        return ""
    counts = {s: sum(1 for r in records if r.get("state") == s) for s in STATES}
    parts = [f"{counts[s]} {label}" for s, label in (("decided", "decided"), ("pr", "in PR"), ("deployed", "deployed, awaiting AWS"),
                                                     ("verified", "verified"), ("reopened", "reopened"), ("stalled", "stalled"))
             if counts[s]]
    owners = sorted({r.get("owner") for r in records if r.get("state") == "stalled" and r.get("owner")})
    return f"Fixes in flight: {', '.join(parts)}" + (f" (stalled: {', '.join(owners)})" if owners else "")
