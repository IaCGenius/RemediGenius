"""SG exposure rules (mission A6, also A1). Deterministic: same facts in, same findings out.

Logic adapted from jhkchan/aws-agent-skills ec2-security-group-auditor @ eeace51 (Apache-2.0):
per inbound rule classify SOURCE (PUBLIC / RESTRICTED / CONDITIONAL prefix list) and PORT
(high-risk registry, range intersection), worst rule wins per security group.
Severity is fixed per rule below (ADR-0017), never chosen by the model.

  python3 check.py --facts /opt/data/facts/<tenant>/<date>/sg.json --out <result.json>
"""
import argparse
import ipaddress
import json
import sys
from pathlib import Path

from .skillresult import envelope, finding

SKILL = "sg-exposure@0.1.0"
RULES = {
    "all": {"id": "SGNET-001", "severity": "critical", "fix": "FIX-SGNET-01",
            "title": "All ports or all protocols open to the internet"},
    "admin": {"id": "SGNET-002", "severity": "critical", "fix": "FIX-SGNET-01",
              "title": "Administrative or cluster-control port open to the internet"},
    "db": {"id": "SGNET-003", "severity": "critical", "fix": "FIX-SGNET-01",
           "title": "Database or cache port open to the internet"},
    "other": {"id": "SGNET-004", "severity": "high", "fix": "FIX-SGNET-01",
              "title": "Other high-risk port (queue, directory, SMB, mail, amplification) open to the internet"},
    "noncrit_attached": {"id": "SGNET-005", "severity": "medium", "fix": "FIX-SGNET-02",
                         "title": "Non-critical port open to the internet on a group in use"},
    "noncrit_unused": {"id": "SGNET-006", "severity": "low", "fix": "FIX-SGNET-02",
                       "title": "Non-critical port open to the internet on a group with no network interfaces"},
}
# (low, high, protocols, class)  protocols: "tcp", "udp" or "both"
HIGH_RISK = [
    (22, 22, "tcp", "admin"), (23, 23, "tcp", "admin"), (3389, 3389, "both", "admin"),
    (5900, 5910, "tcp", "admin"), (2375, 2376, "tcp", "admin"),
    (6443, 6443, "tcp", "admin"), (10250, 10250, "tcp", "admin"), (2379, 2380, "tcp", "admin"),
    (3306, 3306, "tcp", "db"), (5432, 5432, "tcp", "db"), (1433, 1433, "tcp", "db"),
    (1521, 1521, "tcp", "db"), (27017, 27019, "tcp", "db"), (6379, 6379, "tcp", "db"),
    (9042, 9042, "tcp", "db"), (5984, 5984, "tcp", "db"), (11211, 11211, "tcp", "db"),
    (9200, 9200, "tcp", "db"), (9300, 9300, "tcp", "db"),
    (5671, 5672, "tcp", "other"), (9092, 9092, "tcp", "other"),
    (135, 135, "tcp", "other"), (139, 139, "tcp", "other"), (445, 445, "tcp", "other"),
    (389, 389, "tcp", "other"), (636, 636, "tcp", "other"), (25, 25, "tcp", "other"),
    (53, 53, "udp", "other"), (123, 123, "udp", "other"), (161, 161, "udp", "other"),
    (1900, 1900, "udp", "other"), (5353, 5353, "udp", "other"), (11211, 11211, "udp", "other"),
]
RANK = ["all", "admin", "db", "other", "noncrit"]  # worst first
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                                              "100.64.0.0/10", "169.254.0.0/16", "127.0.0.0/8",
                                              "fc00::/7", "fe80::/10", "::1/128")]
# Our parameter (not in upstream): a non-private CIDR this broad or broader counts as the internet.
BROAD_V4, BROAD_V6 = 16, 32


def source_is_public(cidr):
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
    if net.prefixlen == 0:
        return True
    if any(net.version == p.version and net.subnet_of(p) for p in PRIVATE):
        return False
    return net.prefixlen <= (BROAD_V4 if net.version == 4 else BROAD_V6)


