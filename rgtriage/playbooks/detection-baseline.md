# Detection and audit baseline (Config.1, CloudTrail.1/2/4/5, GuardDuty.1, SecurityHub.1, Inspector.1)

**Means:** a region or account lacks the service that records or detects activity. These are
"you would not see an attack" gaps and make every other finding harder to investigate.

**Verify:** `rgtriage doctor`; `rgtriage aws config describe_configuration_recorder_status`;
`rgtriage aws cloudtrail describe_trails`; `rgtriage aws cloudtrail get_trail_status --params '{"Name":"<trail>"}'`.

**Terraform — AWS Config with the service-linked role (Config.1):**
```hcl
resource "aws_iam_service_linked_role" "config" {
  aws_service_name = "config.amazonaws.com"
}

resource "aws_config_configuration_recorder" "this" {
  name     = "default"
  role_arn = aws_iam_service_linked_role.config.arn
  recording_group {
    all_supported                 = true
    include_global_resource_types = true # in ONE region only, to avoid duplicate IAM items
  }
}

resource "aws_config_delivery_channel" "this" {
  name           = "default"
  s3_bucket_name = aws_s3_bucket.config_logs.id
  depends_on     = [aws_config_configuration_recorder.this]
}

resource "aws_config_configuration_recorder_status" "this" {
  name       = aws_config_configuration_recorder.this.name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.this]
}
```
If the service-linked role already exists, import it (`terraform import aws_iam_service_linked_role.config arn:aws:iam::<acct>:role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig`).
The delivery bucket policy must allow `config.amazonaws.com` `s3:GetBucketAcl`, `s3:ListBucket` and `s3:PutObject`.

**CloudTrail (CloudTrail.1/.2/.4/.5):**
```hcl
resource "aws_cloudtrail" "main" {
  name                          = "management-events"
  s3_bucket_name                = aws_s3_bucket.trail.id
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true                                      # CloudTrail.4
  kms_key_id                    = aws_kms_key.trail.arn                     # CloudTrail.2
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.trail.arn}:*" # CloudTrail.5
  cloud_watch_logs_role_arn     = aws_iam_role.trail_to_cwl.arn
}
```
**GuardDuty / Security Hub / Inspector:** `aws_guardduty_detector { enable = true }`, `aws_securityhub_account {}`,
`aws_inspector2_enabler { account_ids = [...] resource_types = ["EC2", "ECR", "LAMBDA"] }` in every used region.
In an AWS Organization enable them from the delegated administrator with auto-enable instead of per account.

**Trade-offs:** Config and GuardDuty bill per resource/event; you can limit Config recording to needed types.
