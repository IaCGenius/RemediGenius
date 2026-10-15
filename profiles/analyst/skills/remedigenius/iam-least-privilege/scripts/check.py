"""IAM least-privilege rules (mission B6, also B1, A5). Deterministic: same facts in, same findings out.

Logic adapted from jhkchan/aws-agent-skills iam-least-privilege-advisor @ eeace51 (Apache-2.0),
steps 1-9 and 11: Deny statements never grant; admin wildcard; privilege-escalation service
wildcards; inverse wildcards (NotAction/NotResource); privilege-escalation actions on "*";
service wildcards on "*"; partition/all-bucket resource wildcards; wildcard actions on scoped
resources and bypass-prone conditions (ambiguous). Worst statement wins per policy.
Our scoping: AWS-managed policies are judged only on admin / privilege escalation (their broad
read-only grants are by design); service-linked roles are skipped (not customer-editable).
Severity is fixed per rule below (ADR-0017), never chosen by the model.

  python3 check.py --facts /opt/data/facts/<tenant>/<date>/iam.json --out <result.json>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skillresult" / "scripts"))
from skillresult import envelope, finding  # noqa: E402

SKILL = "iam-least-privilege@0.1.0"
RULES = {
    "admin": {"id": "IAMLP-001", "severity": "critical", "fix": "FIX-IAMLP-01",
              "title": "Step 2: Action * on Resource * (administrator)"},
    "privesc_wild": {"id": "IAMLP-002", "severity": "critical", "fix": "FIX-IAMLP-01",
                     "title": "Step 3/5: wildcard on a privilege-escalation service (iam, sts, kms, secretsmanager, ssm, lambda, cloudformation) on *"},
    "privesc_action": {"id": "IAMLP-003", "severity": "high", "fix": "FIX-IAMLP-02",
                       "title": "Step 5: privilege-escalation action on Resource *"},
    "inverse": {"id": "IAMLP-004", "severity": "high", "fix": "FIX-IAMLP-02",
                "title": "Step 4: NotAction or NotResource in an Allow (inverse wildcard)"},
    "service_wild": {"id": "IAMLP-005", "severity": "high", "fix": "FIX-IAMLP-02",
                     "title": "Step 3: service wildcard on Resource *"},
    "broad_resource": {"id": "IAMLP-006", "severity": "high", "fix": "FIX-IAMLP-02",
                       "title": "Step 8: resource pattern spans every partition or every bucket"},
    "ambiguous": {"id": "IAMLP-007", "severity": "medium", "fix": "FIX-IAMLP-03",
                  "title": "Step 6/7: wildcard actions on scoped resources, or a bypass-prone condition"},
}
ORDER = ["admin", "privesc_wild", "privesc_action", "inverse", "service_wild", "broad_resource", "ambiguous"]
AWS_MANAGED_RULES = {"admin", "privesc_wild", "privesc_action"}
PRIVESC_SERVICES = {"iam", "sts", "kms", "secretsmanager", "ssm", "lambda", "cloudformation"}
PRIVESC_ACTIONS = {"iam:passrole", "sts:assumerole", "iam:createpolicy", "iam:createpolicyversion",
                   "iam:attachrolepolicy", "iam:putrolepolicy", "iam:updateassumerolepolicy",
                   "iam:createservicelinkedrole"}


def as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def is_read_wildcard(a):
    verb = a.split(":", 1)[-1]
    return verb in ("describe*", "list*")


def bypass_condition(cond):
    for op, kv in (cond or {}).items():
        if op.startswith("ForAllValues:"):
            return f"{op} (true when the key is absent)"
        if op == "Null" and any(str(v).lower() == "false" for v in (kv or {}).values()):
            return "Null: false"
        for key, val in (kv or {}).items():
            if key.lower() == "aws:sourceip" and any(v in ("0.0.0.0/0", "::/0") for v in as_list(val)):
                return "aws:SourceIp 0.0.0.0/0"
    return None


def classify_statement(st):
    if st.get("Effect") != "Allow":
        return None, None
    if st.get("NotAction") or st.get("NotResource"):
        return "inverse", "NotAction/NotResource"
    actions = [a.lower() for a in as_list(st.get("Action"))]
    resources = as_list(st.get("Resource"))
    all_res = "*" in resources
    if all_res:
        if "*" in actions:
            return "admin", "Action * on *"
        wild = [a for a in actions if "*" in a]
        pw = [a for a in wild if a.split(":", 1)[0] in PRIVESC_SERVICES and a.endswith(":*")]
        if pw:
            return "privesc_wild", ", ".join(pw)
        pa = [a for a in actions if a in PRIVESC_ACTIONS]
        if pa:
            return "privesc_action", ", ".join(pa)
        sw = [a for a in wild if not is_read_wildcard(a)]
        if sw:
            return "service_wild", ", ".join(sw)
    broad = [r for r in resources if r.startswith("arn:aws-*:") or r in ("arn:aws:s3:::*", "arn:aws:s3:::*/*")]
    if broad:
        return "broad_resource", ", ".join(broad)
    if not all_res and any("*" in a for a in actions):
        return "ambiguous", "wildcard actions on scoped resources: " + ", ".join(a for a in actions if "*" in a)
    bypass = bypass_condition(st.get("Condition"))
    if bypass:
        return "ambiguous", "bypass-prone condition: " + bypass
    return None, None


def classify_policy(doc, aws_managed):
    worst, hits = None, []
    for i, st in enumerate(as_list((doc or {}).get("Statement"))):
        key, why = classify_statement(st)
        if key is None or (aws_managed and key not in AWS_MANAGED_RULES):
            continue
        hits.append({"statement": st.get("Sid", f"#{i}"), "rule": RULES[key]["id"], "why": why})
        if worst is None or ORDER.index(key) < ORDER.index(worst):
            worst = key
    return worst, hits


def run(facts):
    findings = []
    for p in facts.get("policies", []):
        if p.get("service_linked"):
            continue
        doc = p.get("document")
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except ValueError:
                continue
        aws_managed = p.get("managed_by") == "aws"
        key, hits = classify_policy(doc, aws_managed)
        if key is None:
            continue
        rule = RULES[key]
        ev = {"policy": p["name"], "kind": p["kind"], "managed_by": p.get("managed_by", "customer"),
              "attached_to": p.get("attached_to", [])[:20], "attachment_count": len(p.get("attached_to", [])),
              "verdict": "AMBIGUOUS" if key == "ambiguous" else "OVERPERMISSIVE",
              "rule": rule["title"], "statements": hits[:10]}
        if doc and doc.get("Version") == "2008-10-17":
            ev["legacy_version"] = True
        findings.append(finding(rule, p["arn"], "global", ev, key=p["key"]))
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    facts = json.load(open(a.facts, encoding="utf-8"))
    status, reason = "OK", ""
    errors = facts.get("errors", [])
    if errors:
        reason = f"partial facts: {len(errors)} collection errors (see facts.facts_errors)"
    if not facts.get("policies") and errors:
        status, reason = "ERROR", "no policies collected"
    findings = run(facts) if status == "OK" else []
    result = envelope(
        SKILL, "B6", {"tenant": facts.get("tenant"), "account": facts.get("account"), "regions": ["global"]},
        facts.get("calls", []),
        {"policies": len(facts.get("policies", [])), "principals": facts.get("principals", {}),
         "collected_at": facts.get("collected_at"), "facts_errors": errors},
        findings, status, reason,
        ["Effective permissions (permission boundaries, SCPs, unused access from CloudTrail) are not evaluated in v0."])
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(a.out, "w", encoding="utf-8"), indent=2)
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    print(json.dumps({"out": a.out, "status": status, "findings": len(findings), "by_severity": counts}))


if __name__ == "__main__":
    main()
