# Terraform hardening snippets (local)

Copy and adapt. Replace placeholders with values from the receipt.

## S3 Block Public Access
```hcl
resource "aws_s3_bucket_public_access_block" "example" {
  bucket = "<bucket-name-from-receipt>"
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

## EBS encryption default
```hcl
resource "aws_ebs_encryption_by_default" "example" {
  enabled = true
}
```

Extend with additional snippets as needed. Always cite the section used.

Before using a snippet, inspect supplied repository/module/provider version and resource ownership. Edit an existing managed resource rather than declaring a second owner; otherwise identify import/adoption steps as unvalidated proposals. EBS encryption-by-default affects new volumes in the configured region, not existing volume encryption. Never assert validation/plan/apply ran unless tool evidence proves it.
