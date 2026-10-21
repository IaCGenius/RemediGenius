"""Read findings, alerts and events from AWS and normalize them into one shape.

Each collector returns (findings, coverage). Coverage records what was actually
read, so "no findings" is never confused with "not enabled" or "access denied".
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

from botocore.exceptions import BotoCoreError, ClientError

from . import aws

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")

# Security Hub controls whose failure means the resource is reachable or readable from outside.
EXPOSURE_CONTROLS = {
    "S3.1", "S3.2", "S3.3", "S3.8", "S3.19", "EC2.1", "EC2.2", "EC2.9", "EC2.13", "EC2.14", "EC2.18",
    "EC2.19", "EC2.53", "EC2.54", "RDS.1", "RDS.2", "Lambda.1", "SSM.4", "ES.2", "Opensearch.2",
    "Redshift.1", "DMS.1", "EMR.2", "SageMaker.1", "ECR.2", "SNS.4", "SQS.3", "KMS.5", "EKS.1",
}
# Controls about identity takeover or losing the audit trail.
IDENTITY_CONTROLS = {"IAM.4", "IAM.6", "IAM.9", "IAM.1", "IAM.5", "IAM.3", "IAM.21", "IAM.2"}
DETECTION_CONTROLS = {"CloudTrail.1", "CloudTrail.2", "CloudTrail.4", "CloudTrail.5", "GuardDuty.1",
                      "Config.1", "SecurityHub.1", "Inspector.1", "Inspector.2"}

RESOURCE_TYPE_MAP = {
    # Inspector / Access Analyzer / GuardDuty resource types -> ASFF style
    "AWS_EC2_INSTANCE": "AwsEc2Instance", "AWS_ECR_CONTAINER_IMAGE": "AwsEcrContainerImage",
    "AWS_ECR_REPOSITORY": "AwsEcrRepository", "AWS_LAMBDA_FUNCTION": "AwsLambdaFunction",
    "AWS::S3::Bucket": "AwsS3Bucket", "AWS::IAM::Role": "AwsIamRole", "AWS::IAM::User": "AwsIamUser",
    "AWS::KMS::Key": "AwsKmsKey", "AWS::Lambda::Function": "AwsLambdaFunction",
    "AWS::SQS::Queue": "AwsSqsQueue", "AWS::SecretsManager::Secret": "AwsSecretsManagerSecret",
    "AWS::SNS::Topic": "AwsSnsTopic", "AWS::EC2::Snapshot": "AwsEc2Snapshot",
    "AWS::RDS::DBSnapshot": "AwsRdsDbSnapshot", "AWS::ECR::Repository": "AwsEcrRepository",
    "AWS::DynamoDB::Table": "AwsDynamoDbTable", "AWS::EFS::FileSystem": "AwsEfsFileSystem",
    "Instance": "AwsEc2Instance", "AccessKey": "AwsIamAccessKey", "S3Bucket": "AwsS3Bucket",
    "EKSCluster": "AwsEksCluster", "Lambda": "AwsLambdaFunction", "RDSDBInstance": "AwsRdsDbInstance",
    "Container": "Container", "ECSCluster": "AwsEcsCluster",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def finding_key(source: str, native_id: str) -> str:
    return hashlib.sha1(f"{source}|{native_id}".encode()).hexdigest()[:12]


def base_finding(source: str, native_id: str, **fields) -> dict:
    finding = {
        "key": finding_key(source, native_id), "source": source, "native_id": native_id,
        "product": fields.pop("product", source), "account": "", "region": "", "title": "",
        "description": "", "severity": "MEDIUM", "category": "posture", "type": "", "control_id": "",
        "resource": {"type": "", "id": "", "name": "", "tags": {}}, "first_seen": "", "last_seen": "",
        "workflow": "NEW", "remediation": {"text": "", "url": ""}, "console_url": "",
        "signals": {}, "context": {},
    }
    finding.update(fields)
    return finding


def resource_name(resource_id: str) -> str:
    """Best-effort short name from an ARN or id (bucket name, role name, instance id)."""
    rid = resource_id or ""
    if rid.startswith("arn:"):
        tail = rid.split(":", 5)[-1]
        return tail.rsplit("/", 1)[-1] if "/" in tail else tail.rsplit(":", 1)[-1]
    if rid.startswith("AWS::::Account:"):
        return rid.split(":")[-1]
    return rid.rsplit("/", 1)[-1]


def gd_label(score: float) -> str:
    if score >= 9:
        return "CRITICAL"
    if score >= 7:
        return "HIGH"
    if score >= 4:
        return "MEDIUM"
    return "LOW"


def paginate_ex(client, operation: str, result_key: str, limit: int, **params) -> tuple[list, bool]:
    """Read at most `limit` items. Returns (items, truncated) so callers can say "at least N"."""
    if limit <= 0:
        return [], False
    pages = client.get_paginator(operation).paginate(**params, PaginationConfig={"MaxItems": limit})
    items = []
    for page in pages:
        items.extend(page.get(result_key, []))
    return items[:limit], bool(pages.resume_token)


def paginate(client, operation: str, result_key: str, limit: int, **params) -> list:
    return paginate_ex(client, operation, result_key, limit, **params)[0]


# ---------------------------------------------------------------- Security Hub

def _asff_category(f: dict) -> str:
    product = f.get("ProductName", "")
    types = " ".join(f.get("Types") or [])
    if product == "Health":
        return "health"
    if any(t in types for t in ("TTPs", "Effects", "Unusual Behaviors")):
        return "threat"
    if "Vulnerabilities" in types:
        return "vulnerability"
    if "Sensitive Data" in types:
        return "data"
    return "posture"


def normalize_asff(f: dict) -> dict:
    res = (f.get("Resources") or [{}])[0]
    control = (f.get("Compliance") or {}).get("SecurityControlId") or (f.get("ProductFields") or {}).get("ControlId", "")
    region = f.get("Region") or res.get("Region") or ""
    rec = (f.get("Remediation") or {}).get("Recommendation") or {}
    finding = base_finding(
        "securityhub", f["Id"], product=f.get("ProductName", "Security Hub"),
        account=f.get("AwsAccountId", ""), region=region, title=f.get("Title", ""),
        description=(f.get("Description") or "")[:1200], severity=(f.get("Severity") or {}).get("Label", "MEDIUM"),
        category=_asff_category(f), type=(f.get("Types") or [""])[0], control_id=control,
        first_seen=f.get("FirstObservedAt") or f.get("CreatedAt", ""), last_seen=f.get("LastObservedAt") or f.get("UpdatedAt", ""),
        workflow=(f.get("Workflow") or {}).get("Status", "NEW"),
        remediation={"text": rec.get("Text", ""), "url": rec.get("Url", "")},
    )
    finding["resource"] = {"type": res.get("Type", ""), "id": res.get("Id", ""), "name": resource_name(res.get("Id", "")),
                           "tags": res.get("Tags") or {}, "details": _trim(res.get("Details"))}
    standards = [s.get("StandardsId", "") for s in (f.get("Compliance") or {}).get("AssociatedStandards") or []]
    finding["context"]["standards"] = [s.split("/")[-3] if s.count("/") >= 3 else s for s in standards]
    finding["context"]["generator"] = f.get("GeneratorId", "")
    if control in EXPOSURE_CONTROLS:
        finding["signals"]["public_exposure"] = True
    if control in IDENTITY_CONTROLS:
        finding["signals"]["identity_risk"] = True
    if control in DETECTION_CONTROLS:
        finding["signals"]["detection_gap"] = True
    if control:
        finding["console_url"] = f"https://{region}.console.aws.amazon.com/securityhub/home?region={region}#/controls/{control}"
    else:
        finding["console_url"] = (f"https://{region}.console.aws.amazon.com/securityhub/home?region={region}"
                                  f"#/findings?search=Id%3D%255Coperator%255C%253AEQUALS%255C%253A{quote(f['Id'], safe='')}")
    return finding


def collect_securityhub(session, account, region, opts):
    """Severity-tiered reads: everything that can rank high is read in full, lower tiers are capped.

    Products that were read directly (GuardDuty, Inspector, ...) are excluded server-side, so a
    40,000-finding Inspector estate is not pulled a second time through Security Hub.
    """
    sh = aws.client(session, "securityhub", region)
    sh.describe_hub()
    base = {"RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}],
            "WorkflowStatus": [{"Value": "NEW", "Comparison": "EQUALS"}, {"Value": "NOTIFIED", "Comparison": "EQUALS"}]}
    excluded = opts.get("exclude_products") or []
    if excluded:
        base["ProductName"] = [{"Value": name, "Comparison": "NOT_EQUALS"} for name in excluded]
    findings, counts, truncated = [], {}, {}
    for label in SEVERITIES:
        cap = int(opts["detail_limits"].get(label, 0))
        raw, more = paginate_ex(sh, "get_findings", "Findings", cap,
                                Filters={**base, "SeverityLabel": [{"Value": label, "Comparison": "EQUALS"}]},
                                SortCriteria=[{"Field": "UpdatedAt", "SortOrder": "desc"}])
        counts[label], truncated[label] = len(raw), more
        findings.extend(normalize_asff(f) for f in raw
                        if (f.get("Compliance") or {}).get("Status") not in ("PASSED", "NOT_AVAILABLE"))
    try:
        aggregators = sh.list_finding_aggregators().get("FindingAggregators", [])
    except ClientError:
        aggregators = []
    return findings, {"aggregator": bool(aggregators), "excluded_products": excluded, "counts": counts,
                      "truncated": any(truncated.values()),
                      "truncated_severities": [k for k, v in truncated.items() if v]}


# ---------------------------------------------------------------- GuardDuty

def _gd_resource(f: dict) -> dict:
    r = f.get("Resource") or {}
    rtype = RESOURCE_TYPE_MAP.get(r.get("ResourceType", ""), r.get("ResourceType", ""))
    rid, name, tags = "", "", {}
    if r.get("InstanceDetails"):
        d = r["InstanceDetails"]
        rid = name = d.get("InstanceId", "")
        tags = {t["Key"]: t["Value"] for t in d.get("Tags") or []}
    elif r.get("S3BucketDetails"):
        d = r["S3BucketDetails"][0]
        rid, name = d.get("Arn", ""), d.get("Name", "")
        tags = {t["Key"]: t["Value"] for t in d.get("Tags") or []}
    elif r.get("AccessKeyDetails"):
        d = r["AccessKeyDetails"]
        name = d.get("UserName", "")
        rid = d.get("AccessKeyId", "") or name
        if d.get("UserType") == "Root":
            rtype = "AwsAccount"
    elif r.get("EksClusterDetails"):
        rid = r["EksClusterDetails"].get("Arn", "")
        name = r["EksClusterDetails"].get("Name", "")
    elif r.get("LambdaDetails"):
        rid = r["LambdaDetails"].get("FunctionArn", "")
        name = r["LambdaDetails"].get("FunctionName", "")
    elif r.get("RdsDbInstanceDetails"):
        rid = r["RdsDbInstanceDetails"].get("DbInstanceArn", "")
        name = r["RdsDbInstanceDetails"].get("DbInstanceIdentifier", "")
    return {"type": rtype, "id": rid, "name": name or resource_name(rid), "tags": tags}


def normalize_guardduty(f: dict) -> dict:
    svc = f.get("Service") or {}
    action = svc.get("Action") or {}
    region = f.get("Region", "")
    finding = base_finding(
        "guardduty", f["Arn"], product="GuardDuty", account=f.get("AccountId", ""), region=region,
        title=f.get("Title", ""), description=(f.get("Description") or "")[:1200],
        severity=gd_label(float(f.get("Severity", 0))), category="threat", type=f.get("Type", ""),
        first_seen=svc.get("EventFirstSeen") or f.get("CreatedAt", ""), last_seen=svc.get("EventLastSeen") or f.get("UpdatedAt", ""),
        console_url=f"https://{region}.console.aws.amazon.com/guardduty/home?region={region}#/findings?fId={f.get('Id','')}",
        remediation={"text": "Follow the GuardDuty remediation guide for this finding type.",
                     "url": "https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_remediate.html"},
    )
    finding["resource"] = _gd_resource(f)
    finding["signals"]["active_threat"] = True
    finding["signals"]["event_count"] = svc.get("Count", 1)
    ftype = f.get("Type", "")
    if "RootCredentialUsage" in ftype or (f.get("Resource", {}).get("AccessKeyDetails") or {}).get("UserType") == "Root":
        finding["signals"]["identity_risk"] = True
        finding["signals"]["root_usage"] = True
    s3 = (f.get("Resource", {}).get("S3BucketDetails") or [{}])[0]
    if ((s3.get("PublicAccess") or {}).get("EffectivePermission")) == "PUBLIC":
        finding["signals"]["public_exposure"] = True
    actor = {}
    api = action.get("AwsApiCallAction") or {}
    if api:
        ip = api.get("RemoteIpDetails") or {}
        actor = {"api": api.get("Api"), "service": api.get("ServiceName"), "caller_type": api.get("CallerType"),
                 "ip": ip.get("IpAddressV4"), "country": (ip.get("Country") or {}).get("CountryName"),
                 "org": (ip.get("Organization") or {}).get("AsnOrg")}
    net = action.get("NetworkConnectionAction") or action.get("PortProbeAction")
    if net:
        actor["network"] = _trim(net, 600)
    ak = f.get("Resource", {}).get("AccessKeyDetails") or {}
    if ak:
        actor.update({"principal": ak.get("UserName"), "principal_type": ak.get("UserType"), "access_key": ak.get("AccessKeyId")})
    finding["context"]["actor"] = {k: v for k, v in actor.items() if v}
    finding["context"]["action_type"] = action.get("ActionType", "")
    return finding


def collect_guardduty(session, account, region, opts):
    gd = aws.client(session, "guardduty", region)
    detectors = gd.list_detectors().get("DetectorIds", [])
    if not detectors:
        raise _Disabled("GuardDuty has no detector in this region")
    detector = detectors[0]
    criteria = {"Criterion": {"service.archived": {"Eq": ["false"]}}}
    counts = {}
    try:
        stats = gd.get_findings_statistics(DetectorId=detector, FindingStatisticTypes=["COUNT_BY_SEVERITY"],
                                           FindingCriteria=criteria)["FindingStatistics"].get("CountBySeverity", {})
        for score, n in stats.items():
            label = gd_label(float(score))
            counts[label] = counts.get(label, 0) + n
    except ClientError:
        counts = {}
    ids, truncated = paginate_ex(gd, "list_findings", "FindingIds", opts["limit"], DetectorId=detector,
                                 FindingCriteria=criteria, SortCriteria={"AttributeName": "severity", "OrderBy": "DESC"})
    findings = []
    for start in range(0, len(ids), 50):
        batch = gd.get_findings(DetectorId=detector, FindingIds=ids[start:start + 50]).get("Findings", [])
        findings.extend(normalize_guardduty(f) for f in batch)
    return findings, {"detector": detector, "counts": counts, "total": sum(counts.values()) or len(ids), "truncated": truncated}


# ---------------------------------------------------------------- Inspector

def normalize_inspector(f: dict) -> dict:
    res = (f.get("resources") or [{}])[0]
    vuln = f.get("packageVulnerabilityDetails") or {}
    region = res.get("region", "")
    kind = f.get("type", "")
    finding = base_finding(
        "inspector", f["findingArn"], product="Inspector", account=f.get("awsAccountId", ""), region=region,
        title=f.get("title", ""), description=(f.get("description") or "")[:1200],
        severity=f.get("severity", "MEDIUM") if f.get("severity") in SEVERITIES else "LOW",
        category="exposure" if kind == "NETWORK_REACHABILITY" else "vulnerability", type=kind,
        control_id=vuln.get("vulnerabilityId", ""), first_seen=f.get("firstObservedAt", ""), last_seen=f.get("lastObservedAt", ""),
        remediation={"text": ((f.get("remediation") or {}).get("recommendation") or {}).get("text", ""),
                     "url": ((f.get("remediation") or {}).get("recommendation") or {}).get("Url", "")},
        console_url=f"https://{region}.console.aws.amazon.com/inspector/v2/home?region={region}#/findings/all",
    )
    rtype = RESOURCE_TYPE_MAP.get(res.get("type", ""), res.get("type", ""))
    finding["resource"] = {"type": rtype, "id": res.get("id", ""), "name": resource_name(res.get("id", "")), "tags": res.get("tags") or {}}
    finding["signals"].update({
        "exploit_available": f.get("exploitAvailable") == "YES",
        "fix_available": f.get("fixAvailable") in ("YES", "PARTIAL"),
        "epss": ((f.get("epss") or {}).get("score")),
        "inspector_score": f.get("inspectorScore"),
    })
    if kind == "NETWORK_REACHABILITY":
        finding["signals"]["public_exposure"] = True
    packages = [{"name": p.get("name"), "installed": p.get("version"), "fixed_in": p.get("fixedInVersion"),
                 "manager": p.get("packageManager")} for p in vuln.get("vulnerablePackages") or []][:5]
    if packages:
        finding["context"]["packages"] = packages
    if res.get("type") == "AWS_ECR_CONTAINER_IMAGE":
        img = (res.get("details") or {}).get("awsEcrContainerImage") or {}
        finding["context"]["image"] = {"repository": img.get("repositoryName"), "tags": img.get("imageTags"), "base": img.get("platform")}
    return finding


ROLLUPS = (
    # aggregation type, request key, response key, resource type, id field, unit noun
    ("AMI", "amiAggregation", "amiAggregation", "AwsEc2Image", "ami", "instances"),
    ("REPOSITORY", "repositoryAggregation", "repositoryAggregation", "AwsEcrRepository", "repository", "images"),
    ("AWS_LAMBDA_FUNCTION", "lambdaFunctionAggregation", "lambdaFunctionAggregation", "AwsLambdaFunction", "functionName", "functions"),
)


def _counts(sc: dict) -> dict:
    return {k: int(sc.get(k, 0) or 0) for k in ("all", "critical", "high", "medium")}


def _top_severity(c: dict) -> str:
    return "CRITICAL" if c["critical"] else "HIGH" if c["high"] else "MEDIUM" if c["medium"] else "LOW"


def _aggregate(ins, agg_type, request_key, limit, account_id):
    request = {request_key: {"sortBy": "CRITICAL", "sortOrder": "DESC"}}
    params = {"aggregationType": agg_type, "aggregationRequest": request}
    if account_id:
        params["accountIds"] = [{"comparison": "EQUALS", "value": account_id}]
    return paginate(ins, "list_finding_aggregations", "responses", limit, **params)


def inspector_rollup(kind: str, row: dict, account: str, region: str) -> dict | None:
    """One finding per fixable unit: rebuilding an AMI or image, or updating a function, clears all its CVEs."""
    _, _, response_key, rtype, id_field, unit = next(r for r in ROLLUPS if r[0] == kind)
    data = row.get(response_key) or {}
    ident = data.get(id_field)
    c = _counts(data.get("severityCounts") or {})
    if not ident or not (c["critical"] or c["high"]):
        return None
    affected = data.get("affectedInstances") or data.get("affectedImages")
    label = {"AMI": "AMI", "REPOSITORY": "ECR repository", "AWS_LAMBDA_FUNCTION": "Lambda function"}[kind]
    where = f" across {affected} {unit}" if affected else ""
    finding = base_finding(
        "inspector", f"rollup:{kind}:{data.get('accountId', account)}:{region}:{ident}", product="Inspector",
        account=data.get("accountId", account), region=region, severity=_top_severity(c), category="vulnerability",
        type=f"InspectorRollup/{kind}",
        title=f"{label} {ident}: {c['all']:,} open vulnerabilities ({c['critical']:,} critical, {c['high']:,} high){where}",
        description=(f"Inspector aggregation for {label} {ident}. Fixing the source artifact (rebuild/patch the AMI or image, "
                     "update the function's dependencies or runtime) clears these findings together."),
        console_url=f"https://{region}.console.aws.amazon.com/inspector/v2/home?region={region}#/findings/all",
        remediation={"text": "Rebuild from a patched base and redeploy; see the vulnerabilities playbook.", "url": ""},
    )
    finding["resource"] = {"type": rtype, "id": ident, "name": ident if kind != "AWS_LAMBDA_FUNCTION" else ident,
                           "tags": data.get("lambdaTags") or {}}
    finding["signals"].update({"fleet_findings": c["all"], "critical_count": c["critical"], "high_count": c["high"],
                               "rollup": True, "fix_available": True})
    finding["context"]["rollup"] = {"kind": kind, "counts": c, "affected": affected, "runtime": data.get("runtime")}
    return finding


def collect_inspector(session, account, region, opts):
    """Totals and fix units come from aggregation APIs (complete, cheap); full detail only for what can rank high."""
    ins = aws.client(session, "inspector2", region)
    status = ins.batch_get_account_status().get("accounts", [{}])
    state = ((status[0] if status else {}).get("state") or {}).get("status")
    if state not in ("ENABLED", "ENABLING"):
        raise _Disabled(f"Inspector status is {state or 'unknown'}")
    # A delegated administrator sees every member account; otherwise totals and detail cover this account only,
    # so they stay consistent and a member's findings are not counted twice when it is also onboarded.
    org_wide = bool(account.get("delegated_admin"))
    account_id = "" if org_wide else account.get("account_id", "")
    totals = {"all": 0, "critical": 0, "high": 0, "medium": 0}
    for row in _aggregate(ins, "ACCOUNT", "accountAggregation", 100, account_id):
        for k, v in _counts((row.get("accountAggregation") or {}).get("severityCounts") or {}).items():
            totals[k] += v
    findings = []
    rollup_limit = int(opts.get("rollup_limit", 25))
    for kind, request_key, *_ in ROLLUPS:
        for row in _aggregate(ins, kind, request_key, rollup_limit, account_id):
            rollup = inspector_rollup(kind, row, account_id, region)
            if rollup:
                findings.append(rollup)
    top_packages = [{"package": (r.get("packageAggregation") or {}).get("packageName"),
                     **_counts((r.get("packageAggregation") or {}).get("severityCounts") or {})}
                    for r in _aggregate(ins, "PACKAGE", "packageAggregation", 10, account_id)]
    top_vulns = [{"id": (r.get("titleAggregation") or {}).get("vulnerabilityId"),
                  "title": ((r.get("titleAggregation") or {}).get("title") or "")[:90],
                  **_counts((r.get("titleAggregation") or {}).get("severityCounts") or {})}
                 for r in _aggregate(ins, "TITLE", "titleAggregation", 10, account_id)]
    active = [{"comparison": "EQUALS", "value": "ACTIVE"}]
    scope = {"awsAccountId": [{"comparison": "EQUALS", "value": account_id}]} if account_id else {}
    limits = opts["detail_limits"]
    detail, truncated = [], False
    for severity, extra in (("CRITICAL", {}), ("HIGH", {}),
                            ("MEDIUM", {"exploitAvailable": [{"comparison": "EQUALS", "value": "YES"}]})):
        raw, more = paginate_ex(ins, "list_findings", "findings", int(limits.get(severity, 0)),
                                filterCriteria={"findingStatus": active, "severity": [{"comparison": "EQUALS", "value": severity}],
                                                **scope, **extra},
                                sortCriteria={"field": "INSPECTOR_SCORE", "sortOrder": "DESC"})
        detail.extend(raw)
        truncated = truncated or more
    findings.extend(normalize_inspector(f) for f in detail)
    return findings, {"counts": {"CRITICAL": totals["critical"], "HIGH": totals["high"], "MEDIUM": totals["medium"]},
                      "total": totals["all"], "detailed": len(detail), "truncated": truncated, "org_wide": org_wide,
                      "top_packages": top_packages, "top_vulnerabilities": top_vulns}


# ---------------------------------------------------------------- IAM Access Analyzer

def classify_external_access(rtype: str, name: str, detail: dict, public: bool) -> tuple[str, str, bool]:
    """Severity by who is trusted: identity-provider trust is usually intended; missing OIDC conditions are not."""
    label = rtype or "Resource"
    if public:
        return "CRITICAL", f"{label} {name} is publicly accessible", True
    principal = detail.get("principal") or {}
    federated = str(principal.get("Federated", ""))
    condition = json.dumps(detail.get("condition") or {})
    if "token.actions.githubusercontent.com" in federated:
        if ":sub" not in condition:
            return ("HIGH", f"{label} {name} trusts GitHub OIDC without a repository (sub) condition: "
                    "any GitHub workflow could assume it", True)
        return "LOW", f"{label} {name} trusts GitHub OIDC (repository-scoped)", False
    if "cognito-identity" in federated:
        if "unauth" in name.lower():
            return "MEDIUM", f"{label} {name} can be assumed by unauthenticated Cognito identities", False
        return "LOW", f"{label} {name} trusts Cognito authenticated identities", False
    if federated:
        provider = federated.rsplit("/", 1)[-1] if "/" in federated else federated
        return "LOW", f"{label} {name} trusts identity provider {provider} (usually intended, e.g. SSO)", False
    accounts = principal.get("AWS")
    if accounts:
        return "MEDIUM", f"{label} {name} is trusted by external account {accounts}", False
    return "HIGH", f"{label} {name} is shared outside the zone of trust", False


def collect_accessanalyzer(session, account, region, opts):
    limit = opts["limit"]
    aa = aws.client(session, "accessanalyzer", region)
    analyzers = [a for a in aa.list_analyzers().get("analyzers", []) if a.get("status") == "ACTIVE"]
    if not analyzers:
        raise _Disabled("No active IAM Access Analyzer in this region")
    findings = []
    for analyzer in analyzers:
        external = analyzer["type"] in ("ACCOUNT", "ORGANIZATION")
        raw = paginate(aa, "list_findings_v2", "findings", limit, analyzerArn=analyzer["arn"],
                       filter={"status": {"eq": ["ACTIVE"]}})
        for f in raw:
            rtype = RESOURCE_TYPE_MAP.get(f.get("resourceType", ""), f.get("resourceType", ""))
            kind = f.get("findingType", "ExternalAccess")
            detail = {}
            if external and len(findings) < 50:
                try:
                    full = aa.get_finding(analyzerArn=analyzer["arn"], id=f["id"])["finding"]
                    detail = {"is_public": full.get("isPublic"), "principal": full.get("principal"),
                              "actions": (full.get("action") or [])[:8], "condition": full.get("condition")}
                except (ClientError, KeyError):
                    detail = {}
            public = bool(detail.get("is_public"))
            if kind == "ExternalAccess":
                sev, title, public = classify_external_access(rtype, resource_name(f.get("resource", "")), detail, public)
            else:
                sev, title = "LOW", f"{kind}: unused access on {resource_name(f.get('resource', ''))}"
            finding = base_finding(
                "accessanalyzer", f["id"], product="IAM Access Analyzer", account=f.get("resourceOwnerAccount", ""),
                region=region, title=title, severity=sev, category="exposure" if kind == "ExternalAccess" else "posture",
                type=kind, first_seen=str(f.get("createdAt", "")), last_seen=str(f.get("updatedAt", "")),
                console_url=f"https://{region}.console.aws.amazon.com/access-analyzer/home?region={region}#/findings",
                remediation={"text": "Remove the external or unused grant, or archive the finding with a reason if intended.",
                             "url": "https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-findings-remediate.html"},
            )
            finding["resource"] = {"type": rtype, "id": f.get("resource", ""), "name": resource_name(f.get("resource", "")), "tags": {}}
            finding["context"]["access"] = {k: v for k, v in detail.items() if v}
            if public:
                finding["signals"]["public_exposure"] = True
            findings.append(finding)
    return findings, {"analyzers": [a["name"] for a in analyzers]}


# ---------------------------------------------------------------- AWS Config

def collect_config(session, account, region, opts):
    limit = opts["limit"]
    cfg = aws.client(session, "config", region)
    recorders = cfg.describe_configuration_recorder_status().get("ConfigurationRecordersStatus", [])
    if not any(r.get("recording") for r in recorders):
        raise _Disabled("AWS Config is not recording in this region")
    rules = paginate(cfg, "describe_compliance_by_config_rule", "ComplianceByConfigRules", 200,
                     ComplianceTypes=["NON_COMPLIANT"])
    findings = []
    for rule in rules:
        name = rule["ConfigRuleName"]
        if name.startswith("securityhub-"):  # Security Hub controls are already read from Security Hub.
            continue
        results = paginate(cfg, "get_compliance_details_by_config_rule", "EvaluationResults",
                           max(1, limit - len(findings)), ConfigRuleName=name, ComplianceTypes=["NON_COMPLIANT"])
        for r in results:
            q = r["EvaluationResultIdentifier"]["EvaluationResultQualifier"]
            rid = q.get("ResourceId", "")
            finding = base_finding(
                "config", f"{name}|{q.get('ResourceType')}|{rid}|{region}", product="AWS Config",
                account=account.get("account_id", ""), region=region, title=f"Config rule {name} is non-compliant",
                description=(r.get("Annotation") or "")[:600], severity="MEDIUM", category="posture",
                type="ConfigRule", control_id=name, last_seen=str(r.get("ResultRecordedTime", "")),
                console_url=f"https://{region}.console.aws.amazon.com/config/home?region={region}#/rules/details?configRuleName={name}",
            )
            finding["resource"] = {"type": RESOURCE_TYPE_MAP.get(q.get("ResourceType", ""), q.get("ResourceType", "")),
                                   "id": rid, "name": rid, "tags": {}}
            findings.append(finding)
        if len(findings) >= limit:
            break
    return findings, {"non_compliant_rules": len(rules)}


# ---------------------------------------------------------------- CloudWatch alarms

SECURITY_ALARM_WORDS = ("root", "unauthorized", "iam", "cloudtrail", "securitygroup", "security-group", "nacl",
                        "console", "mfa", "kms", "guardduty", "config", "s3-policy", "vpc", "gateway")


def collect_cloudwatch(session, account, region, opts):
    limit = opts["limit"]
    cw = aws.client(session, "cloudwatch", region)
    alarms = paginate(cw, "describe_alarms", "MetricAlarms", limit, StateValue="ALARM")
    findings = []
    for a in alarms:
        security = any(w in a["AlarmName"].lower() for w in SECURITY_ALARM_WORDS)
        finding = base_finding(
            "cloudwatch", a["AlarmArn"], product="CloudWatch alarm", account=account.get("account_id", ""), region=region,
            title=f"Alarm {a['AlarmName']} is in ALARM", description=(a.get("StateReason") or "")[:600],
            severity="HIGH" if security else "MEDIUM", category="threat" if security else "operational", type="CloudWatchAlarm",
            last_seen=str(a.get("StateUpdatedTimestamp", "")),
            console_url=f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#alarmsV2:alarm/{quote(a['AlarmName'])}",
        )
        dims = {d["Name"]: d["Value"] for d in a.get("Dimensions") or []}
        finding["resource"] = {"type": "CloudWatchMetric", "id": f"{a.get('Namespace')}/{a.get('MetricName')}",
                               "name": a["AlarmName"], "tags": {}, "details": dims}
        findings.append(finding)
    return findings, {}


# ---------------------------------------------------------------- AWS Health

def collect_health(session, account, region, opts):
    limit = opts["limit"]
    health = aws.client(session, "health", "us-east-1")
    events = paginate(health, "describe_events", "events", limit,
                      filter={"eventStatusCodes": ["open", "upcoming"],
                              "eventTypeCategories": ["issue", "accountNotification", "scheduledChange"]})
    findings = []
    for e in events:
        code = e.get("eventTypeCode", "")
        sev = "HIGH" if "SECURITY" in code else ("MEDIUM" if e.get("eventTypeCategory") == "issue" else "LOW")
        finding = base_finding(
            "health", e["arn"], product="AWS Health", account=account.get("account_id", ""), region=e.get("region", ""),
            title=f"{e.get('service')} {e.get('eventTypeCategory')}: {code}", severity=sev, category="health", type=code,
            first_seen=str(e.get("startTime", "")), last_seen=str(e.get("lastUpdatedTime", "")),
            console_url="https://health.aws.amazon.com/health/home#/account/dashboard/open-issues",
        )
        finding["resource"] = {"type": "AwsHealthEvent", "id": e["arn"], "name": code, "tags": {}}
        findings.append(finding)
    return findings, {}


COLLECTORS = {
    "securityhub": collect_securityhub, "guardduty": collect_guardduty, "inspector": collect_inspector,
    "accessanalyzer": collect_accessanalyzer, "config": collect_config, "cloudwatch": collect_cloudwatch,
    "health": collect_health,
}
GLOBAL_SOURCES = {"health"}
# Products that Security Hub re-publishes; prefer the direct read when it succeeded.
SH_PRODUCT_SOURCE = {"GuardDuty": "guardduty", "Inspector": "inspector", "IAM Access Analyzer": "accessanalyzer",
                     "Health": "health", "Config": "config"}


class _Disabled(Exception):
    pass


def _trim(value, limit=1500):
    if value is None:
        return None
    text = json.dumps(value, default=str)
    return value if len(text) <= limit else {"truncated": text[:limit]}


def run_one(source, session, account, region, opts):
    entry = {"source": source, "account": account["name"], "account_id": account.get("account_id", ""), "region": region}
    try:
        findings, meta = COLLECTORS[source](session, account, region, opts)
        entry.update(status="ok", count=len(findings), **meta)
        origin = [source, entry["account_id"], region]
        for f in findings:
            f["collected_from"] = origin  # maps the finding back to the read that produced it (aggregators span regions)
        return findings, entry
    except _Disabled as exc:
        entry.update(status="not_enabled", count=0, note=str(exc))
    except aws.WriteBlocked as exc:
        entry.update(status="error", count=0, note=str(exc))
    except ClientError as exc:
        code = aws.error_code(exc)
        status = "denied" if "AccessDenied" in code or code in ("UnauthorizedOperation", "AuthorizationError") else (
            "not_enabled" if code in ("InvalidAccessException", "SubscriptionRequiredException", "BadRequestException",
                                      "ResourceNotFoundException", "NoSuchConfigurationRecorderException") else "error")
        note = f"{code}: {str(exc)[:240]}"
        if source == "health" and code == "SubscriptionRequiredException":
            status, note = "not_available", ("Health API needs a Business/Enterprise support plan; "
                                            "Health events still arrive through Security Hub when it is enabled")
        elif source == "securityhub" and code == "InvalidAccessException":
            note = "Security Hub is not enabled in this region"
        entry.update(status=status, count=0, note=note)
    except BotoCoreError as exc:
        entry.update(status="error", count=0, note=str(exc)[:240])
    return [], entry


def collect(profile: dict, sources: list[str] | None = None, progress=None) -> tuple[list[dict], list[dict]]:
    """Read every configured source for every account and region in parallel.

    Direct sources run first; Security Hub then excludes, server-side, the products that were read
    directly in that account/region, so large Inspector or GuardDuty estates are not read twice.
    """
    sources = [s for s in (sources or profile["sources"]) if s in COLLECTORS]
    opts = {"limit": int(profile.get("max_findings_per_source", 500)), "detail_limits": profile["detail_limits"],
            "rollup_limit": int(profile.get("rollup_limit", 25))}
    direct_jobs, hub_jobs, coverage = [], [], []
    for account in profile["accounts"]:
        try:
            session = aws.session_for(account)
            identity = session.client("sts").get_caller_identity()
            account["account_id"] = account.get("account_id") or identity["Account"]
        except (ClientError, BotoCoreError) as exc:
            coverage.append({"source": "credentials", "account": account["name"], "region": "-", "status": "denied",
                             "count": 0, "note": str(exc)[:240]})
            continue
        for source in sources:
            regions = ["us-east-1"] if source in GLOBAL_SOURCES else account["regions"]
            for region in regions:
                (hub_jobs if source == "securityhub" else direct_jobs).append((source, session, account, region))
    findings: list[dict] = []

    def run_all(jobs, job_opts):
        with ThreadPoolExecutor(max_workers=8) as pool:
            for found, entry in pool.map(lambda job: run_one(*job, job_opts(job)), jobs):
                if progress:
                    progress(entry)
                findings.extend(found)
                coverage.append(entry)

    run_all(direct_jobs, lambda job: opts)
    ok = {(c["source"], c.get("account_id"), c["region"]) for c in coverage if c["status"] == "ok"}

    def hub_opts(job):
        _, _, account, region = job
        excluded = [product for product, source in SH_PRODUCT_SOURCE.items()
                    if (source, account["account_id"], "us-east-1" if source in GLOBAL_SOURCES else region) in ok]
        return {**opts, "exclude_products": excluded}

    run_all(hub_jobs, hub_opts)
    return dedupe(findings, coverage), coverage


def dedupe(findings: list[dict], coverage: list[dict]) -> list[dict]:
    direct_ok = {(c["source"], c.get("account_id"), c["region"]) for c in coverage if c["status"] == "ok"}
    health_ok = {c.get("account_id") for c in coverage if c["source"] == "health" and c["status"] == "ok"}
    seen = set()
    result = []
    for f in findings:
        if f["source"] == "securityhub":
            direct = SH_PRODUCT_SOURCE.get(f["product"])
            if direct == "health" and f["account"] in health_ok:
                continue
            if direct and (direct, f["account"], f["region"]) in direct_ok:
                continue
        if f["key"] in seen:
            continue
        seen.add(f["key"])
        result.append(f)
    return result
