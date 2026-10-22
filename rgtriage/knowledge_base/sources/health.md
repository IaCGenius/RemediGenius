---
type: Source Guide
title: AWS Health events
description: Open and upcoming AWS Health issues, account notifications and scheduled changes.
tags:
- health
- operations
sources:
- id: aws
  resource: https://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html
  title: What is AWS Health?
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Service issues, security notifications (for example exposed keys reported by AWS) and scheduled changes such as retirements.[^aws]

# How the desk reads it

Open and upcoming events from the Health API (us-east-1 endpoint).

# How it is scored

Health category; security notifications stay visible next to findings.

# Blind spots

The Health API needs a Business, Enterprise On-Ramp or Enterprise support plan; Health events still reach Security Hub.

# Investigate next

Read the event description and affected entities; map affected resources to applications with knowledge concepts.

Related: [generic](/remedigenius/playbooks/generic.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: What is AWS Health?
