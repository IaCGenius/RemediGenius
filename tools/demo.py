"""RemediGenius Community Edition (RemediGenius-CE) offline demo — no AWS account, no model, no Docker.

    python tools/demo.py

Clearly synthetic findings go through the real pipeline: normalization, prioritization, the
attention board and the IaC locator (against a small generated Terraform repo).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rgtriage import collect, config, digest, iac, playbooks, prioritize  # noqa: E402

ACCOUNT = "111122223333"  # documentation account id, not a real account
NOW = "2026-10-20T12:00:00.000Z"

SECURITY_HUB = [
    {"Id": "demo-s3-8", "ProductName": "Security Hub", "AwsAccountId": ACCOUNT, "Region": "us-east-1",
     "Title": "S3.8 S3 general purpose buckets should block public access", "Severity": {"Label": "HIGH"},
     "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
     "Compliance": {"Status": "FAILED", "SecurityControlId": "S3.8"},
     "Resources": [{"Type": "AwsS3Bucket", "Id": "arn:aws:s3:::demo-payments-exports", "Tags": {"app": "payments"}}],
     "Workflow": {"Status": "NEW"}, "LastObservedAt": NOW,
     "Remediation": {"Recommendation": {"Url": "https://docs.aws.amazon.com/securityhub/latest/userguide/s3-controls.html"}}},
    {"Id": "demo-config-1", "ProductName": "Security Hub", "AwsAccountId": ACCOUNT, "Region": "us-east-1",
     "Title": "Config.1 AWS Config should be enabled", "Severity": {"Label": "CRITICAL"},
     "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
     "Compliance": {"Status": "FAILED", "SecurityControlId": "Config.1"},
     "Resources": [{"Type": "AwsAccount", "Id": f"AWS::::Account:{ACCOUNT}"}], "Workflow": {"Status": "NEW"}, "LastObservedAt": NOW},
]
GUARDDUTY = [
    {"Arn": f"arn:aws:guardduty:us-east-1:{ACCOUNT}:detector/demo/finding/1", "Id": "1", "AccountId": ACCOUNT, "Region": "us-east-1",
     "Title": "Unusual S3 reads on the payments exports bucket", "Severity": 8.0, "Type": "Exfiltration:S3/AnomalousBehavior",
     "Resource": {"ResourceType": "S3Bucket", "S3BucketDetails": [{"Name": "demo-payments-exports", "Arn": "arn:aws:s3:::demo-payments-exports",
                  "Tags": [{"Key": "app", "Value": "payments"}]}],
                  "AccessKeyDetails": {"UserName": "ci-deployer", "UserType": "IAMUser", "AccessKeyId": "AKIADEMO"}},
     "Service": {"Count": 412, "EventFirstSeen": NOW, "EventLastSeen": NOW,
                 "Action": {"ActionType": "AWS_API_CALL", "AwsApiCallAction": {"Api": "GetObject", "ServiceName": "s3.amazonaws.com",
                            "RemoteIpDetails": {"IpAddressV4": "203.0.113.50", "Country": {"CountryName": "Exampleland"}}}}}},
]
INSPECTOR = [
    {"findingArn": f"arn:aws:inspector2:us-east-1:{ACCOUNT}:finding/demo", "awsAccountId": ACCOUNT, "severity": "CRITICAL",
     "title": "CVE-2026-0001 - openssl", "type": "PACKAGE_VULNERABILITY", "exploitAvailable": "YES", "fixAvailable": "YES",
     "packageVulnerabilityDetails": {"vulnerabilityId": "CVE-2026-0001", "vulnerablePackages": [
         {"name": "openssl", "version": "3.0.1", "fixedInVersion": "3.0.9", "packageManager": "OS"}]},
     "resources": [{"type": "AWS_EC2_INSTANCE", "id": "i-0demo", "region": "us-east-1", "tags": {"env": "prod"}}]},
]
TERRAFORM = '''resource "aws_s3_bucket" "exports" {
  bucket = "demo-payments-exports"
}

resource "aws_s3_bucket_public_access_block" "exports" {
  bucket                  = aws_s3_bucket.exports.id
  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}
'''


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    profile = config.normalize({"name": "demo (synthetic data)", "accounts": [{"name": "demo", "account_id": ACCOUNT}],
                                "applications": [{"name": "payments", "tags": {"app": "payments"}, "criticality": "mission_critical"}]})
    findings = ([collect.normalize_asff(f) for f in SECURITY_HUB] + [collect.normalize_guardduty(f) for f in GUARDDUTY]
                + [collect.normalize_inspector(f) for f in INSPECTOR])
    findings, issues = prioritize.prioritize(findings, profile)
    coverage = [{"source": s, "account": "demo", "account_id": ACCOUNT, "region": "us-east-1", "status": "ok", "count": 1}
                for s in ("securityhub", "guardduty", "inspector")]
    coverage.append({"source": "config", "account": "demo", "account_id": ACCOUNT, "region": "us-east-1",
                     "status": "not_enabled", "count": 0, "note": "AWS Config is not recording in this region"})
    scan = {"scanned_at": NOW.replace(".000", ""), "profile": {"name": profile["name"]}, "findings": findings,
            "issues": issues, "coverage": coverage, "changes": {}}
    print("SYNTHETIC DEMO — not a real account, not a live agent.\n")
    print(digest.markdown(scan))

    public = next(f for f in findings if f.get("control_id") == "S3.8")
    with tempfile.TemporaryDirectory() as repo:
        (Path(repo) / "storage.tf").write_text(TERRAFORM)
        match = iac.build([repo]).match(public)[0]
        print(f"\n## Where S3.8 is fixed in code (ref {public['key']})")
        print(f"{match['address']} — confidence {match['confidence']}: {match['why']}")
        for related in match["related"]:
            print(f"  configured by {related['address']} (line {related['line']}): set block_public_policy and "
                  "restrict_public_buckets to true")
    print(f"\nPlaybooks for S3.8: {', '.join(playbooks.select(public))}. In the live product the agent turns this into a "
          "reviewed diff and runs `terraform validate` on a scratch copy.")


if __name__ == "__main__":
    main()
