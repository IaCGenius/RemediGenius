---
type: Security Practice
title: Identity and root
description: Lock the root user away, require MFA, keep credentials short-lived and permissions least-privilege.
tags: [iam, root, mfa, least-privilege, cis, fsbp]
sources:
  - {id: iam-bp, resource: "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html", title: Security best practices in IAM, author: aws-documentation}
  - {id: iam-controls, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/iam-controls.html", title: Security Hub controls for IAM, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  controls: [IAM.1, IAM.2, IAM.3, IAM.4, IAM.5, IAM.6, IAM.7, IAM.8, IAM.9, IAM.10, IAM.11, IAM.12, IAM.13, IAM.14, IAM.15,
             IAM.16, IAM.17, IAM.18, IAM.19, IAM.21, IAM.22, IAM.26, IAM.27, IAM.28]
---

# Goal

Nobody uses the root user day to day; every human signs in with MFA through federation where possible; machine access
uses roles with temporary credentials; every policy grants only what the job needs.[^iam-bp]

# Why it matters

Stolen credentials are the most common way into an AWS account. Root cannot be restricted by IAM policies, a long-lived
access key in a script or laptop leaks eventually, and an `Action: "*"` policy turns one leaked key into full control.

# What checks it

| Control | Checks | Desk default |
|---|---|---|
| IAM.4 / IAM.9 / IAM.6 | root has no access key; root has MFA; root MFA is hardware | P1 when root keys exist or root is used |
| IAM.5 / IAM.19 | console users have MFA | P2 |
| IAM.3 / IAM.22 | keys rotated within 90 days; credentials unused for 45 days removed | P3, higher with identity-risk signals |
| IAM.1 / IAM.21 | no customer policy grants `*:*` or broad service wildcards | P2 |
| IAM.2 | policies attached to groups or roles, not users | P3 |
| IAM.15, IAM.16 and the other password-policy controls | length, reuse, complexity | P4 unless console users exist |
| IAM.18 / IAM.27 / IAM.28 | a support role exists; CloudShell full access not attached; an Access Analyzer external-access analyzer is on | P3 |

GuardDuty adds behaviour: `Policy:IAMUser/RootCredentialUsage`, `UnauthorizedAccess:IAMUser/*`, `CredentialAccess:*`.
Root use scales with the number of calls (+15 to +40) and identity takeover risk adds +10 (see
[how the desk works](/remedigenius/guides/how-the-desk-works.md)).

# Investigate and fix

- [Root account](/remedigenius/playbooks/root-account.md) and [IAM identities](/remedigenius/playbooks/iam-identities.md)
  playbooks; [threat response](/remedigenius/playbooks/threat-response.md) when GuardDuty is involved.
- Evidence: `iam get_account_summary`, `iam list_access_keys`, `iam get_access_key_last_used`, CloudTrail
  `lookup_events` by access key ([where to look](/remedigenius/guides/where-to-look.md)).
- Prefer IAM Identity Center and roles over IAM users; in Terraform, attach policies to roles and use condition keys
  such as `aws:SourceAccount` and `aws:PrincipalOrgID`.

# Build on it

- **Team** concepts for who owns identity (who may approve admin access, who answers a root alert at night).
- **Policy**: your rules beyond the baseline, for example "break-glass root credentials live in a safe; any root sign-in
  is an incident".
- **Risk Exception** for a known IAM user you cannot remove yet (a vendor integration), with an expiry and approver.
- **Runbook**: your steps for a leaked key, so the desk proposes them instead of generic ones.

Related: [CIS AWS Foundations Benchmark](/remedigenius/frameworks/cis-aws-foundations.md) · [IAM Access Analyzer findings](/remedigenius/sources/accessanalyzer.md) · [GuardDuty findings](/remedigenius/sources/guardduty.md)

[^iam-bp]: Security best practices in IAM
