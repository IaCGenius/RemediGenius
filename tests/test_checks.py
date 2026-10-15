"""Rule tests on synthetic facts (fake account 111122223333, no real data).

  python tests/test_checks.py        # exits non-zero on any failure
Each case: facts in, expected {resource key: rule_id or None}. Also validates the SkillResult shape.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / "profiles" / "analyst" / "skills" / "remedigenius"
sys.path.insert(0, str(SK / "skillresult" / "scripts"))
from skillresult import validate, merge  # noqa: E402

ACCT = "111122223333"
ALL_BPA = {k: True for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")}
NO_BPA = {k: False for k in ALL_BPA}


def stmt(action, principal="*", cond=None, effect="Allow", resource="arn:aws:s3:::b/*"):
    s = {"Effect": effect, "Principal": principal, "Action": action, "Resource": resource}
    if cond:
        s["Condition"] = cond
    return s


def bucket(name, bpa=None, policy=None, acl=None, ownership=None):
    return {"name": name, "region": "us-east-1", "bpa": bpa, "acl_grants": acl or [], "ownership": ownership,
            "website": False, "policy": {"Version": "2012-10-17", "Statement": policy} if policy else None}


ALLUSERS = "http://acs.amazonaws.com/groups/global/AllUsers"
S3 = {
    "tenant": "test", "account": ACCT, "account_bpa": NO_BPA, "access_points_collected": False, "calls": [], "errors": [],
    "buckets": [
        bucket("bpa-on", ALL_BPA, [stmt("s3:GetObject")]),                                   # Rule 1 -> none
        bucket("pub-write", NO_BPA, [stmt("s3:PutObject")]),                                 # BKTPUB-001
        bucket("pub-read", None, [stmt(["s3:GetObject"], {"AWS": "*"})]),                    # BKTPUB-002
        bucket("pub-read-referer", NO_BPA, [stmt("s3:GetObject", cond={"StringLike": {"aws:Referer": "x"}})]),  # weak -> 002
        bucket("acl-write", NO_BPA, acl=[{"grantee_uri": ALLUSERS, "permission": "WRITE"}]),  # BKTPUB-003
        bucket("acl-read", NO_BPA, acl=[{"grantee_uri": ALLUSERS, "permission": "READ"}]),    # BKTPUB-004
        bucket("acl-enforced", NO_BPA, acl=[{"grantee_uri": ALLUSERS, "permission": "READ"}],
               ownership="BucketOwnerEnforced"),                                              # ignored -> 006
        bucket("vpce-only", NO_BPA, [stmt("s3:GetObject", cond={"StringEquals": {"aws:SourceVpce": "vpce-1"}})]),  # 005
        bucket("restrict-on", dict(NO_BPA, RestrictPublicBuckets=True), [stmt("s3:GetObject")]),  # 006
        bucket("clean", NO_BPA),                                                              # 006
        bucket("account-safe", None),                                                         # with account BPA below
    ],
}
S3_EXPECT = {"bpa-on": None, "pub-write": "BKTPUB-001", "pub-read": "BKTPUB-002", "pub-read-referer": "BKTPUB-002",
             "acl-write": "BKTPUB-003", "acl-read": "BKTPUB-004", "acl-enforced": "BKTPUB-006", "vpce-only": "BKTPUB-005",
             "restrict-on": "BKTPUB-006", "clean": "BKTPUB-006", "account-safe": "BKTPUB-006"}


def sg(gid, perms, enis=1):
    return {"group_id": gid, "group_name": gid, "vpc_id": "vpc-1", "region": "us-east-1", "owner_id": ACCT,
            "ip_permissions": perms, "attached_enis": enis}


def perm(proto, lo, hi, cidrs=(), v6=(), pls=()):
    return {"IpProtocol": proto, "FromPort": lo, "ToPort": hi, "IpRanges": [{"CidrIp": c} for c in cidrs],
            "Ipv6Ranges": [{"CidrIpv6": c} for c in v6], "PrefixListIds": [{"PrefixListId": p} for p in pls],
            "UserIdGroupPairs": []}


SG = {
    "tenant": "test", "account": ACCT, "regions": ["us-east-1"], "calls": [], "errors": [],
    "prefix_lists": {"pl-aws": {"owner_id": "AWS", "entries": []},
                     "pl-private": {"owner_id": ACCT, "entries": ["10.1.0.0/16"]}},
    "security_groups": [
        sg("sg-all", [perm("-1", None, None, ["0.0.0.0/0"])]),                       # SGNET-001
        sg("sg-range", [perm("tcp", 0, 65535, ["0.0.0.0/0"])]),                       # SGNET-001
        sg("sg-ssh6", [perm("tcp", 22, 22, v6=["::/0"])]),                            # SGNET-002
        sg("sg-split", [perm("tcp", 3389, 3389, ["0.0.0.0/1", "128.0.0.0/1"])]),       # SGNET-002
        sg("sg-mysql-range", [perm("tcp", 3300, 3310, ["0.0.0.0/0"])]),                # SGNET-003
        sg("sg-dns", [perm("udp", 53, 53, ["0.0.0.0/0"])]),                            # SGNET-004
        sg("sg-web", [perm("tcp", 443, 443, ["0.0.0.0/0"]), perm("tcp", 22, 22, ["10.0.0.0/8"])]),  # SGNET-005
        sg("sg-web-unused", [perm("tcp", 8080, 8080, ["0.0.0.0/0"])], enis=0),        # SGNET-006
        sg("sg-private", [perm("tcp", 22, 22, ["10.0.0.0/8", "203.0.113.7/32"])]),    # none
        sg("sg-pl-aws", [perm("tcp", 22, 22, pls=["pl-aws"])]),                         # SGNET-002
        sg("sg-pl-private", [perm("tcp", 22, 22, pls=["pl-private"])]),                 # none
        sg("sg-icmp", [perm("icmp", -1, -1, ["0.0.0.0/0"])]),                           # SGNET-005
        sg("sg-empty", []),                                                            # none
    ],
}
SG_EXPECT = {"sg-all": "SGNET-001", "sg-range": "SGNET-001", "sg-ssh6": "SGNET-002", "sg-split": "SGNET-002",
             "sg-mysql-range": "SGNET-003", "sg-dns": "SGNET-004", "sg-web": "SGNET-005", "sg-web-unused": "SGNET-006",
             "sg-private": None, "sg-pl-aws": "SGNET-002", "sg-pl-private": None, "sg-icmp": "SGNET-005", "sg-empty": None}


def pol(key, statements, managed_by="customer", kind="managed", slr=False):
    return {"key": key, "arn": f"arn:aws:iam::{ACCT}:policy/{key}", "name": key, "kind": kind, "managed_by": managed_by,
            "attached_to": [f"arn:aws:iam::{ACCT}:role/r"], "service_linked": slr,
            "document": {"Version": "2012-10-17", "Statement": statements}}


def a(action, resource="*", **kw):
    return dict({"Effect": "Allow", "Action": action, "Resource": resource}, **kw)


IAM = {
    "tenant": "test", "account": ACCT, "calls": [], "errors": [], "principals": {},
    "policies": [
        pol("admin", [a("*")]),                                                         # IAMLP-001
        pol("iam-star", [a("iam:*")]),                                                  # IAMLP-002
        pol("passrole", [a("iam:PassRole")]),                                           # IAMLP-003
        pol("notaction", [{"Effect": "Allow", "NotAction": "iam:*", "Resource": "*"}]), # IAMLP-004
        pol("s3-star", [a("s3:*")]),                                                    # IAMLP-005
        pol("all-buckets", [a("s3:GetObject", "arn:aws:s3:::*/*")]),                    # IAMLP-006
        pol("scoped-wild", [a("s3:Get*", "arn:aws:s3:::my-bucket/*")]),                # IAMLP-007
        pol("cond-bypass", [a("s3:GetObject", "arn:aws:s3:::my-bucket/*",
                              Condition={"ForAllValues:StringEquals": {"aws:TagKeys": ["x"]}})]),  # IAMLP-007
        pol("least", [a(["s3:GetObject"], "arn:aws:s3:::my-bucket/*"), a("ec2:Describe*")]),  # none
        pol("deny-only", [{"Effect": "Deny", "Action": "*", "Resource": "*"}]),         # none
        pol("aws-readonly", [a(["s3:Get*", "ec2:Describe*"])], managed_by="aws"),       # none (aws-managed scoping)
        pol("aws-admin", [a("*")], managed_by="aws"),                                    # IAMLP-001
        pol("slr", [a("*")], slr=True),                                                  # skipped
    ],
}
IAM_EXPECT = {"admin": "IAMLP-001", "iam-star": "IAMLP-002", "passrole": "IAMLP-003", "notaction": "IAMLP-004",
              "s3-star": "IAMLP-005", "all-buckets": "IAMLP-006", "scoped-wild": "IAMLP-007", "cond-bypass": "IAMLP-007",
              "least": None, "deny-only": None, "aws-readonly": None, "aws-admin": "IAMLP-001", "slr": None}


def run(skill, facts, expect, keyfn):
    with tempfile.TemporaryDirectory() as tmp:
        fp, op = Path(tmp) / "facts.json", Path(tmp) / "out.json"
        fp.write_text(json.dumps(facts))
        p = subprocess.run([sys.executable, str(SK / skill / "scripts" / "check.py"), "--facts", str(fp), "--out", str(op)],
                           capture_output=True, text=True)
        if p.returncode:
            return [f"{skill}: check.py failed: {p.stderr[-500:]}"]
        result = json.loads(op.read_text())
    got = {keyfn(f): f["rule_id"] for f in result["findings"]}
    errs = [f"{skill}: {k} expected {v} got {got.get(k)}" for k, v in expect.items() if got.get(k) != v]
    errs += [f"{skill}: unexpected finding {k} {v}" for k, v in got.items() if k not in expect]
    errs += [f"{skill}: shape: {e}" for e in validate(result)]
    if result["findings"]:  # annotations: allowed fields merge, extra fields refused
        row = result["findings"][0]["row_id"]
        merge(result, {"annotations": [{"row_id": row, "explanation": "e", "impact": "i", "next_step": "n"}]})
        try:
            merge(result, [{"row_id": row, "explanation": "e", "impact": "i", "next_step": "n", "severity": "low"}])
            errs.append(f"{skill}: merge accepted a severity field")
        except SystemExit:
            pass
    return errs


def main():
    S3_case = json.loads(json.dumps(S3))
    errs = run("s3-public-access", S3_case, S3_EXPECT, lambda f: f["evidence"]["bucket"])
    errs += run("sg-exposure", SG, SG_EXPECT, lambda f: f["evidence"]["group_id"])
    errs += run("iam-least-privilege", IAM, IAM_EXPECT, lambda f: f["evidence"]["policy"])
    # account-level BPA protects buckets without their own BPA
    acct = dict(S3, account_bpa=ALL_BPA, buckets=[bucket("account-safe", None, [stmt("s3:GetObject")])])
    errs += run("s3-public-access", acct, {"account-safe": None}, lambda f: f["evidence"]["bucket"])
    total = len(S3_EXPECT) + len(SG_EXPECT) + len(IAM_EXPECT) + 1
    print("\n".join(errs) if errs else f"all {total} rule cases pass")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
