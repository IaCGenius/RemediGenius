---
name: ce-iam-least-privilege
description: Draft least-privilege IAM policy suggestions from collected IAM evidence. Cite exact statements and mark proposals as AI-generated requiring operator review. Use after ce-aws-security triage.
license: Apache-2.0
---

# IAM least-privilege drafting

Start from an existing receipt that contains IAM policy documents, role trust policies, or Access Analyzer findings. Do not invent permissions.

## Working procedure

1. **Frame** — Name the target role/user/policy and the receipt ID. State the time of the observation.
2. **Inspect** — Extract exact statements, actions, resources, and conditions using `ce_aws show`. Preserve original field names.
3. **Deterministic checks** — Apply the local rules in `references/least-privilege-rules.md`. Flag wildcard actions or resources that match the rules.
4. **Interpret** — Separate observed statements from suggested reductions. Cite the receipt.
5. **Propose** — Offer at most three tightened policy fragments (JSON or Terraform). Label each “AI-generated — operator review required”. Include assumptions, verification steps, and rollback.
6. **Review** — Call `ce_review` with the draft and the source receipt.

## Limits

- Does not call IAM Access Analyzer or any external service.
- Does not apply changes.
- Empty or partial policy documents are reported as incomplete evidence, not as least-privilege compliant.

Read `references/least-privilege-rules.md` for the deterministic checks.
