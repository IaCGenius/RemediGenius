---
type: Security Practice
title: Data protection
description: Keep data private by default, encrypted at rest and in transit, and recoverable.
tags: [s3, encryption, kms, rds, backup, data, cis, fsbp]
sources:
  - {id: s3-bp, resource: "https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html", title: Security best practices for Amazon S3, author: aws-documentation}
  - {id: s3-controls, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/s3-controls.html", title: Security Hub controls for S3, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  controls: [S3.1, S3.2, S3.3, S3.5, S3.6, S3.8, S3.9, S3.12, S3.13, S3.14, S3.15, S3.17, S3.19, S3.20, EC2.3, EC2.7,
             RDS.1, RDS.2, RDS.3, RDS.4, RDS.5, RDS.11, EFS.1, KMS.3, Macie.1]
---

# Goal

S3 Block Public Access on at the account level and on every bucket; buckets reachable only over TLS; encryption at rest
everywhere (EBS default encryption, RDS, EFS, DynamoDB); backups and versioning for data you cannot lose; databases and
snapshots never public.[^s3-bp]

# Why it matters

A public bucket or database snapshot is the most common cloud data breach, and it needs no exploit. Encryption with
customer-managed keys adds a second, auditable permission check; versioning and backups turn ransomware or a bad
delete into an inconvenience.

# What checks it

| Control | Checks | Desk default |
|---|---|---|
| S3.1 / S3.8 / S3.2 / S3.3 / S3.19 | account and bucket Block Public Access; no public read or write | P1 when the bucket is actually public (public exposure +15) |
| S3.5 | bucket policy requires TLS | P3 |
| S3.14 / S3.15 / S3.20 | versioning, object lock, MFA delete | P3 |
| S3.9 / S3.17 | server access logging; KMS encryption | P3 |
| EC2.7 / EC2.3 / RDS.3 / EFS.1 | default EBS encryption; encrypted volumes, databases, file systems | P3 |
| RDS.1 / RDS.2 | no public snapshots; databases not publicly accessible | P1–P2 |
| RDS.5 / RDS.11 | multi-AZ; automated backups | P3–P4 |

Access Analyzer adds the evidence: who outside your organization can reach a bucket, key or queue, and whether that
access is public. A sensitive-data goal (Security Goal concept) raises all of these for the resource types you name.

# Investigate and fix

- [S3 public access](/remedigenius/playbooks/s3-public-access.md), [S3 data protection](/remedigenius/playbooks/s3-data-protection.md)
  and [RDS databases](/remedigenius/playbooks/rds-databases.md) playbooks.[^s3-controls]
- Evidence: `s3 get_public_access_block`, `s3 get_bucket_policy_status`, `s3 get_bucket_encryption`,
  `rds describe_db_snapshot_attributes`. The desk never reads object contents.

# Build on it

- **Application** concepts with `data` (for example "cardholder data", "customer PII") and the tags that mark the
  resources, so their findings become mission critical.
- **Security Goal** "Protect customer data" for `AwsS3Bucket`, `AwsRdsDbInstance`, `AwsDynamoDbTable`.
- **Risk Exception** for intentionally public buckets (static websites, public datasets): name the exact bucket.
- **Policy**: your encryption standard (which KMS keys, who administers them).

Related: [IAM Access Analyzer findings](/remedigenius/sources/accessanalyzer.md) · [CIS AWS Foundations Benchmark](/remedigenius/frameworks/cis-aws-foundations.md) · [AWS Foundational Security Best Practices](/remedigenius/frameworks/aws-foundational-security-best-practices.md)

[^s3-bp]: Security best practices for Amazon S3
[^s3-controls]: Security Hub controls for S3
