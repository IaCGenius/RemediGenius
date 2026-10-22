---
name: rg-iac-fix
description: When the user asks for a fix - find the Terraform, CloudFormation or CDK code that deployed a resource named in a finding and propose a minimal, reviewable code change (unified diff) with impact, validation and rollback. Not for explaining or verifying a finding (rg-triage).
license: Apache-2.0
---
# Propose an IaC fix for a finding

Use when the user asks to fix, remediate or patch. If they only asked what a finding means or whether it is real,
answer that (rg-triage) and offer the fix.

## Steps
1. `rg_triage action=fix ref=<ref>` (add `iac_paths=["C:/path/to/repo"]` if the user names a repo
   not in `triage.yaml`). It returns:
   - candidate code locations ranked by evidence: **high** (CloudFormation logical-id tag or
     Terraform state id equals the resource), **medium** (name/prefix in code matches), **low**
     (same type, name computed — must confirm), **none** (not in code / account-level fix);
   - an excerpt of the block and the separate Terraform blocks that configure it
     (e.g. `aws_s3_bucket_public_access_block` for a bucket);
   - the remediation playbook (Terraform, CloudFormation, CLI, trade-offs).
2. Confirm the match. For **low** candidates read the file (`read_file`) and check variables /
   tfvars / naming to see whether it really produces this resource. If you cannot confirm, say
   which candidate is most likely and why, and what would confirm it (e.g. `terraform state list`).
3. Verify the finding is still true before writing code: the decisive read from the evidence guide on the
   `Guidance:` line (pass `account`). If live configuration no longer matches the finding, say so and do not write a
   fix for a problem that is not there. For IAM fixes, base the change on the policy document you read, not its name.
4. Write the change in the repo's own style: same module, naming, provider generation
   (e.g. split `aws_s3_bucket_*` resources for AWS provider v4+), variables over hard-coding.
   Prefer the smallest change that fixes the control. Present:
   ```
   File: path/to/main.tf  (match: high — state id)
   ```diff
   @@ resource "aws_s3_bucket_public_access_block" "data" @@
   -  block_public_policy     = false
   +  block_public_policy     = true
   ```
   Effect: what changes in AWS (in-place vs replacement — say when Terraform will REPLACE a
   resource, e.g. RDS storage_encrypted).
   Blast radius: who/what could break, and how to check first.
   Verify: `terraform plan` shows only the expected change; after apply, rescan (`rg_triage action=scan`)
   — Security Hub may take time to re-evaluate.
   Rollback: revert the commit / re-apply previous value.
   ```
<!-- PROTECTED_START -->
5. Save the proposal with `write_file` under the proposals folder (its path is given at session start and in
   any blocked-write message; in the Spot and workstation deployments it is `/opt/data/proposals/`):
   the diff as `<ref>-<topic>.patch` and, for Terraform, each new/changed file in full
   (`<ref>-<file>.tf`). Never edit the repository itself; other paths are blocked.
<!-- PROTECTED_END -->
6. Terraform: validate before presenting it as ready —
   `rg_triage action=validate module=<module folder> files=["<proposal>.tf=<target file name>"]`.
   It runs init (no backend) + validate + fmt on a temp copy. Fix errors from the real diagnostics
   (up to 3 attempts) and say "validated (syntax/schema), not planned". If terraform is missing,
   say it was not validated.
7. Define the **proof of done** with the fix: the decisive read-only call and the values it must return once the
   change is deployed (e.g. `s3 get_public_access_block` → `PublicAccessBlockConfiguration.BlockPublicPolicy: true`).
   Say how the change reaches AWS (their PR and CI/CD; you never apply it).
8. After the user confirms, record `decide status=fixing` with `owner` and `proof` (and `pr` once they have one). The
   desk then tracks it: in PR → deployed (proof passes) → verified (proof passes and the AWS finding is gone), or
   reopened / stalled. Show progress with `rg_triage action=fixes`. Terraform validate is syntax and schema only; the
   proof read is what shows the fix worked.

## When there is no IaC
Say so plainly. Give the operator CLI/console fix from the playbook now, plus a code snippet to bring
the resource under IaC (an `import` block for Terraform ≥1.5, or CloudFormation resource import), so the
fix does not drift back.

## Account-level controls (Config.1, CloudTrail.*, GuardDuty.1, CIS CloudWatch.*)
These are fixed by adding baseline resources. Suggest the file that already holds account-wide
resources (the tool lists files that configure the aws provider) or a new `security-baseline.tf`.
In AWS Organizations, recommend the delegated-admin/org-wide setting over per-account resources.
