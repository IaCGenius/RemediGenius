# One-time bootstrap: the bucket that holds Terraform state for the other root modules.
#
# Applied once per account, by hand, with local state:
#   terraform -chdir=deploy/bootstrap init
#   terraform -chdir=deploy/bootstrap apply -var account_id=<id>
#   terraform -chdir=deploy/bootstrap state pull > /tmp/state.json   # keep a copy somewhere safe
#
# Then every other root module uses that bucket:
#   terraform -chdir=deploy/aws-static init -backend-config=../backend.hcl
#   cp deploy/backend.hcl.example deploy/backend.hcl  (git-ignored)
#
# Native S3 locking (use_lockfile) avoids a DynamoDB table. Terraform >= 1.10 is required for it.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = {
      Project = "remedigenius-ce", Stack = var.name, ManagedBy = "terraform"
    }
  }
}

variable "account_id" {
  type        = string
  description = "The account that owns the state bucket."
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type        = string
  default     = "remedigenius-ce-tfstate"
  description = "Prefix for the state bucket name (the bucket gets a random suffix)."
}

resource "aws_s3_bucket" "state" {
  bucket_prefix = "${var.name}-"
  force_destroy = false # a destroyed state bucket cannot be recovered by Terraform
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "state_tls" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

output "bucket" {
  value = aws_s3_bucket.state.id
}

output "backend_hcl" {
  description = "Write these values into deploy/backend.hcl (git-ignored)."
  value       = <<-EOT
    bucket       = "${aws_s3_bucket.state.id}"
    region       = "${var.region}"
    use_lockfile = true
    encrypt      = true
  EOT
}