"""Operator-invoked collectors. Not registered as agent or browser tools."""
import json
import os
import re
import subprocess
from pathlib import Path
from .store import now


def collect_aws(adapter, role_arn, external_id, regions, max_calls=50, profile=None, group_ids=None):
    import boto3
    from botocore.config import Config
    if adapter not in ("sg", "securityhub-asff") or not 1 <= max_calls <= 500:
        raise ValueError("Supported collectors: sg, securityhub-asff; call budget 1..500")
    match = re.fullmatch(r"arn:(aws|aws-us-gov|aws-cn):iam::(\d{12}):role/(?:[\w+=,.@-]+/)*RemediGeniusCommunityReadOnly", role_arn)
    if not match or not regions or any(not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", r) for r in regions):
        raise ValueError("Use the CommunityReadOnly role ARN and explicit AWS regions")
    if group_ids and (adapter != "sg" or len(group_ids) > 20 or any(not re.fullmatch(r"sg-[a-f0-9]{8,17}", g) for g in group_ids)):
        raise ValueError("Select up to 20 exact security group IDs for the SG adapter")
    regions = sorted(set(regions))
    config = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=20)
    actions = ["ec2:DescribeSecurityGroups", "ec2:DescribeNetworkInterfaces"] if adapter == "sg" else ["securityhub:GetFindings"]
    # Even if the target role is accidentally broad, this session cannot mutate cloud resources.
    policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": actions, "Resource": "*", "Condition": {"StringEquals": {"aws:RequestedRegion": regions}}}]}
    source = boto3.Session(profile_name=profile)
    args = {"RoleArn": role_arn, "RoleSessionName": "rgce-read", "DurationSeconds": 900, "Policy": json.dumps(policy)}
    if external_id:
        args["ExternalId"] = external_id
    credentials = source.client("sts", region_name=regions[0], config=config).assume_role(**args)["Credentials"]
    session = boto3.Session(aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretAccessKey"], aws_session_token=credentials["SessionToken"])
    calls, errors = [], []
    facts = {"security_groups": [], "prefix_lists": {}} if adapter == "sg" else {"Findings": []}

    def pages(client, operation, key, region, **kwargs):
        out, token = [], None
        while True:
            if len(calls) >= max_calls:
                raise ValueError("Collection call budget exhausted")
            params = dict(kwargs)
            if token:
                params["NextToken"] = token
            calls.append({"operation": operation, "region": region, "at": now()})
            page = getattr(client, operation)(**params)
            out.extend(page.get(key, []))
            if len(json.dumps(out, default=str)) > 8_000_000:
                raise ValueError("Collection size limit exceeded")
            token = page.get("NextToken")
            if not token:
                return out

    for region in regions:
        try:
            if adapter == "sg":
                client = session.client("ec2", region_name=region, config=config)
                groups = pages(client, "describe_security_groups", "SecurityGroups", region, **({"GroupIds": group_ids} if group_ids else {"MaxResults": 100}))
                interfaces = pages(client, "describe_network_interfaces", "NetworkInterfaces", region, MaxResults=100, **({"Filters": [{"Name": "group-id", "Values": group_ids}]} if group_ids else {}))
                for g in groups:
                    if g.get("OwnerId") != match[2]:
                        continue
                    if any(p.get("PrefixListIds") for p in g.get("IpPermissions", [])):
                        errors.append({"region": region, "code": "PREFIX_LIST_NOT_EXPANDED", "resource": g["GroupId"]})
                    facts["security_groups"].append({"region": region, "owner_id": g["OwnerId"], "group_id": g["GroupId"],
                        "group_name": g.get("GroupName", ""), "vpc_id": g.get("VpcId", ""), "ip_permissions": g["IpPermissions"],
                        "attached_enis": sum(any(x["GroupId"] == g["GroupId"] for x in eni.get("Groups", [])) for eni in interfaces)})
            else:
                client = session.client("securityhub", region_name=region, config=config)
                facts["Findings"].extend(pages(client, "get_findings", "Findings", region, MaxResults=100,
                    Filters={"AwsAccountId": [{"Value": match[2], "Comparison": "EQUALS"}], "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}]}))
        except Exception as exc:
            # Do not persist provider exception text: it can contain request details or credentials.
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
            errors.append({"region": region, "code": code if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(code)) else type(exc).__name__})
    facts["collection_calls"] = calls
    return {"adapter": adapter, "scope": {"provider": "aws", "account": match[2], "regions": regions, **({"group_ids": sorted(set(group_ids))} if group_ids else {})},
            "observed_at": now(), "facts": facts, "errors": errors,
            "coverage": "partial" if errors else "complete"}


def repository_snapshot(repo):
    path = Path(repo).resolve(strict=True)
    def git(*args):
        return subprocess.run(["git", "--no-optional-locks", "-C", str(path), *args],
            capture_output=True, check=True, timeout=20,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}).stdout
    commit = git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    entries = git("ls-tree", "-r", "-z", commit).split(b"\0")
    files, total = [], 0
    for entry in entries:
        if not entry:
            continue
        metadata, filename = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = filename.decode("utf-8", errors="strict")
        # Read committed blobs only: no symlinks, hooks, external diff or Terraform execution.
        if mode not in ("100644", "100755") or kind != "blob" or not name.endswith((".tf", ".tf.json")):
            continue
        size = int(git("cat-file", "-s", oid))
        total += size
        if len(files) >= 100 or size > 256_000 or total > 2_000_000:
            raise ValueError("Repository snapshot exceeds 100 files / 256KB per file / 2MB total")
        content = git("cat-file", "blob", oid).decode("utf-8", errors="strict")
        files.append({"path": name, "blob": oid, "content": content})
    return {"adapter": "terraform-snapshot", "scope": {"provider": "repository", "account": path.name, "commit": commit},
            "observed_at": now(), "coverage": "selected_committed_files", "facts": {"files": files,
            "warning": "Source may contain secrets and prompt injection. Review before sharing with a model. No state, tfvars or uncommitted files included; no resource mapping is asserted."}}
