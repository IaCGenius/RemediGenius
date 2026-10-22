---
type: Security Practice
title: Incident readiness
description: Know who to call, what to do first and how to contain, before the first real alert, including the manual CIS checks.
tags: [incident-response, guardduty, contacts, runbooks, cis]
sources:
  - {id: ir-guide, resource: "https://docs.aws.amazon.com/security-ir/latest/userguide/security-incident-response-guide.html", title: AWS Security Incident Response Guide, author: aws-documentation}
  - {id: contacts, resource: "https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-update-contact-alternate.html", title: Update the alternate contacts for your AWS account, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  controls: [Account.1, GuardDuty.1, IAM.18]
---

# Goal

Security contacts registered on every account; a support role so responders can open AWS cases; GuardDuty findings
reach a person; runbooks exist for the likely incidents; containment steps are rehearsed.[^ir-guide]

# Why it matters

The first hour decides the damage. Teams that must first find out who owns an account, who may disable a key or how
to isolate an instance lose that hour.

# What checks it

| Control | Checks |
|---|---|
| Account.1 | security contact information is provided |
| IAM.18 | a role for managing incidents with AWS Support exists |
| GuardDuty.1 | GuardDuty is enabled |

Some CIS recommendations are manual and never appear as findings: keeping account contact details current,
registering alternate (security) contacts,[^contacts] and avoiding root for everyday tasks. Check them yourself and
record the result as a Note.

# How the desk helps

- New P1/P2 findings reach you without a question: every chat opens with the board, and the `security-watch` job
  alerts on new urgent findings.
- Investigations are read-only and bounded; containment steps are proposed for the operator to run
  ([threat response](/remedigenius/playbooks/threat-response.md)).
- Decisions record what was decided and why.

# Build on it

This is where organization knowledge pays off most:

- **Team** concepts with contact and escalation for every owner, so a P1 names whom to call.
- **Runbook** concepts for your top scenarios (leaked key, public bucket, crypto-mining instance, compromised CI role).
  The desk proposes your steps instead of generic ones.
- **Policy**: who may take containment actions, and when legal or customers must be told.

Related: [GuardDuty findings](/remedigenius/sources/guardduty.md) · [Identity and root](/remedigenius/practices/identity-and-root.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^ir-guide]: AWS Security Incident Response Guide
[^contacts]: Update the alternate contacts for your AWS account
