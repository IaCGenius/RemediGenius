---
name: ce-s3-deep-dive
description: Deep inspection of S3 bucket public access, encryption, versioning, and logging from collected evidence. Produce precise CLI or Terraform proposals.
license: Apache-2.0
---

# S3 public access and encryption deep-dive

Start from a receipt that contains S3 bucket configuration (GetPublicAccessBlock, GetBucketEncryption, GetBucketPolicy, GetBucketAcl, GetBucketVersioning, GetBucketLogging).

## Working procedure

1. **Frame** — Name the bucket and receipt ID.
2. **Inspect** — Extract exact PublicAccessBlockConfiguration, ServerSideEncryptionConfiguration, Policy, ACL, VersioningConfiguration, and LoggingConfiguration fields.
3. **Deterministic checks** — Apply the checklist in `references/s3-checklist.md`.
4. **Interpret** — State observed facts for each control. Cite fields.
5. **Propose** — At most three CLI or Terraform changes. Label AI-generated. Include verification commands that re-read the same APIs.
6. **Review** — Call `ce_review`.

## Limits

- Does not list object contents.
- Does not call external S3 scanners.
- Partial configuration is reported as incomplete evidence.

Read `references/s3-checklist.md`.
