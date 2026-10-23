"""Kanban cards for people: one change to make, the exact AWS CLI to make it, a chat prompt for an IaC fix, and the
read that proves it is done. The desk only writes the text; it never runs the commands, and Hermes never starts an
agent on these cards (they are filed in triage without an assignee)."""
from __future__ import annotations

import re
import shlex

from . import playbooks, prioritize
from .collect import resource_name

KANBAN_PRIORITY = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}  # Hermes lists higher numbers first
SG_INTERNET = {"EC2.13", "EC2.14", "EC2.18", "EC2.19", "EC2.53", "EC2.54"}
SG_PORT = {"EC2.13": 22, "EC2.14": 3389}
S3_BUCKET_PUBLIC = {"S3.2", "S3.3", "S3.8", "S3.19"}
ROOT_CONTROLS = {"IAM.4", "IAM.6", "IAM.9", "CIS 1.4", "CIS 1.5", "CIS 1.6"}
PAB = "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"


def members(scan: dict, refs: list[str], find) -> list[dict]:
    """The findings a card covers: each ref plus the same issue on other resources, open ones only, best first."""
    picked: dict[str, dict] = {}
    for ref in refs:
        f = find(scan, ref)
        if not f:
            raise ValueError(f"No unique finding matches {ref!r}")
        group = prioritize.group_key(f)
        for m in scan["findings"]:
            if m["key"] == f["key"] or (prioritize.group_key(m) == group and prioritize.is_open(m)):
                picked.setdefault(m["key"], m)
    return sorted(picked.values(), key=lambda m: -m["score"])


def _q(value: str) -> str:
    return shlex.quote(str(value))


def _sg_open_rules(read, f: dict, group: str) -> list[dict] | None:
    """Internet-open inbound rules of a security group from a live read; None when the read is not possible."""
    result = read(f, "ec2", "describe_security_group_rules", {"Filters": [{"Name": "group-id", "Values": [group]}]})
    if result is None:
        return None
    return [r for r in result.get("SecurityGroupRules", []) if not r.get("IsEgress")
            and (r.get("CidrIpv4") == "0.0.0.0/0" or r.get("CidrIpv6") == "::/0")]


def _rule_text(rule: dict) -> str:
    proto = {"-1": "all traffic"}.get(str(rule.get("IpProtocol")), str(rule.get("IpProtocol")))
    lo, hi = rule.get("FromPort"), rule.get("ToPort")
    ports = "" if proto == "all traffic" or lo in (None, -1) else (f" {lo}" if lo == hi else f" {lo}-{hi}")
    return f"{proto}{ports} from {rule.get('CidrIpv4') or rule.get('CidrIpv6')}"


