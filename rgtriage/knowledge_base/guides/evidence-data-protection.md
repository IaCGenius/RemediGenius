---
type: Guide
title: "Evidence: data protection"
description: Whether data stores are public, shared or unencrypted - bucket and account public access blocks, policies, ACLs, snapshots and keys.
tags: [remedigenius, evidence, s3, kms, data]
sources:
  - {id: bpa, resource: "https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html", title: Blocking public access to your Amazon S3 storage, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

Question shapes: "is this bucket public?", "who can read it?", "is it encrypted?", "is this snapshot shared?".

## Reads that decide it
1. S3 public access: `s3control get_public_access_block AccountId=<id>` (account level) and
   `s3 get_public_access_block Bucket=<name>` (bucket level); either can block[^bpa]. Then
   `s3 get_bucket_policy_status` (`IsPublic`), `s3 get_bucket_policy` and `s3 get_bucket_acl`.
2. Cross-account sharing: principals and conditions in the bucket or key policy (`kms get_key_policy`); Access
   Analyzer findings for the resource.
3. Encryption: `s3 get_bucket_encryption`, `rds describe_db_instances` (`StorageEncrypted`, `KmsKeyId`),
   `ec2 describe_snapshots` / `rds describe_db_snapshot_attributes` for public or shared snapshots.

## Limits to say out loud
- The desk never reads object contents, secrets or decrypted data. Whether a bucket holds sensitive data comes from
  Macie findings (in Security Hub when enabled), tags or the organization's Application concepts, not from looking.
- `NoSuchBucketPolicy` or `NoSuchPublicAccessBlockConfiguration` errors are evidence (none configured), not failures.

## Stop when
Each layer that can make the resource public or shared has been read, or is named as unread.

Related: [data protection](/remedigenius/practices/data-protection.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^bpa]: Blocking public access to your Amazon S3 storage
