"""Offline tests for the rgtriage package: no AWS credentials or network needed."""
import json
from datetime import datetime, timedelta, timezone

import boto3
import pytest

from rgtriage import aws, cli, collect, config, digest, iac, playbooks, prioritize, store

NOW = datetime.now(timezone.utc)
ACCOUNT = "111122223333"


def iso(delta_days=0):
    return (NOW - timedelta(days=delta_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def asff(control="S3.8", severity="HIGH", product="Security Hub", rid="arn:aws:s3:::payments-data", rtype="AwsS3Bucket",
         title=None, tags=None, types=None, fid=None):
    return {
        "Id": fid or f"arn:aws:securityhub:us-east-1:{ACCOUNT}:finding/{control}-{rid}",
        "ProductName": product, "AwsAccountId": ACCOUNT, "Region": "us-east-1",
        "Title": title or f"{control} control failed", "Description": "d", "Severity": {"Label": severity},
        "Types": types or ["Software and Configuration Checks/Industry and Regulatory Standards/AWS-Foundational-Security-Best-Practices"],
        "Compliance": {"Status": "FAILED", "SecurityControlId": control,
                       "AssociatedStandards": [{"StandardsId": "standards/aws-foundational-security-best-practices/v/1.0.0"}]},
        "Resources": [{"Type": rtype, "Id": rid, "Region": "us-east-1", "Tags": tags or {}}],
        "Workflow": {"Status": "NEW"}, "FirstObservedAt": iso(3), "LastObservedAt": iso(0),
        "Remediation": {"Recommendation": {"Text": "fix it", "Url": "https://docs.aws.amazon.com/x"}},
    }


def guardduty(ftype="Policy:IAMUser/RootCredentialUsage", severity=2.0, count=5000, bucket=None, user_type="Root"):
    resource = {"ResourceType": "AccessKey", "AccessKeyDetails": {"UserName": "Root", "UserType": user_type, "AccessKeyId": "ASIAX"}}
    if bucket:
        resource = {"ResourceType": "S3Bucket", "S3BucketDetails": [{"Name": bucket, "Arn": f"arn:aws:s3:::{bucket}",
                    "PublicAccess": {"EffectivePermission": "NOT_PUBLIC"}}],
                    "AccessKeyDetails": {"UserName": "alice", "UserType": "IAMUser", "AccessKeyId": "AKIAX"}}
    return {
        "Arn": f"arn:aws:guardduty:us-east-1:{ACCOUNT}:detector/d/finding/{ftype}-{bucket}", "Id": "f1", "AccountId": ACCOUNT,
        "Region": "us-east-1", "Title": ftype, "Description": "d", "Severity": severity, "Type": ftype,
        "CreatedAt": iso(10), "UpdatedAt": iso(0), "Resource": resource,
        "Service": {"Count": count, "EventFirstSeen": iso(10), "EventLastSeen": iso(0),
                    "Action": {"ActionType": "AWS_API_CALL", "AwsApiCallAction": {
                        "Api": "ListBuckets", "ServiceName": "s3.amazonaws.com", "CallerType": "Remote IP",
                        "RemoteIpDetails": {"IpAddressV4": "203.0.113.9", "Country": {"CountryName": "Nowhere"},
                                            "Organization": {"AsnOrg": "Example ISP"}}}}},
    }


def inspector(cve="CVE-2026-0001", severity="HIGH", exploit="YES"):
    return {
        "findingArn": f"arn:aws:inspector2:us-east-1:{ACCOUNT}:finding/{cve}", "awsAccountId": ACCOUNT,
        "title": f"{cve} - openssl", "description": "d", "severity": severity, "type": "PACKAGE_VULNERABILITY",
        "exploitAvailable": exploit, "fixAvailable": "YES", "epss": {"score": 0.4}, "inspectorScore": 8.1,
        "firstObservedAt": NOW, "lastObservedAt": NOW,
        "packageVulnerabilityDetails": {"vulnerabilityId": cve, "vulnerablePackages": [
            {"name": "openssl", "version": "3.0.1", "fixedInVersion": "3.0.9", "packageManager": "OS"}]},
        "resources": [{"type": "AWS_EC2_INSTANCE", "id": "i-0abc", "region": "us-east-1", "tags": {"env": "prod"}}],
        "remediation": {"recommendation": {"text": "upgrade"}},
    }


PROFILE = config.normalize({
    "name": "test", "regions": ["us-east-1"],
    "accounts": [{"name": "prod", "account_id": ACCOUNT, "criticality": "business_critical"}],
    "goals": [{"text": "protect data", "boost": {"resource_types": ["AwsS3Bucket"], "points": 5}}],
    "applications": [{"name": "payments", "tags": {"app": "payments"}, "criticality": "mission_critical"}],
})


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- read-only guard

def test_read_operation_classifier():
    assert aws.is_read_operation("DescribeInstances")
    assert aws.is_read_operation("GetFindings")
    assert aws.is_read_operation("ListBuckets")
    assert aws.is_read_operation("LookupEvents")
    assert not aws.is_read_operation("PutBucketPolicy")
    assert not aws.is_read_operation("DeleteBucket")
    assert not aws.is_read_operation("GetSecretValue")
    assert not aws.is_read_operation("GetObject")
    assert not aws.is_read_operation("Decrypt")
    assert not aws.is_read_operation("UpdateFindings")


def test_guarded_session_blocks_writes_before_any_request():
    session = aws.guarded(boto3.Session(aws_access_key_id="AKIAFAKE", aws_secret_access_key="fake", region_name="us-east-1"))
    s3 = session.client("s3")
    with pytest.raises(aws.WriteBlocked):
        s3.put_bucket_tagging(Bucket="b", Tagging={"TagSet": []})
    with pytest.raises(aws.WriteBlocked):
        session.client("securityhub").batch_update_findings(FindingIdentifiers=[], Note={"Text": "x", "UpdatedBy": "y"})


def test_cli_aws_refuses_writes(home, monkeypatch, capsys):
    (home / "triage.yaml").write_text("accounts: [{name: a, account_id: '1'}]\n")
    with pytest.raises(SystemExit) as exc:
        cli.main(["aws", "s3", "delete_bucket", "--params", '{"Bucket":"x"}'])
    assert "not a read-only operation" in str(exc.value)


# ---------------------------------------------------------------- normalization

def test_normalize_asff_signals_and_links():
    f = collect.normalize_asff(asff("S3.8"))
    assert f["source"] == "securityhub" and f["control_id"] == "S3.8"
    assert f["signals"]["public_exposure"] is True
    assert f["resource"]["name"] == "payments-data"
    assert "controls/S3.8" in f["console_url"]
    assert collect.normalize_asff(asff("CloudTrail.1"))["signals"]["detection_gap"]


def test_normalize_guardduty_root_and_actor():
    f = collect.normalize_guardduty(guardduty())
    assert f["severity"] == "LOW" and f["category"] == "threat"
    assert f["signals"]["root_usage"] and f["signals"]["event_count"] == 5000
    assert f["resource"]["type"] == "AwsAccount"
    assert f["context"]["actor"]["ip"] == "203.0.113.9"
    assert collect.gd_label(8.0) == "HIGH" and collect.gd_label(9.5) == "CRITICAL" and collect.gd_label(5) == "MEDIUM"


def test_normalize_inspector():
    f = collect.normalize_inspector(inspector())
    assert f["category"] == "vulnerability" and f["control_id"] == "CVE-2026-0001"
    assert f["signals"]["exploit_available"] and f["signals"]["fix_available"]
    assert f["context"]["packages"][0]["fixed_in"] == "3.0.9"
    assert f["resource"]["type"] == "AwsEc2Instance"


def test_dedupe_prefers_direct_source_when_it_was_read():
    sh_gd = collect.normalize_asff(asff(product="GuardDuty", control="", fid="arn:gd-in-sh"))
    sh_gd["product"] = "GuardDuty"
    direct = collect.normalize_guardduty(guardduty())
    cov_ok = [{"source": "guardduty", "account_id": ACCOUNT, "region": "us-east-1", "status": "ok"}]
    assert [f["source"] for f in collect.dedupe([sh_gd, direct], cov_ok)] == ["guardduty"]
    cov_off = [{"source": "guardduty", "account_id": ACCOUNT, "region": "us-east-1", "status": "denied"}]
    assert len(collect.dedupe([sh_gd, direct], cov_off)) == 2


def test_collector_errors_become_coverage_not_crashes():
    from botocore.exceptions import ClientError

    def denied(*_):
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "GetFindings")

    original = collect.COLLECTORS["securityhub"]
    collect.COLLECTORS["securityhub"] = denied
    try:
        findings, entry = collect.run_one("securityhub", None, {"name": "a", "account_id": "1"}, "us-east-1", {"limit": 10})
    finally:
        collect.COLLECTORS["securityhub"] = original
    assert findings == [] and entry["status"] == "denied"


def test_multi_account_collect_continues_past_a_failed_account(monkeypatch):
    from botocore.exceptions import ClientError

    class FakeSTS:
        def __init__(self, account):
            self.account = account

        def get_caller_identity(self):
            if self.account == "broken":
                raise ClientError({"Error": {"Code": "AccessDenied", "Message": "cannot assume"}}, "AssumeRole")
            return {"Account": self.account}

    class FakeSession:
        def __init__(self, account):
            self.account = account

        def client(self, service, **_):
            return FakeSTS(self.account)

    monkeypatch.setattr(collect.aws, "session_for", lambda account, region=None: FakeSession(account["name"]))
    seen = []
    monkeypatch.setitem(collect.COLLECTORS, "securityhub",
                        lambda session, account, region, opts: seen.append((account["account_id"], region)) or
                        ([collect.normalize_asff(asff(fid=f"{account['account_id']}-{region}"))], {}))
    profile = config.normalize({"accounts": [
        {"name": "prod", "regions": ["us-east-1", "eu-west-1"]}, {"name": "broken"}], "sources": ["securityhub"]})
    findings, coverage = collect.collect(profile)
    assert sorted(seen) == [("prod", "eu-west-1"), ("prod", "us-east-1")]
    assert len(findings) == 2
    assert any(c["source"] == "credentials" and c["account"] == "broken" and c["status"] == "denied" for c in coverage)


def test_assume_role_session_passes_external_id(monkeypatch):
    calls = {}

    class FakeBase:
        def __init__(self, **kw):
            self.events = type("E", (), {"register": lambda *a, **k: None})()

        def client(self, service, **_):
            class STS:
                def assume_role(self, **kw):
                    calls.update(kw)
                    return {"Credentials": {"AccessKeyId": "A", "SecretAccessKey": "S", "SessionToken": "T"}}
            return STS()

    monkeypatch.setattr(aws.boto3, "Session", FakeBase)
    aws.session_for({"role_arn": "arn:aws:iam::1:role/R", "external_id": "xyz"})
    assert calls["RoleArn"] == "arn:aws:iam::1:role/R" and calls["ExternalId"] == "xyz"


# ---------------------------------------------------------------- prioritization

def _prioritized(raw_findings, decisions=None):
    return prioritize.prioritize(raw_findings, PROFILE, decisions)


def test_root_usage_with_many_calls_is_p1_even_when_source_says_low():
    findings, _ = _prioritized([collect.normalize_guardduty(guardduty(count=5000))])
    f = findings[0]
    assert f["severity"] == "LOW" and f["priority"] == "P1"
    assert any("root credentials" in r for r in f["reasons"])


def test_application_tag_criticality_and_goal_boost():
    plain = collect.normalize_asff(asff("S3.9", "MEDIUM", rid="arn:aws:s3:::logs"))
    tagged = collect.normalize_asff(asff("S3.9", "MEDIUM", rid="arn:aws:s3:::pay", tags={"app": "payments"}))
    findings, _ = _prioritized([plain, tagged])
    by_name = {f["resource"]["name"]: f for f in findings}
    assert by_name["pay"]["score"] - by_name["logs"]["score"] == 5  # mission_critical +15 vs business_critical +10
    assert any("application payments" in r for r in by_name["pay"]["reasons"])
    assert any("matches goal" in r for r in by_name["pay"]["reasons"])


def test_nonprod_tag_lowers_priority():
    prod = collect.normalize_asff(asff("EC2.19", "HIGH", rid="sg-1", rtype="AwsEc2SecurityGroup", tags={"env": "prod"}))
    dev = collect.normalize_asff(asff("EC2.19", "HIGH", rid="sg-2", rtype="AwsEc2SecurityGroup", tags={"env": "dev"}))
    findings, _ = _prioritized([prod, dev])
    by = {f["resource"]["name"]: f for f in findings}
    assert by["sg-1"]["score"] > by["sg-2"]["score"]


def test_toxic_combination_on_same_resource():
    threat = collect.normalize_guardduty(guardduty("Exfiltration:S3/AnomalousBehavior", 8.0, 1, bucket="payments-data"))
    exposure = collect.normalize_asff(asff("S3.8", rid="arn:aws:s3:::payments-data"))
    findings, _ = _prioritized([threat, exposure])
    for f in findings:
        assert "toxic combination" in " ".join(f["reasons"])
        assert f["related"]


def test_cis_metric_filters_collapse_into_one_issue_and_controls_merge_across_standards():
    cis = [collect.normalize_asff(asff(f"CloudWatch.{n}", "LOW", rid=f"AWS::::Account:{ACCOUNT}", rtype="AwsAccount",
                                       fid=f"cw{n}")) for n in range(1, 15)]
    config_cis = collect.normalize_asff(asff("Config.1", "CRITICAL", rid=f"AWS::::Account:{ACCOUNT}", rtype="AwsAccount",
                                             title="2.5 AWS Config should be enabled", fid="cis-2.5"))
    config_fsbp = collect.normalize_asff(asff("Config.1", "CRITICAL", rid=f"AWS::::Account:{ACCOUNT}", rtype="AwsAccount",
                                              title="Config.1 AWS Config should be enabled", fid="fsbp-config1"))
    _, issues = _prioritized(cis + [config_cis, config_fsbp])
    assert len(issues) == 2
    cfg = next(i for i in issues if i["control_id"] == "Config.1")
    assert cfg["finding_count"] == 2 and cfg["title"].startswith("Config.1")
    family = next(i for i in issues if i["issue_key"] == "family:cis-metric-filters")
    assert family["finding_count"] == 14 and "one change" in family["title"]


def test_inspector_exploit_ranks_above_same_severity_without_exploit():
    a = collect.normalize_inspector(inspector("CVE-1", "HIGH", "YES"))
    b = collect.normalize_inspector(inspector("CVE-2", "HIGH", "NO"))
    findings, _ = _prioritized([a, b])
    assert findings[0]["control_id"] == "CVE-1"


def test_decisions_close_items():
    f = collect.normalize_asff(asff("S3.8"))
    findings, issues = _prioritized([f], {f["key"]: {"status": "accepted_risk", "reason": "public website"}})
    assert not prioritize.is_open(findings[0]) and not prioritize.is_open(issues[0])


# ---------------------------------------------------------------- state, digest, watch

def _scan(findings):
    findings, _ = prioritize.prioritize(findings, PROFILE)
    scan = {"scanned_at": collect.now_iso(), "profile": {"name": "test"}, "findings": findings,
            "coverage": [{"source": "securityhub", "account": "prod", "account_id": ACCOUNT, "region": "us-east-1", "status": "ok", "count": 1},
                         {"source": "guardduty", "account": "prod", "account_id": ACCOUNT, "region": "us-east-1", "status": "ok", "count": 1},
                         {"source": "config", "account": "prod", "account_id": ACCOUNT, "region": "us-east-1", "status": "not_enabled",
                          "count": 0, "note": "not recording"}]}
    store.mark_changes(scan)
    scan["issues"] = prioritize.build_issues(findings)
    store.save_scan(scan)
    return scan


def test_changes_new_and_resolved(home):
    first = collect.normalize_asff(asff("S3.8"))
    _scan([first])
    second = _scan([collect.normalize_asff(asff("EC2.19", rid="sg-1", rtype="AwsEc2SecurityGroup"))])
    assert second["changes"]["new"] == 1
    assert second["changes"]["no_longer_active"][0]["key"] == first["key"]
    assert store.find(second, second["findings"][0]["key"][:6])


def test_decision_roundtrip(home):
    saved = store.save_decision("abc", "fixing", "PR 42")
    assert store.load_decisions()["abc"]["reason"] == "PR 42" and saved["status"] == "fixing"
    with pytest.raises(ValueError):
        store.save_decision("abc", "ignore-me", "x")


def test_markdown_and_html(home):
    scan = _scan([collect.normalize_guardduty(guardduty(count=5000)), collect.normalize_asff(asff("S3.8", title="</script><b>x"))])
    text = digest.markdown(scan)
    assert "P1 — act now" in text and "Ref: `" in text
    assert "config not enabled" in text and "NOT a clean bill of health" in text
    page = digest.html_report(scan)
    assert "<\\/script>" in page and "</script><b>" not in page.split("const rows=")[1].split(";const $")[0]


def test_watch_is_silent_unless_new_urgent(home, monkeypatch, capsys):
    (home / "triage.yaml").write_text(f"name: t\naccounts: [{{name: prod, account_id: '{ACCOUNT}'}}]\n")
    batches = [[collect.normalize_asff(asff("S3.9", "LOW"))],
               [collect.normalize_asff(asff("S3.9", "LOW"))],
               [collect.normalize_asff(asff("S3.9", "LOW")), collect.normalize_guardduty(guardduty(count=900))]]
    cov = [{"source": s, "account": "prod", "account_id": ACCOUNT, "region": "us-east-1", "status": "ok", "count": 1}
           for s in ("securityhub", "guardduty")]

    def fake_collect(profile, sources=None, progress=None, **_):
        found = batches.pop(0)
        for f in found:
            f["collected_from"] = [f["source"], ACCOUNT, "us-east-1"]
        return found, [dict(c) for c in cov]
    monkeypatch.setattr(collect, "collect", fake_collect)
    cli.main(["watch"])
    assert "Security attention board" in capsys.readouterr().out  # first run: full board
    cli.main(["watch"])
    assert capsys.readouterr().out == ""  # nothing new: silent
    cli.main(["watch"])
    out = capsys.readouterr().out
    assert "1 new P1/P2" in out and "RootCredentialUsage" in out


# ---------------------------------------------------------------- playbooks

@pytest.mark.parametrize("finding,expected", [
    ({"control_id": "S3.8", "category": "posture"}, "s3-public-access"),
    ({"control_id": "EC2.19", "category": "posture"}, "security-group-ingress"),
    ({"control_id": "Config.1", "category": "posture"}, "detection-baseline"),
    ({"control_id": "CloudWatch.4", "category": "posture"}, "cis-metric-filters"),
    ({"type": "Policy:IAMUser/RootCredentialUsage", "category": "threat"}, "root-account"),
    ({"control_id": "CVE-1", "source": "inspector", "category": "vulnerability"}, "vulnerabilities"),
    ({"control_id": "Nope.9", "category": "posture"}, "generic"),
])
def test_playbook_selection(finding, expected):
    assert expected in playbooks.select(finding)
    for name in playbooks.select(finding):
        assert playbooks.load(name).startswith("# ")


# ---------------------------------------------------------------- IaC matching

@pytest.fixture
def repo(tmp_path):
    tf = tmp_path / "infra" / "storage"
    tf.mkdir(parents=True)
    (tf / "main.tf").write_text('''
variable "env" {
  default = "dev"
}
resource "aws_s3_bucket" "payments" {
  bucket = "payments-data"
  tags = {
    Name = "payments"
  }
}
resource "aws_s3_bucket_public_access_block" "payments" {
  bucket              = aws_s3_bucket.payments.id
  block_public_policy = false # } brace in comment
}
resource "aws_s3_bucket" "logs" {
  bucket = "acme-${var.env}-logs"
}
resource "aws_s3_bucket" "tmp" {
  bucket_prefix = "scratch-"
}
resource "aws_security_group" "web" {
  name = "web"
  ingress {
    cidr_blocks = ["0.0.0.0/0"]
  }
}
''')
    (tf / "prod.tfvars").write_text('env = "prod"\n')
    other = tmp_path / "infra" / "other"
    other.mkdir()
    (other / "main.tf").write_text('resource "aws_s3_bucket_versioning" "payments" {\n  bucket = aws_s3_bucket.payments.id\n}\n')
    (tmp_path / "infra" / "terraform.tfstate").write_text(json.dumps({"resources": [
        {"mode": "managed", "type": "aws_security_group", "name": "web",
         "instances": [{"attributes": {"id": "sg-0123", "arn": "arn:aws:ec2:us-east-1:1:security-group/sg-0123"}}]}]}))
    cfn = tmp_path / "cfn"
    cfn.mkdir()
    (cfn / "app.yaml").write_text('''AWSTemplateFormatVersion: "2010-09-09"
Resources:
  DataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub "${AWS::StackName}-data"
  AppRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: app-role
''')
    cdk = tmp_path / "cdk.out"
    cdk.mkdir()
    (cdk / "Stack.template.json").write_text(json.dumps({"Resources": {"Fn9270CBC0": {
        "Type": "AWS::Lambda::Function", "Properties": {"FunctionName": "order-handler"},
        "Metadata": {"aws:cdk:path": "Stack/OrderHandler/Resource"}}}}))
    return tmp_path


def _finding(rtype, rid, name=None, tags=None, control=""):
    return {"resource": {"type": rtype, "id": rid, "name": name or collect.resource_name(rid), "tags": tags or {}},
            "control_id": control}


def test_iac_literal_name_is_high_and_lists_same_module_related_blocks(repo):
    idx = iac.build([str(repo)])
    m = idx.match(_finding("AwsS3Bucket", "arn:aws:s3:::payments-data"))[0]
    assert m["confidence"] == "high" and m["address"] == "aws_s3_bucket.payments"
    related = [r["address"] for r in m["related"]]
    assert related == ["aws_s3_bucket_public_access_block.payments"]  # not the same-named block in another module


def test_iac_tfvars_resolved_name(repo):
    m = iac.build([str(repo)]).match(_finding("AwsS3Bucket", "arn:aws:s3:::acme-prod-logs"))[0]
    assert m["address"] == "aws_s3_bucket.logs" and m["confidence"] == "high"


def test_iac_prefix_is_medium(repo):
    m = iac.build([str(repo)]).match(_finding("AwsS3Bucket", "arn:aws:s3:::scratch-20261021abc"))[0]
    assert m["address"] == "aws_s3_bucket.tmp" and m["confidence"] == "medium"


def test_iac_tfstate_id(repo):
    m = iac.build([str(repo)]).match(_finding("AwsEc2SecurityGroup", "sg-0123"))[0]
    assert m["confidence"] == "high" and "state" in m["why"] and m["file"].endswith("main.tf")


def test_iac_cloudformation_logical_id_tag_and_sub_pattern(repo):
    idx = iac.build([str(repo)])
    tagged = _finding("AwsS3Bucket", "arn:aws:s3:::web-prod-data",
                      tags={"aws:cloudformation:logical-id": "DataBucket", "aws:cloudformation:stack-name": "web-prod"})
    m = idx.match(tagged)[0]
    assert m["confidence"] == "high" and m["tool"] == "cloudformation" and m["line"] == 3
    role = idx.match(_finding("AwsIamRole", "arn:aws:iam::1:role/app-role"))[0]
    assert role["address"] == "AppRole"


def test_iac_cdk_construct_path(repo):
    m = iac.build([str(repo)]).match(_finding("AwsLambdaFunction", "arn:aws:lambda:us-east-1:1:function:order-handler"))[0]
    assert m["tool"] == "cdk" and m["cdk_path"] == "Stack/OrderHandler/Resource"


def test_iac_unknown_name_is_low_and_account_level_suggests_location(repo, tmp_path):
    idx = iac.build([str(repo)])
    low = idx.match(_finding("AwsS3Bucket", "arn:aws:s3:::something-else"))
    assert low and all(c["confidence"] == "low" for c in low)
    account = idx.match(_finding("AwsAccount", f"AWS::::Account:{ACCOUNT}", control="Config.1"))[0]
    assert account["confidence"] == "none" and "aws_config_configuration_recorder" in account["add_resource_types"]


def test_iac_excerpt(repo):
    m = iac.build([str(repo)]).match(_finding("AwsS3Bucket", "arn:aws:s3:::payments-data"))[0]
    text = iac.excerpt(m["file"], m["line"], m["end_line"])
    assert 'resource "aws_s3_bucket" "payments"' in text


GITHUB = {"Federated": "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"}


@pytest.mark.parametrize("detail,name,severity,words", [
    ({"principal": GITHUB, "trust_policy": {"Statement": [{"Effect": "Allow", "Principal": GITHUB}]}}, "gh", "HIGH",
     "without a repository"),
    ({"principal": GITHUB, "trust_policy": {"Statement": [{"Effect": "Allow", "Principal": GITHUB, "Condition": {
        "StringEquals": {"token.actions.githubusercontent.com:sub": "repo:org/app:ref:refs/heads/main"}}}]}}, "gh", "LOW", "pinned"),
    ({"principal": GITHUB, "condition": {"StringLike": {"token.actions.githubusercontent.com:sub": "repo:org/app:*"}}}, "gh",
     "MEDIUM", "not confirmed"),
    ({"principal": {"Federated": "arn:aws:iam::1:saml-provider/AWSSSO_x"}}, "sso", "LOW", "usually intended"),
    ({"principal": {"Federated": "cognito-identity.amazonaws.com"}}, "Cognito_x_Unauth_Role", "MEDIUM", "unauthenticated"),
    ({"principal": {"AWS": "444455556666"}}, "ops-admin", "MEDIUM", "external account 444455556666"),
    ({"is_public": True}, "bucket", "CRITICAL", "publicly accessible"),
])
def test_access_analyzer_severity_reflects_who_is_trusted(detail, name, severity, words):
    sev, title, _ = collect.classify_external_access("AwsIamRole", name, detail, bool(detail.get("is_public")))
    assert sev == severity and words in title


def test_inspector_scope_member_vs_delegated_admin(monkeypatch):
    seen = {"agg": [], "list": []}

    class Ins:
        def batch_get_account_status(self):
            return {"accounts": [{"state": {"status": "ENABLED"}}]}

    def fake_paginate_ex(client, op, key, limit, **params):
        seen["list"].append(params.get("filterCriteria", {}).get("awsAccountId"))
        return [], False

    def fake_paginate(client, op, key, limit, **params):
        seen["agg"].append(params.get("accountIds"))
        return []

    monkeypatch.setattr(collect.aws, "client", lambda *a: Ins())
    monkeypatch.setattr(collect, "paginate_ex", fake_paginate_ex)
    monkeypatch.setattr(collect, "paginate", fake_paginate)
    opts = {"detail_limits": config.DEFAULT_DETAIL_LIMITS}
    collect.collect_inspector(None, {"account_id": ACCOUNT}, "us-east-1", opts)
    assert all(a == [{"comparison": "EQUALS", "value": ACCOUNT}] for a in seen["agg"] + seen["list"])
    seen["agg"].clear(); seen["list"].clear()
    _, meta = collect.collect_inspector(None, {"account_id": ACCOUNT, "delegated_admin": True}, "us-east-1", opts)
    assert all(a is None for a in seen["agg"] + seen["list"]) and meta["org_wide"]


def test_policy_evaluations_are_allowed_reads_and_marked_as_evaluations():
    for name in ("SimulatePrincipalPolicy", "SimulateCustomPolicy", "CheckNoPublicAccess", "CheckAccessNotGranted",
                 "CheckNoNewAccess", "ValidatePolicy"):
        assert aws.is_read_operation(name) and name in aws.EVALUATIONS
    for name in ("StartPolicyGeneration", "CreateAccessPreview", "StartResourceScan", "GenerateServiceLastAccessedDetails"):
        assert not aws.is_read_operation(name)



def _trust(condition):
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": GITHUB,
                                                    "Action": "sts:AssumeRoleWithWebIdentity", "Condition": condition}]}


