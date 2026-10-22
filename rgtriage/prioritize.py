"""Deterministic, explainable prioritization.

Source severity is the starting point. Signals that change real-world risk move a
finding up or down, and every adjustment is written into `reasons` so the agent and
the user can see why something is P1 rather than trusting a black box.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .config import CRITICALITY_POINTS
from .knowledge import exception_for

SEVERITY_POINTS = {"CRITICAL": 60, "HIGH": 45, "MEDIUM": 25, "LOW": 10, "INFORMATIONAL": 0}
PRIORITY_THRESHOLDS = (("P1", 70), ("P2", 50), ("P3", 30))
PRIORITY_MEANING = {
    "P1": "act now (today)",
    "P2": "fix this week",
    "P3": "plan in the backlog",
    "P4": "monitor / accept",
}
PROD_VALUES = {"prod", "production", "prd", "live"}
NONPROD_VALUES = {"dev", "development", "test", "testing", "qa", "sandbox", "staging", "stage", "nonprod", "non-prod"}
# GuardDuty / threat types that mean an attacker may already be in.
HIGH_SIGNAL_THREATS = ("Backdoor:", "CryptoCurrency:", "Trojan:", "Exfiltration:", "Impact:", "CredentialAccess:",
                       "UnauthorizedAccess:IAMUser/InstanceCredentialExfiltration", "PrivilegeEscalation:", "Persistence:")


def _priority(score: int) -> str:
    for label, threshold in PRIORITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "P4"


def _parse_time(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def business_context(finding: dict, profile: dict, knowledge: dict | None = None) -> tuple[str, str, str | None]:
    """Return (criticality, why, application) for the finding's resource.

    Reviewed knowledge concepts come first (and are cited by path), then triage.yaml, then environment tags.
    """
    tags = {str(k): str(v) for k, v in (finding["resource"].get("tags") or {}).items()}
    for app in (knowledge or {}).get("applications", []):
        if all(tags.get(k) == v for k, v in app["tags"].items()):
            _cite(finding, app)
            return app["criticality"], f"application {app['title']}, knowledge {app['path']}{_stale(app)}", app["title"]
    for app in profile.get("applications", []):
        want = app.get("tags") or {}
        if want and all(tags.get(k) == str(v) for k, v in want.items()):
            return app.get("criticality", "business_critical"), f"application {app['name']}", app["name"]
    for key in profile.get("environment_tag_keys", []):
        value = tags.get(key, "").lower()
        if value in PROD_VALUES:
            return "business_critical", f"tag {key}={tags[key]}", None
        if value in NONPROD_VALUES:
            return "test_development", f"tag {key}={tags[key]}", None
    account_concept = (knowledge or {}).get("accounts", {}).get(finding["account"])
    if account_concept:
        _cite(finding, account_concept)
        return (account_concept["criticality"], f"account {account_concept['title']}, knowledge {account_concept['path']}"
                f"{_stale(account_concept)}", None)
    for account in profile.get("accounts", []):
        if account.get("account_id") == finding["account"]:
            return account.get("criticality", "business_critical"), f"account {account['name']}", None
    return "business_critical", "default", None


def _cite(finding: dict, concept: dict) -> None:
    used = finding.setdefault("knowledge", [])
    if concept["path"] not in used:
        used.append(concept["path"])
    if concept.get("owner") and not finding.get("owner"):
        finding["owner"] = concept["owner"]
        if concept["owner"].get("exists") and concept["owner"]["path"] not in used:
            used.append(concept["owner"]["path"])


def _stale(concept: dict) -> str:
    return " (stale: ask the owner to re-review it)" if concept.get("stale") else ""


def score_finding(finding: dict, profile: dict, now: datetime | None = None, knowledge: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    signals = finding.get("signals", {})
    reasons: list[str] = []
    score = SEVERITY_POINTS.get(finding["severity"], 10)
    if finding.get("category") == "vulnerability":
        # CVSS severity alone is not urgency: exploitability and exposure (below) decide P1.
        score = round(score * 0.75)
        reasons.append(f"{finding['product']} severity {finding['severity']} (+{score}, vulnerability: exploitability decides urgency)")
    else:
        reasons.append(f"{finding['product']} severity {finding['severity']} (+{score})")

    def add(points: int, why: str):
        nonlocal score
        score += points
        reasons.append(f"{why} ({'+' if points >= 0 else ''}{points})")

    if signals.get("attack_sequence"):
        add(25, "GuardDuty correlated several steps of one attack (attack sequence)")
    elif signals.get("active_threat"):
        if any(finding["type"].startswith(t) or t in finding["type"] for t in HIGH_SIGNAL_THREATS):
            add(20, "threat detection of possible compromise, exfiltration or impact")
        else:
            add(10, "threat detection: suspicious activity was observed, not just a misconfiguration")
    if signals.get("root_usage"):
        count = signals.get("event_count") or 0
        add(40 if count > 100 else 25 if count > 10 else 15, f"root credentials are being used ({count} API calls)")
    elif signals.get("identity_risk"):
        add(10, "identity/credential takeover risk")
    if signals.get("aws_exposure"):
        add(10, "AWS Security Hub exposure analysis correlated this risk (see its traits and attack path)")
    elif signals.get("public_exposure"):
        # A rule or policy that allows outside access; the desk did not trace a network path (#4: say what is known).
        add(15, "configuration allows access from outside the account (path not verified)")
    if signals.get("exploit_available"):
        add(12, "a public exploit exists for this vulnerability")
    if (signals.get("epss") or 0) >= 0.1:
        add(5, f"EPSS {signals['epss']:.2f}: likely to be exploited")
    if signals.get("detection_gap"):
        add(8, "detection/audit gap: you would not see an attack here")
    fleet = signals.get("fleet_findings") or 0
    if fleet >= 100:
        add(8 if fleet >= 1000 else 5, f"one fix clears {fleet:,} findings")
    if signals.get("fix_available"):
        add(3, "a vendor fix is available")
    if signals.get("correlated"):
        add(10, f"toxic combination on the same resource: {signals['correlated']} (desk heuristic)")

    criticality, why, app = business_context(finding, profile, knowledge)
    points = CRITICALITY_POINTS.get(criticality, 0)
    if points:
        add(points, f"business criticality {criticality} ({why})")
    for goal in (knowledge or {}).get("goals", []) + profile.get("goals", []):
        boost = goal.get("boost") or {}
        if (finding["resource"]["type"] in (boost.get("resource_types") or [])
                or finding.get("category") in (boost.get("categories") or [])
                or any(signals.get(s) for s in boost.get("signals") or [])):
            if goal.get("path"):
                _cite(finding, goal)
            add(int(boost.get("points", 5)), f"matches goal: {goal['text']}"
                + (f" (knowledge {goal['path']})" if goal.get("path") else ""))
            break

    last = _parse_time(finding.get("last_seen"))
    if finding["category"] == "threat" and last and now - last > timedelta(days=30):
        add(-10, "no threat activity for over 30 days")
    if finding.get("decision"):
        decision = finding["decision"]
        reasons.append(f"operator decision: {decision['status']}"
                       + (f" (risk exception {decision['knowledge']}, expires {decision.get('expires')})"
                          if decision.get("knowledge") else ""))
    elif finding.get("expired_exception"):
        reasons.append(f"risk exception {finding['expired_exception']['path']} expired on "
                       f"{finding['expired_exception']['expires']}: back in the queue until it is renewed or fixed")

    score = max(0, min(100, score))
    # AWS's own correlated conclusions set a floor: the desk adds context, it never quietly ranks them lower.
    floor = 70 if signals.get("attack_sequence") or (signals.get("aws_exposure") and finding["severity"] == "CRITICAL") \
        else 50 if signals.get("aws_exposure") and finding["severity"] == "HIGH" else 0
    if score < floor and not finding.get("decision"):
        reasons.append(f"kept at {_priority(floor)} or above: AWS rates this {finding['severity']}"
                       + (" (attack sequence)" if signals.get("attack_sequence") else " exposure"))
        score = floor
    finding["score"] = score
    finding["priority"] = _priority(score)
    finding["criticality"] = criticality
    if app:
        finding["application"] = app
    finding["reasons"] = reasons
    return finding


def correlate(findings: list[dict]) -> None:
    """Mark resources that carry more than one kind of risk (threat + exposure, vuln + exposure...)."""
    by_resource = defaultdict(list)
    for f in findings:
        rid = f["resource"].get("name") or f["resource"].get("id")
        if rid and f["resource"].get("type") not in ("AwsAccount", "CloudWatchMetric", "AwsHealthEvent"):
            by_resource[(f["account"], rid)].append(f)
    for group in by_resource.values():
        kinds = {f["category"] for f in group}
        if any(f["signals"].get("public_exposure") for f in group):
            kinds.add("public")
        risky = kinds & {"threat", "vulnerability", "exposure", "public", "data"}
        if len(kinds) > 1 and risky:
            label = " + ".join(sorted(kinds))
            for f in group:
                f["signals"]["correlated"] = label
                f["related"] = [g["key"] for g in group if g is not f][:10]


def group_key(f: dict) -> str:
    control = f.get("control_id") or ""
    if f["signals"].get("rollup"):
        return f"rollup:{f['type']}:{f['account']}:{f['resource'].get('id')}"
    if re.fullmatch(r"CloudWatch\.\d+", control):
        return "family:cis-metric-filters"
    if f["source"] == "inspector" and control:
        package = ((f.get("context") or {}).get("packages") or [{}])[0].get("name")
        return f"package:{package}" if package else f"vuln:{control}"
    if f.get("control_id"):
        return f"control:{f['control_id']}"
    if f["source"] == "guardduty":
        return f"threat:{f['type']}:{f['resource'].get('name')}"
    return f"title:{f['title']}"


def build_issues(findings: list[dict]) -> list[dict]:
    """Collapse findings that share one fix (same control across standards/resources, same CVE...)."""
    groups = defaultdict(list)
    for f in findings:
        groups[group_key(f)].append(f)
    issues = []
    for key, members in groups.items():
        members.sort(key=lambda f: -f["score"])
        top = members[0]
        title = top["title"]
        if key.startswith("package:"):
            cves = {m.get("control_id") for m in members}
            crit = sum(1 for m in members if m["severity"] == "CRITICAL")
            exploit = sum(1 for m in members if m["signals"].get("exploit_available"))
            fixed = {p.get("fixed_in") for m in members for p in (m.get("context") or {}).get("packages", [])[:1] if p.get("fixed_in")}
            target = f" (fixed in {sorted(fixed)[-1]})" if len(fixed) == 1 else ""
            title = (f"Upgrade {key.split(':', 1)[1]}{target}: {len(members):,} critical/high findings, {len(cves)} CVEs"
                     f"{f', {exploit} with public exploits' if exploit else ''}")
        elif key == "family:cis-metric-filters":
            title = f"CloudTrail log metric filters/alarms missing for {len(members)} CIS checks (one change fixes all)"
        elif top.get("control_id") and not title.startswith(top["control_id"]):
            title = next((m["title"] for m in members if m["title"].startswith(top["control_id"])), title)
        resources = sorted({m["resource"].get("name") or m["resource"].get("id") for m in members} - {""})
        issues.append({
            "issue_key": key, "priority": top["priority"], "score": top["score"], "title": title,
            "category": top["category"], "product": top["product"], "severity": top["severity"],
            "control_id": "" if key.startswith("package:") else top.get("control_id", ""),
            "type": f"package {key.split(':', 1)[1]}" if key.startswith("package:") else top.get("type", ""),
            "accounts": sorted({m["account"] for m in members}), "regions": sorted({m["region"] for m in members}),
            "resources": resources[:25], "resource_count": len(resources), "finding_count": len(members),
            "finding_keys": [m["key"] for m in members][:50], "top_key": top["key"], "reasons": top["reasons"],
            "decision": top.get("decision"), "new": any(m.get("new") for m in members),
            "owner": top.get("owner"), "knowledge": top.get("knowledge") or [],
        })
    issues.sort(key=lambda i: (-i["score"], -i["finding_count"]))
    return issues


def prioritize(findings: list[dict], profile: dict, decisions: dict | None = None,
               knowledge: dict | None = None) -> tuple[list[dict], list[dict]]:
    """`knowledge` is `rgtriage.knowledge.effective()`: reviewed organization concepts that change priorities."""
    decisions = decisions or {}
    knowledge = knowledge or {}
    correlate(findings)
    for f in findings:
        if f["key"] in decisions:
            f["decision"] = decisions[f["key"]]
        else:
            exception = exception_for(f, knowledge.get("exceptions", []))
            if exception:
                # A reviewed risk exception acts like an accepted_risk decision until it expires.
                f["decision"] = {"status": "accepted_risk", "reason": exception["description"] or exception["title"],
                                 "by": f"knowledge:{exception['path']}", "knowledge": exception["path"],
                                 "expires": exception["expires"], "approved_by": exception.get("approved_by")}
                _cite(f, exception)
            else:
                expired = exception_for(f, knowledge.get("expired", []))
                if expired:
                    f["expired_exception"] = {"path": expired["path"], "expires": expired["expires"]}
                    _cite(f, expired)
        score_finding(f, profile, knowledge=knowledge)
    findings.sort(key=lambda f: (-f["score"], f["title"]))
    return findings, build_issues(findings)


def is_open(item: dict) -> bool:
    decision = item.get("decision") or {}
    return decision.get("status") not in ("accepted_risk", "suppressed", "resolved", "false_positive")