def commands(findings: list[dict], read) -> tuple[list[str], list[str], list[str]]:
    """(fix commands, verify commands, notes) for the findings. `read(finding, service, op, params)` is one read-only
    AWS call returning a dict, or None when it cannot be made; commands then fall back to describe-then-revoke."""
    fix, verify, notes = [], [], []
    seen: set[tuple] = set()
    for f in findings:
        control, region, account = f.get("control_id") or "", f["region"], f["account"]
        name = f["resource"].get("name") or resource_name(f["resource"].get("id", ""))
        r = f"--region {_q(region)}"
        if (control, name) in seen or (control in SG_INTERNET and ("sg", name) in seen):
            continue
        seen.add((control, name))
        if control in SG_INTERNET or (control == "EC2.2" and name.startswith("sg-")):
            seen.add(("sg", name))
            if control == "EC2.2":
                result = read(f, "ec2", "describe_security_group_rules", {"Filters": [{"Name": "group-id", "Values": [name]}]})
                rules = None if result is None else result.get("SecurityGroupRules", [])
                if rules is None:
                    fix.append(f"aws ec2 describe-security-group-rules {r} --filters Name=group-id,Values={_q(name)}"
                               "   # then revoke every rule id it lists (default group: no rules at all)")
                ingress = [x["SecurityGroupRuleId"] for x in rules or [] if not x.get("IsEgress")]
                egress = [x["SecurityGroupRuleId"] for x in rules or [] if x.get("IsEgress")]
                if ingress:
                    fix.append(f"aws ec2 revoke-security-group-ingress {r} --group-id {_q(name)} --security-group-rule-ids {' '.join(ingress)}")
                if egress:
                    fix.append(f"aws ec2 revoke-security-group-egress {r} --group-id {_q(name)} --security-group-rule-ids {' '.join(egress)}")
                if rules == []:
                    notes.append(f"{name}: the live read shows no rules left; run the verify command and record the fix.")
                notes.append(f"{name} is a default security group: move anything that uses it to its own group first.")
            else:
                rules = _sg_open_rules(read, f, name)
                if rules:
                    fix.append(f"# {name}: " + "; ".join(f"{x['SecurityGroupRuleId']} = {_rule_text(x)}" for x in rules))
                    fix.append(f"aws ec2 revoke-security-group-ingress {r} --group-id {_q(name)} --security-group-rule-ids "
                               + " ".join(x["SecurityGroupRuleId"] for x in rules))
                elif rules == []:
                    notes.append(f"{name}: the live read shows no internet-open inbound rule any more; verify and record the fix.")
                elif control in SG_PORT:
                    fix.append(f"aws ec2 revoke-security-group-ingress {r} --group-id {_q(name)} --protocol tcp "
                               f"--port {SG_PORT[control]} --cidr 0.0.0.0/0")
                else:
                    fix.append(f"aws ec2 describe-security-group-rules {r} --filters Name=group-id,Values={_q(name)}"
                               "   # find the rules open to 0.0.0.0/0 or ::/0, then:")
                    fix.append(f"aws ec2 revoke-security-group-ingress {r} --group-id {_q(name)} --security-group-rule-ids <rule-id>")
                notes.append("If people still need SSH/RDP, give them SSM Session Manager or add a narrow rule first: "
                             f"`aws ec2 authorize-security-group-ingress {r} --group-id <group> --protocol tcp --port 22 "
                             "--cidr <your-admin-cidr>/32`.")
            verify.append(f"aws ec2 describe-security-group-rules {r} --filters Name=group-id,Values={_q(name)} "
                          "--query \"SecurityGroupRules[?!IsEgress && (CidrIpv4=='0.0.0.0/0' || CidrIpv6=='::/0')]\"   # expect []")
        elif control in S3_BUCKET_PUBLIC:
            fix.append(f"aws s3api put-public-access-block --bucket {_q(name)} --public-access-block-configuration {PAB}")
            verify.append(f"aws s3api get-public-access-block --bucket {_q(name)}   # expect all four settings true")
            notes.append("Blocking public access breaks anything that serves this bucket publicly (static sites, public "
                         "downloads); use CloudFront with origin access control for those.")
        elif control == "S3.1":
            fix.append(f"aws s3control put-public-access-block --account-id {_q(account)} --public-access-block-configuration {PAB}")
            verify.append(f"aws s3control get-public-access-block --account-id {_q(account)}")
        elif control == "SSM.7":
            fix.append(f"aws ssm modify-document-permission {r} --name {_q(name)} --permission-type Share --account-ids-to-remove All")
            fix.append(f"aws ssm update-service-setting {r} --setting-id /ssm/documents/console/public-sharing-permission "
                       "--setting-value Disable   # stops new public shares in this region")
            verify.append(f"aws ssm describe-document-permission {r} --name {_q(name)} --permission-type Share   # expect no 'all'")
        elif control == "EC2.8" and name.startswith("i-"):
            fix.append(f"aws ec2 modify-instance-metadata-options {r} --instance-id {_q(name)} --http-tokens required --http-endpoint enabled")
            verify.append(f"aws ec2 describe-instances {r} --instance-ids {_q(name)} --query "
                          "\"Reservations[].Instances[].MetadataOptions.HttpTokens\"   # expect required")
            notes.append("Test the application first: old SDKs that only speak IMDSv1 stop getting credentials.")
        elif control == "EC2.7":
            fix.append(f"aws ec2 enable-ebs-encryption-by-default {r}")
            verify.append(f"aws ec2 get-ebs-encryption-by-default {r}   # expect true")
        elif control in ROOT_CONTROLS or "root" in f["title"].lower() and f["category"] != "threat":
            notes.append("Root account settings have no CLI: sign in as root in the console, then Security credentials -> "
                         "assign a hardware or passkey MFA device and delete any root access keys.")
        elif f["category"] == "threat":
            notes.append(f"{f['title'][:90]}: a threat finding. Investigate before changing anything (who, from where, "
                         "what changed); there is no fix command until the cause is known.")
        elif f["source"] == "inspector" and name.startswith("i-"):
            fix.append(f"aws ssm send-command {r} --document-name AWS-RunPatchBaseline --targets Key=InstanceIds,Values={_q(name)} "
                       "--parameters Operation=Install,RebootOption=RebootIfNeeded")
            verify.append("Inspector rescans after patching; the finding closes on its own (check the next desk scan).")
        else:
            for book in playbooks.select(f):
                for line in playbooks.load(book).splitlines():
                    if line.startswith("**CLI:**"):
                        for cmd in re.findall(r"`([^`]+)`", line):
                            fix.append(f"{cmd}   # fill in the placeholders for {name}")
    return list(dict.fromkeys(fix)), list(dict.fromkeys(verify)), list(dict.fromkeys(notes))


