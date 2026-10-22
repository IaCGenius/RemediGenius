---
type: Source Guide
title: AWS Security Hub CSPM findings
description: Posture checks (FSBP, CIS) and findings that other services forward to Security Hub.
tags:
- securityhub
- posture
- cspm
sources:
- id: aws
  resource: https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-controls-reference.html
  title: Security Hub controls reference
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Failed configuration controls (for example S3.8, EC2.19, IAM.6) from the enabled standards, plus findings forwarded by GuardDuty, Inspector, Access Analyzer and partners.[^aws]

# How the desk reads it

Active findings with workflow status NEW or NOTIFIED, per severity, up to the detail limits in triage.yaml. Findings the desk also reads natively are de-duplicated by their native id.

# How it is scored

Starts from the control severity. Public exposure, identity risk and detection gaps (CloudTrail, Config, GuardDuty off) add points. The same control across standards and resources becomes one issue.

# Blind spots

Only checks for enabled standards and regions; a control can lag a fix by up to 24 hours (periodic checks); suppressed findings are not read.

# Investigate next

Verify the current state with the service's describe/get call before proposing a fix; `rg_triage action=fix` gives the IaC location and playbook.

Related: [s3 public access](/remedigenius/playbooks/s3-public-access.md) · [security group ingress](/remedigenius/playbooks/security-group-ingress.md) · [iam identities](/remedigenius/playbooks/iam-identities.md) · [detection baseline](/remedigenius/playbooks/detection-baseline.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: Security Hub controls reference
