"""Context-adaptive guidance: which skill, practice and evidence guide fit a finding.

Hermes still chooses and loads skills itself; the desk only says, in its tool output, which guidance fits. The skill
depends on what the user asks: explaining or verifying a finding is rg-triage (rg-investigate for threats); a fix is
rg-iac-fix only when the user asks for one. No dispatcher, no change to the tool loop.
"""
from __future__ import annotations

IDENTITY_TYPES = ("AwsIamUser", "AwsIamRole", "AwsIamAccessKey", "AwsIamPolicy", "AwsAccount")
NETWORK_TYPES = ("AwsEc2SecurityGroup", "AwsEc2NetworkAcl", "AwsEc2Instance", "AwsElbv2LoadBalancer", "AwsEc2Vpc",
                 "AwsEc2Subnet", "AwsEc2NetworkInterface")
DATA_TYPES = ("AwsS3Bucket", "AwsKmsKey", "AwsRdsDbInstance", "AwsRdsDbSnapshot", "AwsDynamoDbTable",
              "AwsEbsSnapshot", "AwsEc2Volume", "AwsSecretsManagerSecret", "AwsSnsTopic", "AwsSqsQueue")
GUIDES = "remedigenius/guides/"
FIXABLE = ("vulnerability", "exposure", "posture", "data")


def evidence_guide(finding: dict) -> str:
    """The evidence guide for the domain a finding belongs to."""
    category = finding.get("category") or ""
    resource_type = (finding.get("resource") or {}).get("type") or ""
    source = finding.get("source") or ""
    if category == "threat":
        return GUIDES + "evidence-detection-and-history.md"
    if category == "vulnerability" or source == "inspector":
        return GUIDES + "evidence-vulnerabilities.md"
    if resource_type in IDENTITY_TYPES or source == "accessanalyzer" and resource_type.startswith("AwsIam"):
        return GUIDES + "evidence-identity-and-trust.md"
    if resource_type in NETWORK_TYPES:
        return GUIDES + "evidence-network-exposure.md"
    if resource_type in DATA_TYPES or category == "data":
        return GUIDES + "evidence-data-protection.md"
    if source in ("config", "cloudwatch") or "CloudTrail" in (finding.get("control_id") or ""):
        return GUIDES + "evidence-detection-and-history.md"
    return GUIDES + "where-to-look.md"


def skill_for(finding: dict) -> tuple[str, str]:
    """The skill for explaining or verifying this finding (the default intent)."""
    category = finding.get("category") or ""
    signals = finding.get("signals") or {}
    if category == "threat" or signals.get("active_threat") or signals.get("root_usage"):
        return "rg-investigate", "an active threat: answer who, what, when and whether it was expected before anything else"
    if category in FIXABLE:
        return "rg-triage", "explain or verify it against live evidence; do not propose a fix unless asked"
    if category in ("health", "operational"):
        return "rg-triage", "an operational event: explain impact and owner"
    return "rg-triage", "explain the priority and the next step"


def guidance(finding: dict, practices: list | None = None) -> dict:
    skill, why = skill_for(finding)
    out = {"skill": skill, "why": why, "practices": [p.path for p in practices or []], "evidence": evidence_guide(finding)}
    if (finding.get("category") or "") in FIXABLE:
        out["fix_skill"] = "rg-iac-fix"
    resource_type = (finding.get("resource") or {}).get("type") or ""
    if not out["practices"] and resource_type in IDENTITY_TYPES and (finding.get("signals") or {}).get("identity_risk"):
        out["practices"] = ["remedigenius/practices/identity-and-root.md"]
    if finding.get("owner") or finding.get("knowledge"):
        out["knowledge"] = "rg-knowledge: cite the applied concepts (`rg_triage action=knowledge view=for`)"
    return out


def line(finding: dict, practices: list | None = None) -> str:
    g = guidance(finding, practices)
    text = f"Guidance: to explain or verify, load skill {g['skill']} ({g['why']})"
    if g.get("fix_skill"):
        text += f"; to fix when asked, {g['fix_skill']}"
    text += f"; evidence guide {g['evidence']}"
    if g["practices"]:
        text += "; practice " + ", ".join(g["practices"])
    return text
