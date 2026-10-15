# S3 review checklist

For each bucket in the receipt, record the exact values:

- BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets
- ServerSideEncryptionConfiguration (SSEAlgorithm, BucketKeyEnabled)
- Versioning Status
- Logging TargetBucket and TargetPrefix (or absent)
- Policy statements that allow Principal: "*" or Action: "s3:*"

A missing GetPublicAccessBlock response is “not observed”, not “disabled”.

Public-access-block flags and wildcard policy text do not alone establish effective public access. Check policy conditions, denies, bucket/account blocks and relevant ACL/ownership semantics; report missing evidence. SSEAlgorithm=aws:kms does not alone prove a customer-managed key: identify the key and its ownership when exposed, otherwise mark that requirement unverified. Do not assume the operator requires CMK for every bucket.
