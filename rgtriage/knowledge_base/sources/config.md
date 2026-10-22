---
type: Source Guide
title: AWS Config rule results
description: Non-compliant AWS Config rules and conformance packs.
tags:
- config
- posture
- compliance
sources:
- id: aws
  resource: https://docs.aws.amazon.com/config/latest/developerguide/evaluate-config.html
  title: Evaluating resources with AWS Config rules
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Resources that fail your own Config rules or conformance packs, and (separately) configuration history for investigations.[^aws]

# How the desk reads it

NON_COMPLIANT evaluations per rule, up to the per-source limit.

# How it is scored

MEDIUM posture findings by default; the rule annotation becomes the description. Business criticality and goals move them.

# Blind spots

Only regions with a recorder and only the rules you deploy. Security Hub controls already cover many managed rules.

# Investigate next

`config get_resource_config_history` shows what changed and when.

Related: [detection baseline](/remedigenius/playbooks/detection-baseline.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: Evaluating resources with AWS Config rules
