---
type: Security Practice
title: Logging and detection
description: Record every API call, keep the record tamper-evident, and run detectors in every region so an attack is seen.
tags: [cloudtrail, config, guardduty, securityhub, monitoring, cis, fsbp]
sources:
  - {id: ct-bp, resource: "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/best-practices-security.html", title: Security best practices in CloudTrail, author: aws-documentation}
  - {id: cw-controls, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/cloudwatch-controls.html", title: Security Hub controls for CloudWatch, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  controls: [CloudTrail.1, CloudTrail.2, CloudTrail.3, CloudTrail.4, CloudTrail.5, CloudTrail.6, CloudTrail.7, Config.1,
             GuardDuty.1, SecurityHub.1, EC2.6, KMS.4, S3.22, S3.23, CloudWatch.1, CloudWatch.2, CloudWatch.3, CloudWatch.4,
             CloudWatch.5, CloudWatch.6, CloudWatch.7, CloudWatch.8, CloudWatch.9, CloudWatch.10, CloudWatch.11,
             CloudWatch.12, CloudWatch.13, CloudWatch.14, Inspector.1, Inspector.2, Inspector.3, Inspector.4]
---

# Goal

A multi-region CloudTrail with log file validation and encryption; AWS Config recording in every region you use;
GuardDuty, Security Hub and Inspector enabled everywhere (or through a delegated administrator); alarms on the API
calls that matter.[^ct-bp]

# Why it matters

Every other finding depends on these. Without CloudTrail there is no "who did it"; without Config no "what changed";
without GuardDuty no threat detection at all. Attackers disable logging early, and an empty board in an account
without detectors means nothing.

# What checks it

| Control | Checks | Desk default |
|---|---|---|
| CloudTrail.1 / CloudTrail.4 / CloudTrail.2 | multi-region trail with management events; log file validation; KMS encryption | P2 (detection gap +8) |
| CloudTrail.7 / S3.22 / S3.23 | access logging on the trail bucket; S3 object-level logging | P3 |
| Config.1 | Config recording | P2; also blocks change history for investigations |
| GuardDuty.1 / SecurityHub.1 / Inspector.1–4 | the detectors themselves are enabled | P2 |
| EC2.6 | VPC flow logs | P3 |
| KMS.4 | rotation of customer-managed keys | P3 |
| CloudWatch.1–14 | metric filters and alarms for root use, IAM, CloudTrail, network and console changes | one P3 issue for all 14 |

The desk also reports blind spots itself: a source that is `not_enabled` or `denied` in a region is listed under
Coverage gaps on the board, never treated as clean.

# Investigate and fix

- [Detection baseline](/remedigenius/playbooks/detection-baseline.md) and [CIS metric filters](/remedigenius/playbooks/cis-metric-filters.md)
  playbooks (the metric filters are one Terraform or CloudFormation change).[^cw-controls]
- Organization-wide: an organization trail, Config aggregator and delegated administrators for GuardDuty, Security Hub
  and Inspector (see the multi-account guide in the docs).

# Build on it

- **Account** concepts: say which accounts are production, so a missing trail there outranks one in a sandbox.
- **Policy**: retention you require (for example "CloudTrail logs kept 400 days in the log archive account").
- **Runbook**: who receives the CloudWatch alarms and what they do first.
- **Risk Exception** for regions you deliberately leave unmonitored because they are blocked by an SCP, with an expiry.

Related: [Config rule results](/remedigenius/sources/config.md) · [CloudWatch alarms](/remedigenius/sources/cloudwatch.md) · [Security Hub findings](/remedigenius/sources/securityhub.md) · [CIS AWS Foundations Benchmark](/remedigenius/frameworks/cis-aws-foundations.md)

[^ct-bp]: Security best practices in CloudTrail
[^cw-controls]: Security Hub controls for CloudWatch
