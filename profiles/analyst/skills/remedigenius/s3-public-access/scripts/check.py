"""S3 public access rules (mission A3, also A1). Deterministic: same facts in, same findings out.

Logic adapted from jhkchan/aws-agent-skills s3-public-access-auditor @ eeace51 (Apache-2.0):
Rule 1 BPA authoritative, Rule 2 unrestricted wildcard Allow (write = critical, read = high),
Rule 3 legacy ACL grant to AllUsers/AuthenticatedUsers, Rule 4 condition-restricted wildcard
(fragile), Rule 5 clean but BPA off. Effective BPA = bucket OR account, per setting.
Our refinement: an effective RestrictPublicBuckets stops Rule 2, an effective IgnorePublicAcls
stops Rule 3 (that is how AWS evaluates them); the bucket then falls to Rule 5.
Severity is fixed per rule below (ADR-0017), never chosen by the model.

  python3 check.py --facts /opt/data/facts/<tenant>/<date>/s3.json --out <result.json>
"""
import argparse
import ipaddress
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skillresult" / "scripts"))
from skillresult import envelope, finding  # noqa: E402

SKILL = "s3-public-access@0.1.0"
RULES = {
    "policy_write": {"id": "BKTPUB-001", "severity": "critical", "fix": "FIX-S3PUB-01",
                     "title": "Rule 2: bucket or access point policy lets anyone write or change it"},
    "policy_read": {"id": "BKTPUB-002", "severity": "high", "fix": "FIX-S3PUB-01",
                    "title": "Rule 2: bucket or access point policy lets anyone read it"},
    "acl_write": {"id": "BKTPUB-003", "severity": "critical", "fix": "FIX-S3PUB-02",
                  "title": "Rule 3: ACL grants write to AllUsers or AuthenticatedUsers"},
    "acl_read": {"id": "BKTPUB-004", "severity": "high", "fix": "FIX-S3PUB-02",
                 "title": "Rule 3: ACL grants read to AllUsers or AuthenticatedUsers"},
    "ambiguous": {"id": "BKTPUB-005", "severity": "medium", "fix": "FIX-S3PUB-03",
                  "title": "Rule 4: wildcard principal held back only by a condition (fragile)"},
    "bpa_off": {"id": "BKTPUB-006", "severity": "low", "fix": "FIX-S3PUB-03",
                "title": "Rule 5: not public today, but Block Public Access is not fully on"},
}
BPA_KEYS = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
PUBLIC_GRANTEES = ("http://acs.amazonaws.com/groups/global/AllUsers",
                   "http://acs.amazonaws.com/groups/global/AuthenticatedUsers")
WRITE_PREFIXES = ("s3:put", "s3:delete", "s3:*", "*", "s3:restore", "s3:replicate")
READ_PREFIXES = ("s3:get", "s3:list")
STRONG_KEYS = {"aws:sourcevpce", "aws:sourcevpc", "aws:sourceaccount", "aws:sourceorgid", "aws:principalorgid",
               "aws:principalaccount", "aws:principalarn", "aws:sourcearn", "aws:sourceorgpaths",
               "aws:principalorgpaths"}
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]


def as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def effective_bpa(bucket_bpa, account_bpa):
    b, a = bucket_bpa or {}, account_bpa or {}
    return {k: bool(b.get(k)) or bool(a.get(k)) for k in BPA_KEYS}


def principal_is_everyone(p):
    if p == "*":
        return True
    if isinstance(p, dict):
        return any("*" in as_list(v) for v in p.values())
    return False


def source_ip_strong(values):
    nets = []
    for v in as_list(values):
        try:
            nets.append(ipaddress.ip_network(v, strict=False))
        except ValueError:
            return False
    if not nets or any(n.prefixlen == 0 for n in nets):
        return False
    # private ranges are strong; narrow public ranges (a documented corporate range) count as strong too,
    # anything as broad as a /1 split-halves trick does not
    return all(any(n.version == p.version and n.subnet_of(p) for p in PRIVATE) or n.prefixlen >= 8 for n in nets)


def condition_strength(cond):
    """'none' (no condition), 'weak' or 'strong' (at least one strong key, not IfExists)."""
    if not cond:
        return "none"
    for op, kv in cond.items():
        if op.endswith("IfExists") or not isinstance(kv, dict):
            continue
        for key, val in kv.items():
            k = key.lower()
            if k in STRONG_KEYS:
                return "strong"
            if k == "aws:sourceip" and "NotIpAddress" not in op and source_ip_strong(val):
                return "strong"
    return "weak"


