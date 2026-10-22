---
type: Guide
title: Where to look for evidence
description: Which read-only AWS call or knowledge concept answers each investigation question.
tags: [remedigenius, investigation, cloudtrail, evidence]
sources:
  - {id: cloudtrail, resource: "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html", title: Viewing CloudTrail event history, author: aws-documentation}
  - {id: config, resource: "https://docs.aws.amazon.com/config/latest/developerguide/view-manage-resource-console.html", title: Looking up resource configuration history, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-21T00:00:00Z"}
---

Use `rg_triage action=aws` (one read-only call) for AWS evidence and `rg_triage action=knowledge` for what the
organization has told the desk. Add `account` and `region` from the finding. Each AWS read starts with an `Evidence`
line (account, region, time, complete or partial); quote it when it matters.

A finding is a lead, not proof: its title and severity are a classification made at scan time. Verify the claim with
the smallest live read that decides it. One guide per evidence domain says which reads decide a question, what they
cannot show and when to stop:

- [Identity and trust](/remedigenius/guides/evidence-identity-and-trust.md): who can assume a role (OIDC, SAML, external accounts)
- [Effective permissions](/remedigenius/guides/evidence-effective-permissions.md): what a principal can do; the IAM simulator and SCPs
- [Network exposure](/remedigenius/guides/evidence-network-exposure.md): rule, attachment and public path
- [Data protection](/remedigenius/guides/evidence-data-protection.md): public access blocks, policies, sharing, encryption
- [Detection and history](/remedigenius/guides/evidence-detection-and-history.md): CloudTrail, Config, GuardDuty and their limits
- [Vulnerabilities](/remedigenius/guides/evidence-vulnerabilities.md): package, fix, exploitability, reachability

| Question | Where to look |
|---|---|
| Who did it, from where? | `cloudtrail lookup_events` with `LookupAttributes` on AccessKeyId, Username or ResourceName (management events, 90 days)[^cloudtrail] |
| What changed, and when? | `config get_resource_config_history` (needs AWS Config recording in that region)[^config] |
| Is it reachable from the internet? | `ec2 describe_security_groups`, `ec2 describe_instances` (public IP), `s3 get_bucket_policy_status`, `s3 get_public_access_block`, Access Analyzer findings |
| What can this identity do? | policy documents (`iam get_role_policy`, `iam get_policy_version`), never policy names; `iam simulate_principal_policy` for can-X-do-Y (includes SCPs) |
| Who can assume this role? | `iam get_role` → `AssumeRolePolicyDocument` (principal and every condition) |
| Is it still happening? | the finding's last_seen; for GuardDuty `guardduty get_findings`; for alarms `cloudwatch describe_alarm_history` |
| Is it managed by IaC? | `rg_triage action=fix` (Terraform, CloudFormation and CDK index) |
| Who owns it, how critical is it? | resource tags, then Application, Account and Team concepts (`rg_triage action=knowledge`) |
| Is the risk already accepted? | Risk Exception concepts and decisions on the finding |
| What does the organization require? | Policy and Runbook concepts |

**Limits to say out loud:** CloudTrail `lookup_events` has no S3 object-level or data events; Config history exists
only where Config records; the desk never reads secrets, object contents or KMS-protected data.

Related: [how the desk works](/remedigenius/guides/how-the-desk-works.md) ·
[threat response](/remedigenius/playbooks/threat-response.md) · [GuardDuty findings](/remedigenius/sources/guardduty.md)

[^cloudtrail]: Viewing CloudTrail event history
[^config]: Looking up resource configuration history
