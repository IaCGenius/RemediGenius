# S3 data protection (S3.5 SSL-only, S3.9 access logging, S3.14 versioning, S3.17 KMS, S3.15 object lock)

**Means:** the bucket allows plaintext HTTP requests, has no access logs, cannot recover
overwritten/deleted objects, or uses SSE-S3 where policy requires a customer KMS key.

**Verify:** `rgtriage aws s3 get_bucket_policy --params '{"Bucket":"<b>"}'` (also `get_bucket_versioning`,
`get_bucket_logging`, `get_bucket_encryption`).

**Terraform:**
```hcl
# S3.5 deny non-TLS. A bucket has ONE policy: merge into the existing aws_s3_bucket_policy
# (source_policy_documents) instead of adding a second policy resource that would overwrite it.
data "aws_iam_policy_document" "<name>_tls" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [aws_s3_bucket.<name>.arn, "${aws_s3_bucket.<name>.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# S3.14 versioning
resource "aws_s3_bucket_versioning" "<name>" {
  bucket = aws_s3_bucket.<name>.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3.9 server access logging
resource "aws_s3_bucket_logging" "<name>" {
  bucket        = aws_s3_bucket.<name>.id
  target_bucket = aws_s3_bucket.<log_bucket>.id
  target_prefix = "s3/<name>/"
}

# S3.17 SSE-KMS
resource "aws_s3_bucket_server_side_encryption_configuration" "<name>" {
  bucket = aws_s3_bucket.<name>.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.<key>.arn
    }
    bucket_key_enabled = true
  }
}
```

**CloudFormation:** `VersioningConfiguration: {Status: Enabled}`, `LoggingConfiguration`,
`BucketEncryption.ServerSideEncryptionConfiguration`, and an `AWS::S3::BucketPolicy` Deny with
condition `Bool: {aws:SecureTransport: false}`.

**Trade-offs:** versioning increases storage cost (add lifecycle `noncurrent_version_expiration`);
KMS adds request cost and key-policy dependencies for every reader; the log bucket must not log to itself.