def classify_policy(policy, where):
    """Returns (rule key or None, evidence statements)."""
    worst, hits = None, []
    if not policy:
        return None, []
    for i, st in enumerate(as_list(policy.get("Statement"))):
        if st.get("Effect") != "Allow" or not principal_is_everyone(st.get("Principal")):
            continue
        actions = [a.lower() for a in as_list(st.get("Action"))]
        if st.get("NotAction"):
            actions = ["*"]
        write = any(a.startswith(WRITE_PREFIXES) or a == "*" for a in actions)
        read = write or any(a.startswith(READ_PREFIXES) for a in actions)
        if not read:
            continue
        strength = condition_strength(st.get("Condition"))
        key = "ambiguous" if strength == "strong" else ("policy_write" if write else "policy_read")
        hits.append({"where": where, "statement": st.get("Sid", f"#{i}"), "actions": as_list(st.get("Action")),
                     "condition": strength})
        order = ["policy_write", "policy_read", "ambiguous"]
        if worst is None or order.index(key) < order.index(worst):
            worst = key
    return worst, hits


def classify_bucket(b, account_bpa):
    bpa = effective_bpa(b.get("bpa"), account_bpa)
    ev = {"bucket": b["name"], "effective_bpa": bpa,
          "bpa_scope": {"bucket": b.get("bpa"), "account": account_bpa}}
    if all(bpa.values()):
        return None, ev  # Rule 1: SAFE
    candidates = []
    pol_key, pol_hits = classify_policy(b.get("policy"), "bucket policy")
    for ap in b.get("access_points", []):
        k, h = classify_policy(ap.get("policy"), f"access point {ap.get('name')}")
        pol_hits += h
        if k and (pol_key is None or ["policy_write", "policy_read", "ambiguous"].index(k)
                  < ["policy_write", "policy_read", "ambiguous"].index(pol_key)):
            pol_key = k
    if pol_hits:
        ev["policy_statements"] = pol_hits
    if pol_key in ("policy_write", "policy_read") and bpa["RestrictPublicBuckets"]:
        ev["note"] = "RestrictPublicBuckets is on, so the public policy does not grant anonymous access"
        pol_key = None
    if pol_key:
        candidates.append(pol_key)
    acls_active = b.get("ownership") != "BucketOwnerEnforced" and not bpa["IgnorePublicAcls"]
    grants = [g for g in b.get("acl_grants", []) if g.get("grantee_uri") in PUBLIC_GRANTEES]
    if grants:
        ev["public_acl_grants"] = grants
        if acls_active:
            write = any(g.get("permission") in ("WRITE", "WRITE_ACP", "FULL_CONTROL") for g in grants)
            candidates.append("acl_write" if write else "acl_read")
        else:
            ev["note_acl"] = "public ACL grant present but ignored (BucketOwnerEnforced or IgnorePublicAcls)"
    if b.get("website"):
        ev["website_hosting"] = True
    order = ["policy_write", "acl_write", "policy_read", "acl_read", "ambiguous"]
    if candidates:
        return min(candidates, key=order.index), ev
    return "bpa_off", ev  # Rule 5


def run(facts):
    findings = []
    for b in facts.get("buckets", []):
        if b.get("errors") and b.get("bpa") is None and b.get("policy") is None and not b.get("acl_grants"):
            continue  # nothing readable for this bucket; reported in facts_errors
        key, ev = classify_bucket(b, facts.get("account_bpa"))
        if key is None:
            continue
        rule = RULES[key]
        ev["rule"] = rule["title"]
        ev["verdict"] = {"ambiguous": "AMBIGUOUS", "bpa_off": "SAFE"}.get(key, "PUBLIC")
        findings.append(finding(rule, f"arn:aws:s3:::{b['name']}", b.get("region") or "us-east-1", ev, key=b["name"]))
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
    if not facts.get("buckets") and errors:
        status, reason = "ERROR", "no buckets collected"
    findings = run(facts) if status == "OK" else []
    questions = []
    if facts.get("account_bpa") is None:
        questions.append("Account-level Block Public Access could not be read; assumed OFF (worst case).")
    if not facts.get("access_points_collected"):
        questions.append("Access point policies were not collected (NOT_RUN); exposure through access points is unchecked.")
    result = envelope(
        SKILL, "A3", {"tenant": facts.get("tenant"), "account": facts.get("account"), "regions": ["global"]},
        facts.get("calls", []),
        {"buckets": len(facts.get("buckets", [])), "account_bpa": facts.get("account_bpa"),
         "collected_at": facts.get("collected_at"), "facts_errors": errors},
        findings, status, reason, questions)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(a.out, "w", encoding="utf-8"), indent=2)
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    print(json.dumps({"out": a.out, "status": status, "findings": len(findings), "by_severity": counts}))


if __name__ == "__main__":
    main()
