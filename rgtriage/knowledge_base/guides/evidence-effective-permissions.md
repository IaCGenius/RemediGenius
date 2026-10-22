---
type: Guide
title: "Evidence: effective permissions"
description: What a principal can actually do - read policy documents, not names, and let the IAM simulator evaluate SCPs and boundaries.
tags: [remedigenius, evidence, iam, permissions, scp]
sources:
  - {id: logic, resource: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html", title: Policy evaluation logic, author: aws-documentation}
  - {id: sim, resource: "https://docs.aws.amazon.com/IAM/latest/APIReference/API_SimulatePrincipalPolicy.html", title: SimulatePrincipalPolicy, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

Question shapes: "is this role read-only?", "can X delete Y?", "would an SCP stop it?", "what is the blast radius?".

## Reads that decide it
1. Policy contents, never names. A policy called `ReadOnly` can grant writes.
   - Inline: `iam list_role_policies` (names only) then `iam get_role_policy` for each one.
   - Managed: `iam list_attached_role_policies`, then `iam get_policy` (default version id) and `iam get_policy_version`.
     AWS managed policies (`arn:aws:iam::aws:policy/...`) can be named without reading them, e.g. SecurityAudit.
   - `iam get_role` shows `PermissionsBoundary`; read it too.
2. "Can X do Y on Z?": `iam simulate_principal_policy` with `PolicySourceArn`, `ActionNames` and `ResourceArns`.
   It combines identity policies, the boundary and, in an organization, SCPs (`OrganizationsDecisionDetail`)[^sim].
   It does not include resource policies unless you pass `ResourceHandlingOption`/`ResourcePolicy`, or session
   policies. Report it as "AWS's policy simulator evaluates ...", not as observed activity.
3. Resource side: bucket, key, queue and topic policies can allow or deny on their own (`s3 get_bucket_policy`,
   `kms get_key_policy`, `sqs get_queue_attributes`, `sns get_topic_attributes`)[^logic].

## Limits to say out loud
- SCP and RCP texts are readable only from the management or a delegated administrator account. From a member account
  the simulator's verdict is the evidence; say the policy text itself was not readable.
- Conditions on tags, source IP or MFA can change the answer; the simulator reports `MissingContextValues`.
- Permissions are not usage: use `RoleLastUsed` or CloudTrail for what was actually done.

## Stop when
Each action the user asked about has a verdict from a document you read or from the simulator, and anything not
evaluated (resource policies, session policies, SCP text) is named.

Related: [identity and trust](/remedigenius/guides/evidence-identity-and-trust.md) ·
[identity and root](/remedigenius/practices/identity-and-root.md)

[^logic]: Policy evaluation logic
[^sim]: SimulatePrincipalPolicy