def build(findings: list[dict], read) -> dict:
    """Title, Hermes priority, idempotency key and markdown body for a card covering `findings` (best first)."""
    top = findings[0]
    refs = [f["key"] for f in findings]
    names = list(dict.fromkeys(f["resource"].get("name") or resource_name(f["resource"].get("id", "")) for f in findings))
    controls = list(dict.fromkeys(f.get("control_id") or f.get("type") or f["product"] for f in findings))
    where = sorted({f"{f['account']} / {f['region']}" for f in findings})
    fix, verify, notes = commands(findings, read)
    subject = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
    title = f"[{top['priority']}] {top['title'][:90]} - {subject[:80]} - ref {top['key']}"
    owner = (top.get("owner") or {}).get("title") or "not set (add an Application or Account in Knowledge)"
    lines = [f"**{top['priority']}** · {', '.join(controls[:4])} · {top['product']} {top['severity']} · {'; '.join(where[:3])}",
             f"Refs: {', '.join(refs[:12])}" + (f" (+{len(refs) - 12})" if len(refs) > 12 else ""),
             f"Resources: {', '.join(names[:12])}" + (f" (+{len(names) - 12})" if len(names) > 12 else ""),
             f"Owner: {owner}", "", "**Why this priority**"]
    lines += [f"- {reason}" for reason in top.get("reasons", [])[:4]]
    lines += ["", "**Fix with the AWS CLI** (review first, run with your own admin credentials; RemediGenius never runs these)"]
    lines += (["```bash", *fix, "```"] if fix else ["No safe one-line command for this change; use the IaC prompt below."])
    lines += [f"- {n}" for n in notes]
    lines += ["", "**Fix in code instead** (Terraform, OpenTofu, CloudFormation, CDK, Pulumi): paste into RemediGenius chat "
              "and change the tool name", "```text",
              f"Write a Terraform fix for refs {', '.join(refs[:6])} ({', '.join(controls[:3])} on {subject}). Find where these "
              "resources are defined in our IaC, propose a minimal diff in our style, validate it, and give blast radius "
              "and rollback.", "```"]
    if verify:
        lines += ["", "**Prove it is fixed**", "```bash", *verify, "```"]
    lines += ["", "**Track it**", f"Tell RemediGenius: `ref {top['key']} is fixing, owner <team>, PR <link>`. The desk checks "
              "the fix with a live read on every scan and adds a comment here when it moves to pr, deployed and verified."]
    if top.get("remediation", {}).get("url"):
        lines.append(f"AWS guidance: {top['remediation']['url']}")
    return {"title": title, "priority": KANBAN_PRIORITY.get(top["priority"], 0), "key": f"rg:{prioritize.group_key(top)}"[:120],
            "refs": refs, "body": "\n".join(lines) + "\n"}
