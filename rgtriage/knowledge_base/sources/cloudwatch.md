---
type: Source Guide
title: CloudWatch alarms in ALARM
description: Alarms currently firing; security-related alarms count as threats.
tags:
- cloudwatch
- alarm
- detection
sources:
- id: aws
  resource: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html
  title: Using Amazon CloudWatch alarms
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Metric alarms in ALARM state, including CIS metric-filter alarms for root use, IAM, CloudTrail, security group and network changes.[^aws]

# How the desk reads it

Alarms with state ALARM. Names containing words such as root, unauthorized, iam, cloudtrail, securitygroup, kms or console count as security alarms.

# How it is scored

Security alarms are HIGH threats; other alarms are MEDIUM operational items.

# Blind spots

Only alarms that exist; a missing alarm is reported by the CIS controls instead.

# Investigate next

`cloudwatch describe_alarm_history` shows when it fired; for metric-filter alarms, look up the matching CloudTrail events.

Related: [cis metric filters](/remedigenius/playbooks/cis-metric-filters.md) · [threat response](/remedigenius/playbooks/threat-response.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: Using Amazon CloudWatch alarms
