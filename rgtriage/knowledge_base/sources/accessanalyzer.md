---
type: Source Guide
title: IAM Access Analyzer findings
description: Resources shared outside the account or organization, and unused access.
tags:
- accessanalyzer
- iam
- exposure
sources:
- id: aws
  resource: https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html
  title: Using IAM Access Analyzer
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Buckets, roles, keys, queues and other resources reachable from outside the zone of trust; unused roles, keys and permissions (unused-access analyzers).[^aws]

# How the desk reads it

Active findings from every active analyzer in the region; public access is classified separately from cross-account sharing.

# How it is scored

Public access is HIGH with public exposure; sharing with a named external account is MEDIUM; trust in an identity provider (for example SSO) is LOW because it is usually intended.

# Blind spots

Needs an active analyzer per region (account or organization zone of trust). Intended sharing keeps appearing until it is archived.

# Investigate next

Confirm the external principal with the owner; if the sharing is intended, record a decision or a Risk Exception concept.

Related: [s3 public access](/remedigenius/playbooks/s3-public-access.md) · [iam identities](/remedigenius/playbooks/iam-identities.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: Using IAM Access Analyzer
