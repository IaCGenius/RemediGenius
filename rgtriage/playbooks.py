"""Pick the remediation playbook for a finding. Playbooks are OKF concepts (type Playbook)."""
from __future__ import annotations

import re
from pathlib import Path

DIR = Path(__file__).parent / "playbooks"

# (playbook, control-id regex, finding-type/title regex). First match wins.
RULES = [
    ("root-account", r"^IAM\.(4|6|9)$", r"RootCredentialUsage|root user|\broot\b"),
    ("cis-metric-filters", r"^CloudWatch\.\d+$|^3\.\d+$", r"log metric filter and alarm"),
    ("s3-public-access", r"^S3\.(1|2|3|8|19)$", r"S3.*public|public.*S3|AwsS3Bucket is publicly"),
    ("s3-data-protection", r"^S3\.(4|5|9|14|15|17)$", None),
    ("security-group-ingress", r"^EC2\.(2|13|14|18|19|53|54)$", r"NETWORK_REACHABILITY|security group"),
    ("ec2-hardening", r"^EC2\.(7|8|9)$|^SSM\.1$", r"IMDS"),
    ("detection-baseline", r"^(Config\.1|CloudTrail\.\d+|GuardDuty\.1|SecurityHub\.1|Inspector\.\d+)$", r"^2\.\d+ "),
    ("iam-identities", r"^IAM\.\d+$", r"IAMUser|IAM entity|UnusedIAM|Unused|AccessKey"),
    ("rds-databases", r"^RDS\.\d+$", None),
    ("misc-services", r"^(KMS\.4|Lambda\.1|SQS\.3|SNS\.4|ECR\.1|EKS\.1)$", None),
]


def select(finding: dict) -> list[str]:
    control = finding.get("control_id") or ""
    text = f"{finding.get('type', '')} {finding.get('title', '')}"
    chosen = []
    if finding.get("category") == "threat":
        chosen.append("threat-response")
    if finding.get("source") == "inspector" and finding.get("category") == "vulnerability":
        chosen.append("vulnerabilities")
    for name, control_re, text_re in RULES:
        if (control and re.search(control_re, control)) or (text_re and re.search(text_re, text, re.I)):
            chosen.append(name)
            break
    if not chosen:
        chosen.append("generic")
    return list(dict.fromkeys(chosen))


def load(name: str) -> str:
    """Playbook text without its OKF frontmatter (the files are also shipped as knowledge concepts)."""
    text = (DIR / f"{name}.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5:].lstrip("\n")
    return text


def names() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.md"))
