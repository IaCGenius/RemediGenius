# S3 deterministic checklist

For each bucket in the receipt, record the exact values:

- BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets
- ServerSideEncryptionConfiguration (SSEAlgorithm, BucketKeyEnabled)
- Versioning Status
- Logging TargetBucket and TargetPrefix (or absent)
- Policy statements that allow Principal: "*" or Action: "s3:*"

A missing GetPublicAccessBlock response is “not observed”, not “disabled”.