def port_class(proto, lo, hi):
    """Worst class for one rule's protocol + port range."""
    if proto == "-1":
        return "all"
    if proto in ("icmp", "icmpv6", "1", "58"):
        return "noncrit"
    if proto not in ("tcp", "udp", "6", "17"):
        return "noncrit"
    proto = {"6": "tcp", "17": "udp"}.get(proto, proto)
    if lo is None or (lo <= 0 and hi >= 65535):
        return "all"
    hits = [c for (a, b, p, c) in HIGH_RISK if (p in (proto, "both")) and lo <= b and hi >= a]
    return min(hits, key=RANK.index) if hits else "noncrit"


def classify_sg(sg, prefix_lists):
    worst, why = None, []
    for perm in sg.get("ip_permissions", []):
        proto = str(perm.get("IpProtocol", "-1")).lower()
        lo, hi = perm.get("FromPort"), perm.get("ToPort")
        sources = [r.get("CidrIp") for r in perm.get("IpRanges", [])]
        sources += [r.get("CidrIpv6") for r in perm.get("Ipv6Ranges", [])]
        public = [s for s in sources if s and source_is_public(s)]
        for pl in perm.get("PrefixListIds", []):
            info = prefix_lists.get(pl.get("PrefixListId"), {})
            entries = info.get("entries", [])
            if info.get("owner_id") == "AWS" or any(source_is_public(e) for e in entries):
                public.append(pl.get("PrefixListId"))
        if not public:
            continue
        cls = port_class(proto, lo, hi)
        port = "all" if proto == "-1" else (f"{lo}" if lo == hi else f"{lo}-{hi}")
        why.append({"protocol": proto, "ports": port, "sources": public, "class": cls})
        if worst is None or RANK.index(cls) < RANK.index(worst):
            worst = cls
    return worst, why


def run(facts):
    sgs = facts.get("security_groups", [])
    pls = facts.get("prefix_lists", {})
    findings = []
    for sg in sgs:
        worst, why = classify_sg(sg, pls)
        if worst is None:
            continue
        if worst == "noncrit":
            key = "noncrit_attached" if sg.get("attached_enis", 0) > 0 else "noncrit_unused"
        else:
            key = worst
        rule = RULES[key]
        arn = f"arn:aws:ec2:{sg['region']}:{sg.get('owner_id', '')}:security-group/{sg['group_id']}"
        findings.append(finding(rule, arn, sg["region"], {
            "group_id": sg["group_id"], "group_name": sg.get("group_name", ""), "vpc_id": sg.get("vpc_id", ""),
            "verdict": "OPEN" if worst != "noncrit" else "PUBLIC_NONCRITICAL",
            "rule": rule["title"], "attached_enis": sg.get("attached_enis", 0), "public_rules": why,
        }, key=sg["group_id"]))
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    facts = json.load(open(a.facts, encoding="utf-8"))
    status, reason = "OK", ""
    if facts.get("errors"):
        status, reason = "OK", f"partial facts: {len(facts['errors'])} collection errors (see facts.errors)"
    if not facts.get("security_groups") and facts.get("errors"):
        status, reason = "ERROR", "no security groups collected"
    findings = run(facts) if status != "ERROR" else []
    result = envelope(
        SKILL, "A6", {"tenant": facts.get("tenant"), "account": facts.get("account"), "regions": facts.get("regions", [])},
        facts.get("calls", []),
        {"security_groups": len(facts.get("security_groups", [])), "prefix_lists": len(facts.get("prefix_lists", {})),
         "collected_at": facts.get("collected_at"), "facts_errors": facts.get("errors", [])},
        findings, status, reason)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(result, open(a.out, "w", encoding="utf-8"), indent=2)
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    print(json.dumps({"out": a.out, "status": status, "findings": len(findings), "by_severity": counts}))


if __name__ == "__main__":
    main()
