#!/usr/bin/env python3
"""Collector: no LLM. Runs on the host (not in the agents' container), as root.

Assumes the tenant's read-only role (ExternalId from Secrets Manager), reads configuration only,
writes facts for the analyst's skills:
  /data/hermes/facts/<tenant>/<YYYY-MM-DD>/{s3,sg,iam}.json   (container: /opt/data/facts/...)
and copies them to s3://<bucket>/results/<tenant>/<date>/facts/.

Every API call is counted (calls[]) and every failure recorded (errors[]); a call that fails is
never retried silently. A hard cap on calls per run (API_BUDGET) keeps the daily footprint fixed.

  sudo /opt/rg/dist/collect.py self [--only s3,sg,iam]
  sudo /opt/rg/dist/collect.py --all        # every tenant secret, then results copied to S3
  (scheduled: rg-hermes-collect.timer, on only when schedule_enabled = true in Terraform)
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ENV = dict(line.strip().split("=", 1) for line in open("/etc/rg-hermes.env") if "=" in line)
ENV = {k: v.strip('"') for k, v in ENV.items()}
REGION, BUCKET = ENV["REGION"], ENV["BUCKET"]
PREFIX = ENV.get("NAME_PREFIX", "rgce")
API_BUDGET = int(os.environ.get("RG_API_BUDGET", "3000"))
FACTS_ROOT = Path("/data/hermes/facts")
CONTAINER_UID = 10000  # the hermes user inside the image


class Budget(Exception):
    pass


class Aws:
    def __init__(self, creds=None):
        self.env = dict(os.environ)
        if creds:
            self.env.update(AWS_ACCESS_KEY_ID=creds["AccessKeyId"], AWS_SECRET_ACCESS_KEY=creds["SecretAccessKey"],
                            AWS_SESSION_TOKEN=creds["SessionToken"])
        self.calls = Counter()
        self.failed = Counter()
        self.errors = []

    def __call__(self, api, args, region=None, quiet_codes=()):
        """api like 's3:GetBucketPolicy'; args = aws cli words. Returns parsed JSON or None on error."""
        if sum(self.calls.values()) >= API_BUDGET:
            raise Budget(f"API budget {API_BUDGET} reached")
        self.calls[api] += 1
        cmd = ["aws", *args, "--output", "json", "--region", region or REGION]
        p = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        if p.returncode != 0:
            msg = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else f"exit {p.returncode}"
            if any(c in msg for c in quiet_codes):
                return {"__absent__": True}
            self.failed[api] += 1
            self.errors.append({"api": api, "args": " ".join(args[2:])[:200], "error": msg[:300]})
            return None
        return json.loads(p.stdout) if p.stdout.strip() else {}

    def call_summary(self):
        return [{"api": k, "count": v, "status": "ERROR" if self.failed[k] == v else ("OK" if not self.failed[k] else "PARTIAL"),
                 **({"failed": self.failed[k]} if self.failed[k] else {})} for k, v in sorted(self.calls.items())]


def tenant_config(tenant):
    host = Aws()
    raw = host("secretsmanager:GetSecretValue",
               ["secretsmanager", "get-secret-value", "--secret-id", f"{PREFIX}/hermes/tenant/{tenant}"])
    if not raw:
        sys.exit(f"cannot read tenant secret {PREFIX}/hermes/tenant/{tenant}: {host.errors}")
    return json.loads(raw["SecretString"])


def assume(cfg):
    """host -> the account's read-only role (with its ExternalId); optional via_role_arn hop first."""
    caller = Aws()
    session = f"rg-collector-{cfg['tenant']}"
    if cfg.get("via_role_arn"):
        hop = caller("sts:AssumeRole", ["sts", "assume-role", "--role-arn", cfg["via_role_arn"],
                                        "--role-session-name", session])
        if not hop:
            sys.exit(f"assume-role (tenant hop) failed: {caller.errors}")
        caller = Aws(hop["Credentials"])
    out = caller("sts:AssumeRole", ["sts", "assume-role", "--role-arn", cfg["role_arn"], "--role-session-name", session,
                                    "--external-id", cfg["external_id"], "--duration-seconds", "3600"])
    if not out:
        sys.exit(f"assume-role failed: {caller.errors}")
    return out["Credentials"]


