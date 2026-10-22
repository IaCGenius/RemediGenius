"""Triage profile: which accounts and regions to read, and what matters to the business.

Borrowed from the AWS Well-Architected Agent "agent profile": accounts + regions,
plain-text business goals, and application context (tags -> criticality).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

CRITICALITY_POINTS = {
    "mission_critical": 15,
    "business_critical": 10,
    "non_critical": 0,
    "test_development": -10,
}

DEFAULT_DETAIL_LIMITS = {"CRITICAL": 1000, "HIGH": 1000, "MEDIUM": 300, "LOW": 100, "INFORMATIONAL": 0}
ALL_SOURCES = ("securityhub", "securityhub-exposure", "guardduty", "inspector", "accessanalyzer", "config", "cloudwatch", "health")

EXAMPLE = """\
# RemediGenius triage profile. Edit, then run: rgtriage doctor && rgtriage scan
name: {name}

# Default regions for every account (an account can override).
regions: [{region}]

# Accounts to read. Each uses a local AWS CLI profile and/or a read-only role to assume.
# Attach the AWS managed policy SecurityAudit (or ReadOnlyAccess) to that role.
accounts:
  - name: {account_name}
    account_id: "{account_id}"
    aws_profile: {profile}
    # role_arn: arn:aws:iam::111122223333:role/RemediGeniusReadOnly
    # external_id: optional
    criticality: business_critical   # mission_critical | business_critical | non_critical | test_development
    owner: ""

# Plain-text business goals. Optional boosts raise matching findings in the queue.
goals:
  - text: Protect customer data stored in S3 and databases
    boost: {{resource_types: [AwsS3Bucket, AwsRdsDbInstance, AwsDynamoDbTable], points: 5}}
  - text: Detect and stop misuse of privileged identities
    boost: {{resource_types: [AwsIamUser, AwsIamRole, AwsIamAccessKey], signals: [identity_risk, root_usage], points: 5}}

# Applications: resources carrying these tags inherit the criticality.
applications: []
#  - name: payments
#    tags: {{app: payments}}
#    criticality: mission_critical

# Tag values that mark an environment (applies when no application matches).
environment_tag_keys: [env, environment, Environment, stage]

# Local IaC repositories used to locate the code that deployed a resource.
iac_paths: []
#  - C:/work/my-infra

sources: [securityhub, securityhub-exposure, guardduty, inspector, accessanalyzer, config, cloudwatch, health]
max_findings_per_source: 500

# Other accounts in your AWS Organization are found automatically at every scan: each one where the
# read role below can be assumed is read fully. `rgtriage onboarding` shows coverage and the one-time setup.
organization:
  discover: true
  member_role_name: RemediGeniusReadOnly
  criticality: business_critical     # default for discovered accounts; list an account above to override
"""


def home() -> Path:
    path = Path(os.environ.get("RGTRIAGE_HOME") or Path.home() / ".rgtriage")
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return Path(os.environ.get("RGTRIAGE_CONFIG") or home() / "triage.yaml")


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.exists():
        raise FileNotFoundError(f"No triage profile at {path}. Run: rgtriage init")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return normalize(data)


def normalize(data: dict) -> dict:
    data.setdefault("name", "default")
    data.setdefault("regions", ["us-east-1"])
    data.setdefault("accounts", [])
    data.setdefault("goals", [])
    data.setdefault("applications", [])
    data.setdefault("environment_tag_keys", ["env", "environment", "Environment", "stage"])
    data.setdefault("iac_paths", [])
    data.setdefault("sources", list(ALL_SOURCES))
    if "securityhub" in data["sources"] and "securityhub-exposure" not in data["sources"]:
        data["sources"].insert(data["sources"].index("securityhub") + 1, "securityhub-exposure")  # added in 0.3
    data.setdefault("max_findings_per_source", 500)
    data.setdefault("max_stored_findings", 20000)
    data.setdefault("rollup_limit", 25)
    data["detail_limits"] = {**DEFAULT_DETAIL_LIMITS, **(data.get("detail_limits") or {})}
    # Accounts in the organization that have the common read role are found and read automatically.
    data["organization"] = {"discover": True, "member_role_name": "RemediGeniusReadOnly", "criticality": "business_critical",
                            **(data.get("organization") or {})}
    for n, account in enumerate(data["accounts"]):
        if n and account.get("account_id") and not account.get("role_arn") and not account.get("aws_profile"):
            # Another account listed by id only: read it through the common member role, never as the desk's own account.
            account["role_arn"] = f"arn:aws:iam::{account['account_id']}:role/{data['organization']['member_role_name']}"
        account.setdefault("name", account.get("account_id") or account.get("aws_profile") or "default")
        account.setdefault("regions", data["regions"])
        account.setdefault("criticality", "business_critical")
        if account["criticality"] not in CRITICALITY_POINTS:
            raise ValueError(f"account {account['name']}: unknown criticality {account['criticality']}")
    return data


def write_example(path: Path, *, name: str, region: str, account_id: str, profile: str) -> None:
    text = EXAMPLE.format(name=name, region=region, account_name=name, account_id=account_id,
                          profile=profile or "default")
    path.write_text(text, encoding="utf-8")
