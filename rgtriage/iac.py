"""Locate the IaC that deployed a resource named in a finding.

Supports Terraform (.tf, variables, .tfvars, local .tfstate), CloudFormation/SAM
templates and CDK synth output (cdk.out). Matching is evidence-ranked:

  high    CloudFormation logical-id tags or Terraform state ids that equal the resource
  medium  a literal or resolvable name/prefix in code equals the resource name
  low     same resource type exists but its name is computed; the agent must confirm
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path

import yaml

SKIP_DIRS = {".git", ".terraform", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".rgce", "dist", "build"}
MAX_FILE_BYTES = 1_500_000

# Finding resource type -> IaC types that define it, plus Terraform resources that configure it separately.
TYPE_MAP = {
    "AwsS3Bucket": (["aws_s3_bucket"], ["AWS::S3::Bucket"]),
    "AwsEc2Instance": (["aws_instance", "aws_launch_template", "aws_autoscaling_group"], ["AWS::EC2::Instance", "AWS::EC2::LaunchTemplate"]),
    "AwsEc2Image": (["aws_launch_template", "aws_instance"], ["AWS::EC2::LaunchTemplate", "AWS::EC2::Instance"]),
    "AwsEc2SecurityGroup": (["aws_security_group"], ["AWS::EC2::SecurityGroup"]),
    "AwsEc2Volume": (["aws_ebs_volume"], ["AWS::EC2::Volume"]),
    "AwsEc2Vpc": (["aws_vpc"], ["AWS::EC2::VPC"]),
    "AwsIamRole": (["aws_iam_role"], ["AWS::IAM::Role"]),
    "AwsIamUser": (["aws_iam_user"], ["AWS::IAM::User"]),
    "AwsIamPolicy": (["aws_iam_policy"], ["AWS::IAM::ManagedPolicy", "AWS::IAM::Policy"]),
    "AwsIamAccessKey": (["aws_iam_access_key", "aws_iam_user"], ["AWS::IAM::AccessKey"]),
    "AwsLambdaFunction": (["aws_lambda_function"], ["AWS::Lambda::Function", "AWS::Serverless::Function"]),
    "AwsRdsDbInstance": (["aws_db_instance"], ["AWS::RDS::DBInstance"]),
    "AwsRdsDbCluster": (["aws_rds_cluster"], ["AWS::RDS::DBCluster"]),
    "AwsKmsKey": (["aws_kms_key"], ["AWS::KMS::Key"]),
    "AwsDynamoDbTable": (["aws_dynamodb_table"], ["AWS::DynamoDB::Table"]),
    "AwsEcrRepository": (["aws_ecr_repository"], ["AWS::ECR::Repository"]),
    "AwsEcrContainerImage": (["aws_ecr_repository"], ["AWS::ECR::Repository"]),
    "AwsEksCluster": (["aws_eks_cluster"], ["AWS::EKS::Cluster"]),
    "AwsSnsTopic": (["aws_sns_topic"], ["AWS::SNS::Topic"]),
    "AwsSqsQueue": (["aws_sqs_queue"], ["AWS::SQS::Queue"]),
    "AwsCloudTrailTrail": (["aws_cloudtrail"], ["AWS::CloudTrail::Trail"]),
    "AwsElbv2LoadBalancer": (["aws_lb", "aws_alb"], ["AWS::ElasticLoadBalancingV2::LoadBalancer"]),
    "AwsSecretsManagerSecret": (["aws_secretsmanager_secret"], ["AWS::SecretsManager::Secret"]),
    "AwsEfsFileSystem": (["aws_efs_file_system"], ["AWS::EFS::FileSystem"]),
    "AwsCloudFrontDistribution": (["aws_cloudfront_distribution"], ["AWS::CloudFront::Distribution"]),
    "AwsApiGatewayV2Stage": (["aws_apigatewayv2_stage"], ["AWS::ApiGatewayV2::Stage"]),
    "AwsOpenSearchServiceDomain": (["aws_opensearch_domain"], ["AWS::OpenSearchService::Domain"]),
}
# Account-level controls are fixed by adding/adjusting these resources.
ACCOUNT_FIX_TYPES = {
    "Config.1": (["aws_config_configuration_recorder", "aws_config_configuration_recorder_status", "aws_config_delivery_channel"],
                 ["AWS::Config::ConfigurationRecorder", "AWS::Config::DeliveryChannel"]),
    "CloudTrail.1": (["aws_cloudtrail"], ["AWS::CloudTrail::Trail"]),
    "CloudTrail.2": (["aws_cloudtrail"], ["AWS::CloudTrail::Trail"]),
    "CloudTrail.4": (["aws_cloudtrail"], ["AWS::CloudTrail::Trail"]),
    "CloudTrail.5": (["aws_cloudtrail"], ["AWS::CloudTrail::Trail"]),
    "GuardDuty.1": (["aws_guardduty_detector"], ["AWS::GuardDuty::Detector"]),
    "SecurityHub.1": (["aws_securityhub_account"], ["AWS::SecurityHub::Hub"]),
    "IAM.7": (["aws_iam_account_password_policy"], []), "IAM.15": (["aws_iam_account_password_policy"], []),
    "EC2.7": (["aws_ebs_encryption_by_default"], []), "S3.1": (["aws_s3_account_public_access_block"], []),
    "Macie.1": (["aws_macie2_account"], ["AWS::Macie::Session"]),
    "Inspector.1": (["aws_inspector2_enabler"], []),
}
CLOUDWATCH_CIS = (["aws_cloudwatch_log_metric_filter", "aws_cloudwatch_metric_alarm"],
                  ["AWS::Logs::MetricFilter", "AWS::CloudWatch::Alarm"])
NAME_ATTRS = ("bucket", "bucket_prefix", "name", "name_prefix", "function_name", "identifier", "identifier_prefix",
              "cluster_identifier", "repository_name", "table_name", "domain_name", "alias", "ami", "image_id")
CFN_NAME_PROPS = ("BucketName", "FunctionName", "RoleName", "UserName", "DBInstanceIdentifier", "DBClusterIdentifier",
                  "TableName", "RepositoryName", "QueueName", "TopicName", "GroupName", "ManagedPolicyName",
                  "PolicyName", "TrailName", "Name", "DomainName", "ClusterName", "KeyAlias", "ImageId")

RESOURCE_RE = re.compile(r'^\s*resource\s+"([\w-]+)"\s+"([\w-]+)"\s*\{', re.M)
VARIABLE_RE = re.compile(r'^\s*variable\s+"([\w-]+)"\s*\{', re.M)
ATTR_RE = re.compile(r'^\s*([\w-]+)\s*=\s*(.+?)\s*$', re.M)
TFVAR_RE = re.compile(r'^\s*([\w-]+)\s*=\s*"([^"]*)"\s*$', re.M)


def _iter_files(root: Path, patterns: tuple[str, ...]):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        if any(fnmatch.fnmatch(path.name, p) for p in patterns) and path.stat().st_size <= MAX_FILE_BYTES:
            yield path


def _block_end(text: str, open_index: int) -> int:
    depth, i, in_str = 0, open_index, False
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "#" or (c == "/" and text[i:i + 2] == "//"):
            nl = text.find("\n", i)
            i = len(text) if nl < 0 else nl
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1


def _line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _top_level_attrs(body: str) -> dict:
    """Attributes at depth 1 of a block body, plus a flattened tags map."""
    attrs, depth = {}, 0
    for raw in body.splitlines():
        line = raw.split("#", 1)[0]
        if depth == 0:
            m = ATTR_RE.match(line)
            if m:
                attrs[m.group(1)] = m.group(2).strip().rstrip(",")
        depth += line.count("{") - line.count("}")
    tags = {}
    m = re.search(r'\btags\s*=\s*\{(.*?)\}', body, re.S)
    if m:
        for k, v in re.findall(r'["\']?([\w:.-]+)["\']?\s*=\s*"([^"]*)"', m.group(1)):
            tags[k] = v
    attrs["__tags__"] = tags
    return attrs


def _tf_value_pattern(expr: str, variables: dict) -> str | None:
    """Turn an HCL expression into a glob pattern for the deployed name, or None if unknowable."""
    expr = expr.strip()
    m = re.fullmatch(r'var\.([\w-]+)', expr)
    if m:
        return variables.get(m.group(1))
    if not (expr.startswith('"') and expr.endswith('"')):
        return None
    value = expr[1:-1]

    def sub(match):
        inner = match.group(1).strip()
        vm = re.fullmatch(r'var\.([\w-]+)', inner)
        if vm and vm.group(1) in variables and variables[vm.group(1)] is not None:
            return variables[vm.group(1)]
        return "*"
    pattern = re.sub(r'\$\{([^}]*)\}', sub, value)
    return pattern if pattern.strip("*-_./") else None


class Index:
    def __init__(self):
        self.resources: list[dict] = []
        self.state_ids: dict[str, dict] = {}
        self.roots: list[str] = []

    def add_root(self, root: str | Path):
        root = Path(root).expanduser()
        if not root.exists():
            raise FileNotFoundError(f"IaC path not found: {root}")
        self.roots.append(str(root))
        self._index_terraform(root)
        self._index_cloudformation(root)
        self._index_tfstate(root)
        return self

    # -- Terraform
    def _index_terraform(self, root: Path):
        by_dir: dict[Path, list[Path]] = {}
        for path in _iter_files(root, ("*.tf",)):
            by_dir.setdefault(path.parent, []).append(path)
        for directory, files in by_dir.items():
            texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
            variables = self._tf_variables(directory, texts)
            for path, text in texts.items():
                for m in RESOURCE_RE.finditer(text):
                    rtype, name = m.group(1), m.group(2)
                    end = _block_end(text, m.end() - 1)
                    body = text[m.end():end]
                    attrs = _top_level_attrs(body)
                    patterns = {}
                    for attr in NAME_ATTRS:
                        if attr in attrs:
                            pattern = _tf_value_pattern(attrs[attr], variables)
                            if pattern:
                                patterns[attr] = pattern + ("*" if attr.endswith("_prefix") else "")
                    self.resources.append({
                        "tool": "terraform", "type": rtype, "address": f"{rtype}.{name}", "file": str(path),
                        "line": _line(text, m.start()), "end_line": _line(text, end), "names": patterns,
                        "tags": attrs["__tags__"], "references": sorted(set(re.findall(r'\b(aws_[\w]+\.[\w-]+)\b', body))),
                    })

    @staticmethod
    def _tf_variables(directory: Path, texts: dict) -> dict:
        variables = {}
        for text in texts.values():
            for m in VARIABLE_RE.finditer(text):
                end = _block_end(text, m.end() - 1)
                dm = re.search(r'^\s*default\s*=\s*"([^"]*)"', text[m.end():end], re.M)
                variables[m.group(1)] = dm.group(1) if dm else None
        for tfvars in sorted(directory.glob("*.tfvars")) + sorted(directory.glob("*.auto.tfvars")):
            for k, v in TFVAR_RE.findall(tfvars.read_text(encoding="utf-8", errors="replace")):
                variables[k] = v
        for tfjson in sorted(directory.glob("*.tfvars.json")):
            try:
                for k, v in json.loads(tfjson.read_text(encoding="utf-8")).items():
                    if isinstance(v, str):
                        variables[k] = v
            except (json.JSONDecodeError, AttributeError):
                pass
        return variables

    def _index_tfstate(self, root: Path):
        for path in _iter_files(root, ("*.tfstate",)):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for res in state.get("resources", []):
                if res.get("mode") != "managed":
                    continue
                address = ".".join(filter(None, [res.get("module"), res["type"], res["name"]]))
                for inst in res.get("instances", []):
                    attrs = inst.get("attributes") or {}
                    for key in ("id", "arn", "bucket", "name", "function_name", "identifier"):
                        value = attrs.get(key)
                        if isinstance(value, str) and value:
                            self.state_ids[value] = {"address": address, "state_file": str(path), "type": res["type"]}

    # -- CloudFormation / SAM / CDK
    def _index_cloudformation(self, root: Path):
        for path in _iter_files(root, ("*.yaml", "*.yml", "*.json", "*.template")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "Resources" not in text or ("AWS::" not in text):
                continue
            try:
                node = yaml.compose(text, Loader=yaml.SafeLoader)
            except yaml.YAMLError:
                continue
            resources = _mapping_get(node, "Resources")
            if resources is None or not isinstance(resources, yaml.MappingNode):
                continue
            for key_node, value_node in resources.value:
                if not isinstance(value_node, yaml.MappingNode):
                    continue
                rtype = _scalar(_mapping_get(value_node, "Type"))
                if not rtype or not rtype.startswith(("AWS::", "Custom::")):
                    continue
                props = _mapping_get(value_node, "Properties")
                names, tags = {}, {}
                if isinstance(props, yaml.MappingNode):
                    for prop in CFN_NAME_PROPS:
                        value = _mapping_get(props, prop)
                        pattern = _cfn_pattern(value)
                        if pattern:
                            names[prop] = pattern
                    tags = _cfn_tags(_mapping_get(props, "Tags"))
                    image = _cfn_pattern(_mapping_get(_mapping_get(props, "LaunchTemplateData"), "ImageId"))
                    if image:
                        names["LaunchTemplateData.ImageId"] = image
                metadata = _mapping_get(value_node, "Metadata")
                cdk_path = _scalar(_mapping_get(metadata, "aws:cdk:path")) if isinstance(metadata, yaml.MappingNode) else None
                self.resources.append({
                    "tool": "cdk" if cdk_path else "cloudformation", "type": rtype, "address": key_node.value,
                    "file": str(path), "line": key_node.start_mark.line + 1, "end_line": value_node.end_mark.line + 1,
                    "names": names, "tags": tags, "cdk_path": cdk_path, "references": [],
                })

    # -- matching
    def match(self, finding: dict, limit: int = 5) -> list[dict]:
        res = finding.get("resource") or {}
        rtype, rid, name = res.get("type", ""), res.get("id", ""), res.get("name", "")
        tags = {str(k): str(v) for k, v in (res.get("tags") or {}).items()}
        tf_types, cfn_types = TYPE_MAP.get(rtype, ([], []))
        control = finding.get("control_id", "")
        if rtype == "AwsAccount" or not tf_types:
            fix_types = ACCOUNT_FIX_TYPES.get(control) or (CLOUDWATCH_CIS if control.startswith("CloudWatch.") else None)
            if fix_types:
                return self._account_level(fix_types, control)
        candidates = []

        logical = tags.get("aws:cloudformation:logical-id")
        if logical:
            stack = tags.get("aws:cloudformation:stack-name", "")
            for r in self.resources:
                if r["tool"] in ("cloudformation", "cdk") and r["address"] == logical:
                    candidates.append(self._hit(r, "high", f"resource tag aws:cloudformation:logical-id={logical} (stack {stack})"))
        for key in filter(None, {rid, name}):
            hit = self.state_ids.get(key)
            if hit:
                short = ".".join(hit["address"].split(".")[-2:])
                r = next((x for x in self.resources if x["tool"] == "terraform" and x["address"] == short), None)
                candidates.append(self._hit(r, "high", f"Terraform state {hit['state_file']} maps {key} to {hit['address']}",
                                            address=hit["address"]))
        typed = [r for r in self.resources if r["type"] in tf_types or r["type"] in cfn_types]
        for r in typed:
            for attr, pattern in r["names"].items():
                if name and _glob_equal(pattern, name):
                    exact = "*" not in pattern
                    candidates.append(self._hit(r, "medium" if not exact else "high",
                                                f"{attr} {'=' if exact else 'matches pattern'} {pattern!r} → {name}"))
                    break
            else:
                if tags.get("Name") and r["tags"].get("Name") == tags["Name"]:
                    candidates.append(self._hit(r, "medium", f"tag Name={tags['Name']}"))
        if not candidates and typed:
            for r in typed[:limit]:
                candidates.append(self._hit(r, "low", f"same resource type ({r['type']}); name is computed or not set — confirm"))
        seen, unique = set(), []
        order = {"high": 0, "medium": 1, "low": 2}
        for c in sorted(candidates, key=lambda c: order[c["confidence"]]):
            ident = (c.get("file"), c.get("address"))
            if ident not in seen:
                seen.add(ident)
                unique.append(c)
        return unique[:limit]

    def _account_level(self, fix_types, control):
        tf_types, cfn_types = fix_types
        hits = [self._hit(r, "medium", f"{control} is fixed by {r['type']}; this code already defines one — check it is deployed to this account/region")
                for r in self.resources if r["type"] in tf_types or r["type"] in cfn_types]
        if hits:
            return hits[:5]
        providers = []
        for root in self.roots:
            for path in _iter_files(Path(root), ("*.tf",)):
                if re.search(r'^\s*provider\s+"aws"', path.read_text(encoding="utf-8", errors="replace"), re.M):
                    providers.append(str(path))
        return [{"confidence": "none", "why": f"No {', '.join(tf_types + cfn_types)} found. Add one; candidate locations "
                 f"(files that configure the aws provider): {', '.join(providers[:5]) or 'none found'}",
                 "add_resource_types": tf_types + cfn_types, "suggested_files": providers[:5]}]

    def _hit(self, r: dict | None, confidence: str, why: str, address: str | None = None) -> dict:
        if r is None:
            return {"confidence": confidence, "why": why, "address": address}
        module_dir = Path(r["file"]).parent
        related = [x for x in self.resources if x["tool"] == "terraform" and r["address"] in x.get("references", [])
                   and x["address"] != r["address"] and Path(x["file"]).parent == module_dir]
        return {"confidence": confidence, "why": why, "tool": r["tool"], "type": r["type"], "address": address or r["address"],
                "file": r["file"], "line": r["line"], "end_line": r["end_line"], "cdk_path": r.get("cdk_path"),
                "related": [{"address": x["address"], "file": x["file"], "line": x["line"]} for x in related][:12]}

    def summary(self) -> dict:
        tools: dict[str, int] = {}
        for r in self.resources:
            tools[r["tool"]] = tools.get(r["tool"], 0) + 1
        return {"roots": self.roots, "resources": len(self.resources), "by_tool": tools, "state_ids": len(self.state_ids)}


def _glob_equal(pattern: str, name: str) -> bool:
    return fnmatch.fnmatchcase(name.lower(), pattern.lower())


def _mapping_get(node, key):
    if not isinstance(node, yaml.MappingNode):
        return None
    for k, v in node.value:
        if isinstance(k, yaml.ScalarNode) and k.value == key:
            return v
    return None


def _scalar(node):
    return node.value if isinstance(node, yaml.ScalarNode) else None


def _cfn_pattern(node) -> str | None:
    if isinstance(node, yaml.ScalarNode):
        if node.tag in ("!Ref", "!GetAtt", "!ImportValue"):
            return None
        value = re.sub(r'\$\{[^}]*\}', "*", node.value)
        return value if value.strip("*-_./") else None
    if isinstance(node, yaml.MappingNode):
        sub = _mapping_get(node, "Fn::Sub")
        if isinstance(sub, yaml.ScalarNode):
            value = re.sub(r'\$\{[^}]*\}', "*", sub.value)
            return value if value.strip("*-_./") else None
    return None


def _cfn_tags(node) -> dict:
    tags = {}
    if isinstance(node, yaml.SequenceNode):
        for item in node.value:
            k, v = _scalar(_mapping_get(item, "Key")), _scalar(_mapping_get(item, "Value"))
            if k and v:
                tags[k] = v
    return tags


def excerpt(file: str, start: int, end: int, context: int = 2, max_lines: int = 80) -> str:
    lines = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
    lo, hi = max(1, start - context), min(len(lines), end + context, start + max_lines)
    return "\n".join(f"{n:5d}  {lines[n - 1]}" for n in range(lo, hi + 1))


def build(paths: list[str]) -> Index:
    index = Index()
    for path in paths:
        index.add_root(path)
    return index


def is_credential_path(path) -> bool:
    """True for a folder the agent must never be pointed at: the GitHub key folder, or anything containing or inside it."""
    home = os.environ.get("RGGITHUB_HOME")
    if not home:
        return False
    try:
        target, secret = Path(path).expanduser().resolve(), Path(home).resolve()
    except OSError:
        return True
    return target == secret or secret in target.parents or target in secret.parents
