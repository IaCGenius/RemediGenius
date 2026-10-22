"""Context-adaptive guidance: which skill and which practice fit a finding.

Hermes still chooses and loads skills itself; the desk only says, in its tool output, which guidance fits ("Guidance:
load skill rg-investigate; practice identity and root"). No dispatcher, no change to the tool loop.
"""
from __future__ import annotations

IDENTITY_TYPES = ("AwsIamUser", "AwsIamRole", "AwsIamAccessKey", "AwsIamPolicy", "AwsAccount")


def skill_for(finding: dict) -> tuple[str, str]:
    category = finding.get("category") or ""
    signals = finding.get("signals") or {}
    if category == "threat" or signals.get("active_threat") or signals.get("root_usage"):
        return "rg-investigate", "an active threat: answer who, what, when and whether it was expected before anything else"
    if category in ("vulnerability", "exposure", "posture", "data"):
        return "rg-iac-fix", "a configuration or package fix: locate the code and propose a reviewed change"
    if category in ("health", "operational"):
        return "rg-triage", "an operational event: explain impact and owner"
    return "rg-triage", "explain the priority and the next step"


def guidance(finding: dict, practices: list | None = None) -> dict:
    skill, why = skill_for(finding)
    out = {"skill": skill, "why": why, "practices": [p.path for p in practices or []]}
    resource_type = (finding.get("resource") or {}).get("type") or ""
    if not out["practices"] and resource_type in IDENTITY_TYPES and (finding.get("signals") or {}).get("identity_risk"):
        out["practices"] = ["remedigenius/practices/identity-and-root.md"]
    if finding.get("owner") or finding.get("knowledge"):
        out["knowledge"] = "rg-knowledge: cite the applied concepts (`rg_triage action=knowledge view=for`)"
    return out


def line(finding: dict, practices: list | None = None) -> str:
    g = guidance(finding, practices)
    text = f"Guidance: load skill {g['skill']} ({g['why']})"
    if g["practices"]:
        text += "; practice " + ", ".join(g["practices"])
    return text
