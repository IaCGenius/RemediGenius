---
type: Framework
title: CIS AWS Foundations Benchmark
description: Consensus baseline for securing an AWS account; Security Hub checks most of it as controls, and the desk groups and ranks those findings.
tags: [cis, benchmark, compliance, baseline]
sources:
  - {id: cis, resource: "https://www.cisecurity.org/benchmark/amazon_web_services", title: CIS Amazon Web Services Benchmarks, author: org:center-for-internet-security}
  - {id: sh-cis, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/cis-aws-foundations-benchmark.html", title: CIS AWS Foundations Benchmark in Security Hub, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  standard: cis-aws-foundations-benchmark
---

# What it is

The Center for Internet Security (CIS) publishes the AWS Foundations Benchmark: a consensus set of configuration
recommendations for any AWS account, independent of what runs in it.[^cis] The full text is free to download from CIS;
this concept summarizes it in our words and maps it to what the desk sees.

AWS Security Hub implements the benchmark as a standard. Enable it per account and region (Security Hub supports
several benchmark versions; enable the newest your organization accepts), and each automated recommendation becomes a
Security Hub control with an id such as `IAM.6` or `CloudTrail.1`.[^sh-cis] The recommendation numbers (1.x, 3.x …)
differ between benchmark versions; the Security Hub control ids do not, which is why the desk works with them.

# The five areas, and where the desk explains them

| Benchmark area | What it protects | Typical Security Hub controls | Practice concept |
|---|---|---|---|
| Identity and access management | root user, MFA, keys, password policy, least privilege | IAM.1–IAM.6, IAM.9, IAM.15, IAM.16, IAM.18, IAM.22, IAM.26–IAM.28 | [Identity and root](/remedigenius/practices/identity-and-root.md) |
| Storage | S3 public access and TLS, EBS/RDS/EFS encryption | S3.1, S3.5, S3.8, S3.20, EC2.7, RDS.3, EFS.1 | [Data protection](/remedigenius/practices/data-protection.md) |
| Logging | CloudTrail everywhere and tamper-evident, Config, flow logs, key rotation | CloudTrail.1, CloudTrail.2, CloudTrail.4, CloudTrail.7, Config.1, EC2.6, KMS.4, S3.22, S3.23 | [Logging and detection](/remedigenius/practices/logging-and-detection.md) |
| Monitoring | metric filters and alarms for sensitive API activity | CloudWatch.1–CloudWatch.14 | [Logging and detection](/remedigenius/practices/logging-and-detection.md) |
| Networking | no internet access to admin ports, restrictive default security group, IMDSv2 | EC2.2, EC2.21, EC2.53, EC2.54, EC2.8 | [Network exposure](/remedigenius/practices/network-exposure.md) |

A few recommendations are manual (for example keeping contact details and security questions current); Security
Hub cannot check them, so they never appear as findings. The [incident readiness](/remedigenius/practices/incident-readiness.md)
practice lists them.

# How the desk treats CIS findings

- **Grouped by fix.** The 14 monitoring controls are one issue (one CloudFormation or Terraform change), and the same
  control failing under CIS and FSBP is one issue, not two.
- **Ranked by risk, not by benchmark order.** A failed control starts from its severity; public exposure, root use,
  identity risk and detection gaps move it. Root without hardware MFA and admin ports open to the internet usually
  rank P1; a missing metric filter alone is P3.
- **Detection gaps rank higher than their severity.** CloudTrail, Config and GuardDuty findings get extra points:
  without them you would not see an attack (see [detection baseline](/remedigenius/playbooks/detection-baseline.md)).

# Build on it

Add what the benchmark cannot know: a Policy concept for your stricter rules (for example "MFA delete on every bucket
holding audit logs"), Risk Exceptions for recommendations you accept with an expiry and an approver, and Account
concepts so production accounts outrank sandboxes. See [build on this knowledge](/remedigenius/guides/build-your-knowledge.md).

Related: [AWS Foundational Security Best Practices](/remedigenius/frameworks/aws-foundational-security-best-practices.md) ·
[Security Hub findings](/remedigenius/sources/securityhub.md) · [CIS metric filters](/remedigenius/playbooks/cis-metric-filters.md)

[^cis]: CIS Amazon Web Services Benchmarks
[^sh-cis]: CIS AWS Foundations Benchmark in Security Hub
