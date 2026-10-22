---
type: Framework
title: AWS Foundational Security Best Practices
description: AWS's own control set across services (FSBP); broader than CIS, and the main posture source the desk reads from Security Hub.
tags: [fsbp, aws, best-practices, compliance, baseline]
sources:
  - {id: fsbp, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html", title: AWS Foundational Security Best Practices standard, author: aws-documentation}
  - {id: controls, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-controls-reference.html", title: Security Hub controls reference, author: aws-documentation}
  - {id: wa, resource: "https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html", title: AWS Well-Architected Framework security pillar, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  standard: aws-foundational-security-best-practices
---

# What it is

FSBP is the control set AWS maintains in Security Hub for accounts and the services in them: hundreds of automated
checks such as `S3.8` (bucket blocks public access), `EC2.19` (no unrestricted high-risk ports), `Lambda.1` (no public
invoke) or `RDS.2` (no public database).[^fsbp] Where CIS covers the account foundation, FSBP also covers what you run.
Each control's page in the controls reference explains the check and how to fix it.[^controls]

The [Well-Architected security pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html) is
the design guidance behind both: identity, detection, infrastructure protection, data protection and incident
response.[^wa] The desk's practice concepts follow the same split.

# How it differs from CIS

| | CIS AWS Foundations | FSBP |
|---|---|---|
| Owner | Center for Internet Security, consensus | AWS |
| Scope | the account foundation | the foundation plus service configurations |
| Change | versioned releases | controls added continuously |
| Typical use | audits and external attestations | day-to-day posture |

Enable both if you report against CIS; the desk de-duplicates a control that fails under both into one issue.

# Practices

- [Identity and root](/remedigenius/practices/identity-and-root.md)
- [Logging and detection](/remedigenius/practices/logging-and-detection.md)
- [Data protection](/remedigenius/practices/data-protection.md)
- [Network exposure](/remedigenius/practices/network-exposure.md)
- [Vulnerability and patching](/remedigenius/practices/vulnerability-and-patching.md)
- [Incident readiness](/remedigenius/practices/incident-readiness.md)

Related: [CIS AWS Foundations Benchmark](/remedigenius/frameworks/cis-aws-foundations.md) · [Security Hub findings](/remedigenius/sources/securityhub.md)

[^fsbp]: AWS Foundational Security Best Practices standard
[^controls]: Security Hub controls reference
[^wa]: AWS Well-Architected Framework security pillar
