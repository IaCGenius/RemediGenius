# Everything that holds state: KMS key, bucket (boot code + results), model-key secret, the agents' data
# volume and its daily snapshots. `running = false` stops compute and keeps all of this.

resource "aws_kms_key" "main" {
  description             = "${local.name}: results bucket, secrets, data volume"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.main.key_id
}

# ---------------------------------------------------------------- bucket: boot code + results
resource "aws_s3_bucket" "main" {
  bucket        = local.bucket
  force_destroy = var.destroy_data_on_teardown
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket                  = aws_s3_bucket.main.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "main" {
  bucket = aws_s3_bucket.main.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.main.arn, "${aws_s3_bucket.main.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.main]
}

resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.main.id
  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 30 }
    abort_incomplete_multipart_upload { days_after_initiation = 2 }
  }
}

# ---------------------------------------------------------------- model key (you set the value; Terraform never reads it)
resource "aws_secretsmanager_secret" "model_key" {
  name                    = "${var.name_prefix}/hermes/model-api-key"
  description             = "API key for your OpenAI-compatible model provider. Set with the set_model_key output; Terraform never reads it."
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = var.secret_recovery_days
}

# ---------------------------------------------------------------- data volume (agent state) + daily snapshots
resource "aws_ebs_volume" "data" {
  availability_zone = local.az
  size              = var.data_volume_gb
  type              = "gp3"
  encrypted         = true
  kms_key_id        = aws_kms_key.main.arn
  tags              = { Name = "${local.name}-data", Snapshot = "${local.name}-daily" }
}

resource "aws_iam_role" "dlm" {
  name = "${local.name}-snapshots"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_iam_role_policy" "dlm_kms" {
  name = "snapshot-own-key"
  role = aws_iam_role.dlm.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      # Same set as the tested engine. kms:ReEncrypt* is reported (medium) by the IAM check on this role:
      # a known item to narrow once snapshots are verified without it.
      Action    = ["kms:CreateGrant", "kms:DescribeKey", "kms:Decrypt", "kms:GenerateDataKeyWithoutPlaintext", "kms:ReEncrypt*"]
      Resource  = [aws_kms_key.main.arn]
      Condition = { Bool = { "kms:GrantIsForAWSResource" = "true" } }
    }]
  })
}

resource "aws_dlm_lifecycle_policy" "data" {
  description        = "${local.name} data volume daily keep ${var.snapshot_keep}"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"
  policy_details {
    resource_types = ["VOLUME"]
    target_tags    = { Snapshot = "${local.name}-daily" }
    schedule {
      name = "daily"
      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["08:00"]
      }
      retain_rule { count = var.snapshot_keep }
      copy_tags = true
    }
  }
}