# ------------------------------------------------------------------ S3 (mission A3)
def collect_s3(aws, account):
    facts = {"account_bpa": None, "access_points_collected": False, "buckets": []}
    a = aws("s3:GetAccountPublicAccessBlock", ["s3control", "get-public-access-block", "--account-id", account],
            quiet_codes=("NoSuchPublicAccessBlockConfiguration",))
    if a is not None:
        facts["account_bpa"] = {} if a.get("__absent__") else a.get("PublicAccessBlockConfiguration")
    listed = aws("s3:ListAllMyBuckets", ["s3api", "list-buckets"]) or {}
    for b in listed.get("Buckets", []):
        name = b["Name"]
        loc = aws("s3:GetBucketLocation", ["s3api", "get-bucket-location", "--bucket", name]) or {}
        region = loc.get("LocationConstraint") or "us-east-1"
        region = "eu-west-1" if region == "EU" else region
        item = {"name": name, "region": region, "bpa": None, "policy": None, "acl_grants": [], "ownership": None,
                "website": False}
        r = aws("s3:GetBucketPublicAccessBlock", ["s3api", "get-public-access-block", "--bucket", name], region,
                quiet_codes=("NoSuchPublicAccessBlockConfiguration",))
        if r is not None:
            item["bpa"] = {} if r.get("__absent__") else r.get("PublicAccessBlockConfiguration")
        r = aws("s3:GetBucketPolicy", ["s3api", "get-bucket-policy", "--bucket", name], region,
                quiet_codes=("NoSuchBucketPolicy",))
        if r and not r.get("__absent__"):
            try:
                item["policy"] = json.loads(r["Policy"])
            except (KeyError, ValueError):
                item["policy"] = None
        r = aws("s3:GetBucketAcl", ["s3api", "get-bucket-acl", "--bucket", name], region)
        if r:
            for g in r.get("Grants", []):
                gr = g.get("Grantee", {})
                if gr.get("Type") == "Group":  # only group grantees matter for public access; no IDs kept
                    item["acl_grants"].append({"grantee_uri": gr.get("URI"), "permission": g.get("Permission")})
        r = aws("s3:GetBucketOwnershipControls", ["s3api", "get-bucket-ownership-controls", "--bucket", name], region,
                quiet_codes=("OwnershipControlsNotFoundError",))
        if r and not r.get("__absent__"):
            rules = r.get("OwnershipControls", {}).get("Rules", [])
            item["ownership"] = rules[0].get("ObjectOwnership") if rules else None
        r = aws("s3:GetBucketWebsite", ["s3api", "get-bucket-website", "--bucket", name], region,
                quiet_codes=("NoSuchWebsiteConfiguration",))
        item["website"] = bool(r) and not r.get("__absent__")
        facts["buckets"].append(item)
    return facts


# ------------------------------------------------------------------ Security groups (mission A6)
def collect_sg(aws, regions):
    facts = {"regions": regions, "security_groups": [], "prefix_lists": {}}
    for region in regions:
        enis = aws("ec2:DescribeNetworkInterfaces", ["ec2", "describe-network-interfaces",
                                                     "--query", "NetworkInterfaces[].Groups[].GroupId"], region) or []
        used = Counter(enis)
        sgs = aws("ec2:DescribeSecurityGroups", ["ec2", "describe-security-groups"], region) or {}
        pl_ids = set()
        for sg in sgs.get("SecurityGroups", []):
            perms = sg.get("IpPermissions", [])
            for p in perms:
                pl_ids.update(x.get("PrefixListId") for x in p.get("PrefixListIds", []))
            facts["security_groups"].append({
                "group_id": sg["GroupId"], "group_name": sg.get("GroupName", ""), "vpc_id": sg.get("VpcId", ""),
                "region": region, "owner_id": sg.get("OwnerId", ""), "ip_permissions": perms,
                "attached_enis": used.get(sg["GroupId"], 0)})
        for pl in sorted(i for i in pl_ids if i):
            meta = aws("ec2:DescribeManagedPrefixLists", ["ec2", "describe-managed-prefix-lists",
                                                          "--prefix-list-ids", pl], region) or {}
            m = (meta.get("PrefixLists") or [{}])[0]
            ent = aws("ec2:GetManagedPrefixListEntries", ["ec2", "get-managed-prefix-list-entries",
                                                          "--prefix-list-id", pl], region) or {}
            facts["prefix_lists"][pl] = {"owner_id": m.get("OwnerId"), "name": m.get("PrefixListName"),
                                         "entries": [e.get("Cidr") for e in ent.get("Entries", [])]}
    return facts


