"""SkillResult v0: the one JSON shape every RemediGenius skill returns.

Shared by the check scripts of the other remedigenius skills (they add this folder to sys.path).
Severity and rule verdicts are produced by the check scripts (rules); the model only adds
annotations (explanation, impact, next_step) through `merge`, which refuses to touch anything else.

Usage (by the agent):
  python3 skillresult.py merge --result R.json --annotations A.json [--out R.json]
  python3 skillresult.py validate --result R.json
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone

SEVERITIES = ("critical", "high", "medium", "low", "info")
SKILL_STATUS = ("OK", "ERROR", "NOT_RUN", "SKIPPED")
RULE_ID = re.compile(r"^[A-Z]+-[0-9]{3}$")
FIX_ID = re.compile(r"^FIX-[A-Z0-9]+-[0-9]{2}$")
PROVIDERS = ("aws", "azure", "gcp")
SCOPE = re.compile(r"^(global|[a-z]{2}(-[a-z]+)+-[0-9]+)$")
SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}


def finding(rule, resource_id, scope, evidence, key=None):
    """Build one Finding (packages/contracts Finding.schema.json). `rule` comes from a RULES table."""
    key = key or resource_id.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return {
        "rule_id": rule["id"],
        "row_id": f"{rule['id']}:{scope}:{key}"[:200],
        "resource_id": resource_id,
        "scope": scope,
        "severity": rule["severity"],
        "evidence": evidence,
        "fix_id": rule["fix"],
    }


def envelope(skill, mission, scope, calls, facts, findings, status="OK", reason="", open_questions=None, provider="aws"):
    findings = sorted(findings, key=lambda f: (SEV_ORDER[f["severity"]], f["rule_id"], f["row_id"]))
    return {
        "skill": skill,
        "provider": provider,
        "mission": mission,
        "role": "analyst",
        "status": {"status": status, "reason": reason},
        "scope": scope,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calls": calls,
        "facts": facts,
        "findings": findings,
        "annotations": [],
        "handoff": {"next_roles": ["desk"] if findings else [], "open_questions": open_questions or []},
    }


def validate(result):
    errs = []
    if result.get("provider", "aws") not in PROVIDERS:
        errs.append("provider not in " + "/".join(PROVIDERS))
    if result.get("status", {}).get("status") not in SKILL_STATUS:
        errs.append("status.status not in " + "/".join(SKILL_STATUS))
    rows = set()
    for f in result.get("findings", []):
        if not RULE_ID.match(f.get("rule_id", "")):
            errs.append(f"bad rule_id {f.get('rule_id')}")
        if f.get("severity") not in SEVERITIES:
            errs.append(f"bad severity {f.get('severity')} on {f.get('row_id')}")
        if not SCOPE.match(f.get("scope", "")):
            errs.append(f"bad scope {f.get('scope')}")
        if not FIX_ID.match(f.get("fix_id", "")):
            errs.append(f"bad fix_id {f.get('fix_id')}")
        if not isinstance(f.get("evidence"), dict):
            errs.append(f"evidence must be an object on {f.get('row_id')}")
        if f.get("row_id") in rows:
            errs.append(f"duplicate row_id {f.get('row_id')}")
        rows.add(f.get("row_id"))
    for a in result.get("annotations", []):
        if set(a) != {"row_id", "explanation", "impact", "next_step"}:
            errs.append(f"annotation must have exactly row_id, explanation, impact, next_step: {sorted(a)}")
        elif a["row_id"] not in rows:
            errs.append(f"annotation for unknown row_id {a['row_id']}")
        elif not all(isinstance(a[k], str) and 0 < len(a[k]) <= 4000 for k in ("explanation", "impact", "next_step")):
            errs.append(f"annotation text empty or over 4000 chars: {a['row_id']}")
    return errs


def merge(result, annotations):
    """Add the model's annotations. Anything other than the four annotation fields is rejected."""
    if isinstance(annotations, dict):
        annotations = annotations.get("annotations", [])
    by_row = {a["row_id"]: a for a in result.get("annotations", [])}
    for a in annotations:
        by_row[a.get("row_id")] = {k: a.get(k) for k in ("row_id", "explanation", "impact", "next_step")}
        extra = set(a) - {"row_id", "explanation", "impact", "next_step"}
        if extra:
            raise SystemExit(f"refused: annotation for {a.get('row_id')} carries {sorted(extra)}; "
                             "severity and verdicts come from rules, not annotations")
    result["annotations"] = list(by_row.values())
    errs = validate(result)
    if errs:
        raise SystemExit("refused: " + "; ".join(errs))
    return result


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--result", required=True)
    m.add_argument("--annotations", required=True)
    m.add_argument("--out")
    v = sub.add_parser("validate")
    v.add_argument("--result", required=True)
    a = ap.parse_args()
    result = json.load(open(a.result, encoding="utf-8"))
    if a.cmd == "validate":
        errs = validate(result)
        print("OK" if not errs else "\n".join(errs))
        sys.exit(1 if errs else 0)
    result = merge(result, json.load(open(a.annotations, encoding="utf-8")))
    json.dump(result, open(a.out or a.result, "w", encoding="utf-8"), indent=2)
    print(f"merged {len(result['annotations'])} annotations into {a.out or a.result}")


if __name__ == "__main__":
    main()
