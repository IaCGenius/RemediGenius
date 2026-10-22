---
type: Source Guide
title: Amazon Inspector findings
description: Software vulnerabilities (CVEs) and network reachability for EC2, ECR images and Lambda.
tags:
- inspector
- vulnerability
- cve
sources:
- id: aws
  resource: https://docs.aws.amazon.com/inspector/latest/user/findings-understanding.html
  title: Understanding Amazon Inspector findings
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# What it tells you

Package and code vulnerabilities with CVSS, EPSS, exploit availability and fix versions; network paths that expose ports.[^aws]

# How the desk reads it

Totals and fix units from aggregation APIs (complete and cheap even at 40,000 findings), and full detail only for findings that can rank high. As delegated administrator the totals cover the organization.

# How it is scored

CVSS severity is scaled down (x0.75); exploit available (+12), EPSS of 0.1 or more (+5), reachability and internet exposure decide urgency. Findings are grouped by package or image so one upgrade clears many.

# Blind spots

Only scanned resources (SSM agent on EC2, enhanced scanning on ECR); unsupported OS or language packages are invisible.

# Investigate next

Fix in the image, AMI or dependency file and rebuild; never patch only a running instance.

Related: [vulnerabilities](/remedigenius/playbooks/vulnerabilities.md) · [security group ingress](/remedigenius/playbooks/security-group-ingress.md) · [ec2 hardening](/remedigenius/playbooks/ec2-hardening.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^aws]: Understanding Amazon Inspector findings
