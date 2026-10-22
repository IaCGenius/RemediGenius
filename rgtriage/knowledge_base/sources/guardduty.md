---
type: Source Guide
title: Amazon GuardDuty findings
description: Threat detection from CloudTrail, VPC flow, DNS, S3 and runtime activity.
tags:
- guardduty
- threat
- detection
sources:
- id: aws
  resource: https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_finding-types-active.html
  title: GuardDuty active finding types
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Behavior that looks malicious or unusual: credential exfiltration, crypto mining, backdoors, root use, anomalous API activity, malware.[^aws]

# How the desk reads it

Active (not archived) findings per region, with the actor (principal, key, IP, ASN) and event count kept as context.

# How it is scored

Every GuardDuty finding is an active threat (+10); compromise, exfiltration or impact types add +20 instead; root credential use adds 15 to 40 by call count; no activity for 30 days lowers the score.

# Blind spots

Behavioral and probabilistic: anomaly findings also fire for a new legitimate tool or script. Only regions where GuardDuty is enabled. Protection plans (S3, runtime, malware) are enabled separately.

# Investigate next

Answer who, what, when and whether it was expected from CloudTrail before asking the user; record the user's answer as a decision.

Related: [threat response](/remedigenius/playbooks/threat-response.md) · [root account](/remedigenius/playbooks/root-account.md) · [iam identities](/remedigenius/playbooks/iam-identities.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: GuardDuty active finding types