def test_github_oidc_scope_reads_the_trust_policy():
    aud = {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}}
    assert collect.github_oidc_scope(_trust(aud))["scope"] == "none"
    sub = lambda v: {**aud, "StringLike": {"token.actions.githubusercontent.com:sub": v}}  # noqa: E731
    assert collect.github_oidc_scope(_trust(sub("*")))["scope"] == "broad"
    assert collect.github_oidc_scope(_trust(sub("repo:acme/*")))["scope"] == "broad"
    assert collect.github_oidc_scope(_trust(sub("repo:acme/infra:*")))["scope"] == "repository"
    assert collect.github_oidc_scope(_trust(sub("repo:acme/infra:ref:refs/heads/*")))["scope"] == "repository"
    assert collect.github_oidc_scope(_trust(sub(["repo:acme/infra:ref:refs/heads/main",
                                                 "repo:acme/infra:environment:prod"])))["scope"] == "pinned"
    assert collect.github_oidc_scope({"Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}}]})["scope"] == "unknown"


def test_external_access_headline_comes_from_evidence_not_from_an_empty_summary():
    principal = {"principal": GITHUB, "condition": {}}
    # Access Analyzer's condition summary is empty but the trust policy was not read: no claim either way.
    sev, title, public = collect.classify_external_access("AwsIamRole", "deploy", principal, False)
    assert sev == "MEDIUM" and "not confirmed" in title and "any GitHub workflow" not in title
    scoped = dict(principal, trust_policy=_trust({"StringLike": {"token.actions.githubusercontent.com:sub": "repo:acme/infra:*"}}))
    sev, title, _ = collect.classify_external_access("AwsIamRole", "deploy", scoped, False)
    assert sev == "MEDIUM" and "pull request of repo:acme/infra:*" in title
    open_ = dict(principal, trust_policy=_trust({"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}}))
    sev, title, public = collect.classify_external_access("AwsIamRole", "deploy", open_, False)
    assert sev == "HIGH" and "any GitHub workflow" in title and public
    # Detail could not be fetched: say so instead of guessing a HIGH headline.
    sev, title, _ = collect.classify_external_access("AwsIamRole", "deploy", {}, False)
    assert sev == "MEDIUM" and "detail not retrieved" in title