# ------------------------------------------------------------------ IAM (mission B6)
def collect_iam(aws, account):
    facts = {"policies": [], "principals": {}}
    pages = aws("iam:GetAccountAuthorizationDetails", ["iam", "get-account-authorization-details", "--filter",
                                                       "User", "Role", "Group", "LocalManagedPolicy"]) or {}
    attached = {}  # managed policy arn -> [principal arns]

    def principal(kind, p, inline_key, slr=False):
        for ip in p.get(inline_key, []):
            facts["policies"].append({
                "key": f"{kind}-{p[kind.capitalize() + 'Name']}-{ip['PolicyName']}", "arn": p["Arn"],
                "name": f"{p[kind.capitalize() + 'Name']}/{ip['PolicyName']}", "kind": f"inline ({kind})",
                "managed_by": "customer", "attached_to": [p["Arn"]], "document": ip.get("PolicyDocument"),
                "service_linked": slr})
        for mp in p.get("AttachedManagedPolicies", []):
            attached.setdefault(mp["PolicyArn"], []).append(p["Arn"])

    for u in pages.get("UserDetailList", []):
        principal("user", u, "UserPolicyList")
    for g in pages.get("GroupDetailList", []):
        principal("group", g, "GroupPolicyList")
    for r in pages.get("RoleDetailList", []):
        principal("role", r, "RolePolicyList", slr=r.get("Path", "").startswith("/aws-service-role/"))
    facts["principals"] = {"users": len(pages.get("UserDetailList", [])), "roles": len(pages.get("RoleDetailList", [])),
                           "groups": len(pages.get("GroupDetailList", []))}
    seen = set()
    for mp in pages.get("Policies", []):
        doc = next((v.get("Document") for v in mp.get("PolicyVersionList", []) if v.get("IsDefaultVersion")), None)
        seen.add(mp["Arn"])
        facts["policies"].append({"key": mp["PolicyName"], "arn": mp["Arn"], "name": mp["PolicyName"], "kind": "managed",
                                  "managed_by": "customer", "attached_to": attached.get(mp["Arn"], []), "document": doc,
                                  "service_linked": False})
    for arn in sorted(a for a in attached if a not in seen and ":aws:policy/" in a):
        meta = aws("iam:GetPolicy", ["iam", "get-policy", "--policy-arn", arn]) or {}
        ver = meta.get("Policy", {}).get("DefaultVersionId")
        if not ver:
            continue
        v = aws("iam:GetPolicyVersion", ["iam", "get-policy-version", "--policy-arn", arn, "--version-id", ver]) or {}
        name = arn.rsplit("/", 1)[-1]
        facts["policies"].append({"key": f"aws-{name}", "arn": arn, "name": name, "kind": "managed", "managed_by": "aws",
                                  "attached_to": attached[arn], "document": v.get("PolicyVersion", {}).get("Document"),
                                  "service_linked": "service-role/" in arn and all(":role/aws-service-role/" in p for p in attached[arn])})
    return facts


def tenants():
    """Every tenant the host may collect: one secret per tenant under <prefix>/hermes/tenant/."""
    host = Aws()
    out = host("secretsmanager:ListSecrets", ["secretsmanager", "list-secrets", "--filters",
                                              f"Key=name,Values={PREFIX}/hermes/tenant/"]) or {}
    return sorted(x["Name"].rsplit("/", 1)[-1] for x in out.get("SecretList", []))


def collect_tenant(tenant, only):
    cfg = tenant_config(tenant)
    aws = Aws(assume(cfg))
    who = aws("sts:GetCallerIdentity", ["sts", "get-caller-identity"]) or {}
    account = who.get("Account", cfg.get("account", ""))
    regions = cfg.get("regions") or [REGION]
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = FACTS_ROOT / tenant / day
    out.mkdir(parents=True, exist_ok=True)
    run_status = "SUCCEEDED"
    collectors = {"s3": lambda: collect_s3(aws, account), "sg": lambda: collect_sg(aws, regions),
                  "iam": lambda: collect_iam(aws, account)}
    summary = {}
    for name in only.split(","):
        aws.calls.clear(); aws.failed.clear(); aws.errors.clear()
        try:
            facts = collectors[name]()
            status = "PARTIAL" if aws.errors else "SUCCEEDED"
        except Budget as e:
            facts, status = {}, "PARTIAL"
            aws.errors.append({"api": "budget", "error": str(e)})
        doc = {"provider": "aws", "tenant": tenant, "account": account, "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "collector_status": status, "calls": aws.call_summary(), "errors": list(aws.errors), **facts}
        path = out / f"{name}.json"
        path.write_text(json.dumps(doc, indent=1, default=str))
        os.chown(path, CONTAINER_UID, CONTAINER_UID)
        summary[name] = {"status": status, "calls": sum(aws.calls.values()), "errors": len(aws.errors)}
        if status != "SUCCEEDED":
            run_status = "PARTIAL"
    for p in (FACTS_ROOT, FACTS_ROOT / tenant, out):
        os.chown(p, CONTAINER_UID, CONTAINER_UID)
    subprocess.run(["aws", "s3", "sync", str(out), f"s3://{BUCKET}/results/{tenant}/{day}/facts/", "--only-show-errors",
                    "--region", REGION], check=False)
    return {"tenant": tenant, "date": day, "status": run_status, "facts_dir": str(out), "collectors": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant", nargs="?", help="one tenant; omit with --all")
    ap.add_argument("--all", action="store_true", help="every tenant secret; then copy results to S3")
    ap.add_argument("--only", default="s3,sg,iam")
    a = ap.parse_args()
    if not a.all:
        if not a.tenant:
            ap.error("give a tenant or --all")
        print(json.dumps(collect_tenant(a.tenant, a.only)))
        return
    names = tenants()
    if not names:
        sys.exit("no tenant secrets found (FAILED)")
    failed = 0
    for t in names:
        try:
            print(json.dumps(collect_tenant(t, a.only)), flush=True)
        except SystemExit as e:  # tenant_config/assume exit with a message; keep going with the next tenant
            failed += 1
            print(json.dumps({"tenant": t, "status": "FAILED", "reason": str(e.code)}), flush=True)
    # The analyst's results from the last run, copied next to the facts (the volume also has daily snapshots).
    subprocess.run(["aws", "s3", "sync", "/data/hermes/results/", f"s3://{BUCKET}/results/", "--only-show-errors",
                    "--exclude", "*/facts/*", "--region", REGION], check=False)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
