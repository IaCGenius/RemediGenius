# S3 public access (S3.1, S3.2, S3.3, S3.8, S3.19, Access Analyzer public S3)

**Means:** a bucket (or the account) does not block public access, or a bucket policy/ACL
grants read or write to everyone. Public write is an incident; public read is a data leak
unless the bucket is an intentional public website/asset bucket.

**Verify (read-only):**
- `rgtriage aws s3control get_public_access_block --params '{"AccountId":"<acct>"}'`
- `rgtriage aws s3 get_public_access_block --params '{"Bucket":"<bucket>"}'`
- `rgtriage aws s3 get_bucket_policy_status --params '{"Bucket":"<bucket>"}'`
- `rgtriage aws s3 get_bucket_policy --params '{"Bucket":"<bucket>"}'` and `get_bucket_acl`
- Ask: is this a deliberate public asset/website bucket? If yes, prefer CloudFront + OAC.

**Terraform fix (bucket-level):**
```hcl
resource "aws_s3_bucket_public_access_block" "<name>" {
  bucket                  = aws_s3_bucket.<name>.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```
**Account-level (S3.1):**
```hcl
resource "aws_s3_account_public_access_block" "this" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```
Also remove `"Principal": "*"` statements without restrictive conditions from `aws_s3_bucket_policy`,
and add `aws_s3_bucket_ownership_controls` with `object_ownership = "BucketOwnerEnforced"` to disable ACLs.

**CloudFormation:** on `AWS::S3::Bucket` add
```yaml
PublicAccessBlockConfiguration:
  BlockPublicAcls: true
  BlockPublicPolicy: true
  IgnorePublicAcls: true
  RestrictPublicBuckets: true
OwnershipControls:
  Rules: [{ObjectOwnership: BucketOwnerEnforced}]
```
**CLI (operator runs):** `aws s3api put-public-access-block --bucket <b> --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true`

**Trade-offs / blast radius:** breaks anonymous consumers (static sites, public downloads,
third parties using ACL grants). Check CloudFront origins and bucket policy principals first.
**Verify after:** rescan; the control should move to PASSED after Security Hub re-evaluates (change-triggered, up to ~24h for periodic checks).
