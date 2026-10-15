# CIS AWS Foundations and FSBP mapping (local)

Static lookup. Match the exact Security Hub finding title, control ID, or resource type from the receipt.

| Observed signal (example) | CIS Benchmark | FSBP | Notes |
|---|---|---|---|
| S3 bucket public access block disabled | 2.1.5 | S3.1 | Cite bucket name and PublicAccessBlockConfiguration fields |
| IAM user with console access and no MFA | 1.2 | IAM.6 | Cite user and MFA device count |
| Security group allows 0.0.0.0/0 on port 22 | 5.2 | EC2.19 | Cite group ID and IpPermissions |
| CloudTrail not logging | 3.1 | CloudTrail.1 | Cite trail status and IsLogging |

Extend this table locally. Do not invent mappings.
