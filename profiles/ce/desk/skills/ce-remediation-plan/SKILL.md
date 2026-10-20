---
name: ce-remediation-plan
description: Prepare a prioritized implementation plan for selected AWS findings, then hand off to existing CLI/IaC validation and fresh reassessment. Never applies changes.
license: MIT
---

# Remediation planning

Adapted from rifteo/skills remediation-planner; see PROVENANCE.md and LICENSE.
Use for a requested implementation or fix plan, not every summary or conceptual
question. Keep one agent and the current evidence/context.

1. Establish the supported issue, affected resources and intended outcome. Separate
   incident investigation/containment decisions from preventive hardening.
2. Order work by risk reduction and dependencies: necessary immediate investigation
   or containment decision, root-cause correction, then relevant prevention. An easy
   change is not automatically the highest priority. No unrelated hardening checklist.
3. For each step give a short action and reason, suggested owner role, prerequisite,
   approval/change dependency and completion evidence. Unknown ownership stays unknown.
4. Estimate effort only when the evidence supports it; use rough relative effort
   with assumptions, or say unknown. Do not invent deadlines or fixed hours.
5. Read ce-aws-security/references/ce-fix-preparation.md for requested CLI, Terraform
   or CloudFormation drafts and relevant existing-source edits. Use SDK/provider
   schemas and actual ce_validate tools; model critique is not deterministic validation.
6. Include rollback or explain why an operator-designed recovery plan is needed.
   The operator applies changes through their change process. After they report the
   change, collect fresh evidence and check the intended condition.
7. Offer to save work with ce_case if useful. Only save on request; preserve evidence,
   decision, owner if supplied, pending dependency and reassessment criteria. Deferred
   work is not completed or accepted risk merely because a plan exists.

Commands and artifacts are proposed changes, never evidence of execution. Preserve
source severity and explicitly scoped organizational exceptions. Do not initiate
scans, exports, investigations or customer-cloud mutations to produce a plan.
