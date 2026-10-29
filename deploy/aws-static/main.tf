# RemediGenius-CE durable infrastructure: the S3 bucket, the Glue database and the two IAM roles.
#
# This root module is provisioned once and then left alone. It has no compute: the Spot instance comes and goes
# (deploy/aws-single for a community install, deploy/aws-private for the maintainer's own stack) and only reads the
# outputs below through terraform_remote_state.
#
# State lives in the bucket created by deploy/bootstrap:
#   terraform init -backend-config=../backend.hcl
#   terraform apply -var account_id=<id> -var subnet_id=... (subnet not needed here; kept for SG parity in compute)

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }
  backend "s3" {
    key = "aws-static/terraform.tfstate"
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
  type = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type        = string
  default     = "remedigenius-ce"
  description = "Installation name. Also the Glue database name, so it must stay stable across compute replacements."
}

variable "model_secret_arn" {
  type        = string
  default     = ""
  description = "Existing Secrets Manager secret holding only the model API key. KMS decrypt is granted automatically."
}

variable "member_role_name" {
  type        = string
  default     = "RemediGeniusReadOnly"
  description = "Read-only role in member accounts (member-read-role.yaml as a StackSet)."
}

variable "member_role_arns" {
  type        = list(string)
  default     = []
  description = "Accounts outside an AWS Organization: explicit read-role ARNs the instance role may assume."
}

variable "raw_retention_days" {
  type        = number
  default     = 90
  description = "Expire raw/ AWS response objects after this many days (0 keeps them). Facts in Iceberg do not expire."
  validation {
    condition     = var.raw_retention_days >= 0 && floor(var.raw_retention_days) == var.raw_retention_days
    error_message = "Choose a whole number of days (0 keeps raw evidence)."
  }
}

variable "allow_destroy" {
  type        = bool
  default     = false
  description = "Only for a throwaway stack: lets terraform destroy delete a non-empty bucket."
}

# Durable state: checkpoints (state/), raw evidence (raw/), the Iceberg warehouse (warehouse/) and release archives.
resource "aws_s3_bucket" "data" {
  bucket_prefix = "${var.name}-"
  force_destroy = var.allow_destroy
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.data.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    id     = "expire-old-checkpoint-versions"
    status = "Enabled"
    filter {
      prefix = "state/"
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
  dynamic "rule" {
    for_each = var.raw_retention_days > 0 ? [1] : []
    content {
      id     = "expire-old-raw-evidence"
      status = "Enabled"
      filter {
        prefix = "raw/"
      }
      expiration {
        days = var.raw_retention_days
      }
      noncurrent_version_expiration {
        noncurrent_days = 30
      }
    }
  }
}

resource "aws_glue_catalog_database" "ce" {
  name        = var.name
  description = "RemediGenius-CE Iceberg facts (findings, scans, coverage, decisions, operations)"
}

# Instance role: SSM, its own bucket, the model secret, and assuming the read-only roles.
# AWS security reads go through the audit role (and member read roles), never the instance role.
resource "aws_iam_role" "host" {
  name               = var.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_instance_profile" "host" {
  name = var.name
  role = aws_iam_role.host.name
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The model secret may be encrypted with a customer-managed KMS key; grant decrypt for exactly that key.
data "aws_secretsmanager_secret" "model" {
  count = var.model_secret_arn == "" ? 0 : 1
  arn   = var.model_secret_arn
}

data "aws_kms_key" "model" {
  count  = var.model_secret_arn != "" && try(data.aws_secretsmanager_secret.model[0].kms_key_id, "") != "" ? 1 : 0
  key_id = data.aws_secretsmanager_secret.model[0].kms_key_id
}

locals {
  model_kms_key_arns = [for k in data.aws_kms_key.model : k.arn if k.key_manager == "CUSTOMER"]
}

resource "aws_iam_role_policy" "host" {
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = "sts:AssumeRole", Resource = concat([aws_iam_role.audit.arn], var.member_role_arns) },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.data.arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.data.arn}/state/*" },
    # Release archives are read at boot; the desk never writes them.
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${aws_s3_bucket.data.arn}/source/*", "${aws_s3_bucket.data.arn}/bake/*"] },
    # Raw evidence and the Iceberg warehouse are written by the desk, never by the agent.
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    Resource = ["${aws_s3_bucket.data.arn}/raw/*", "${aws_s3_bucket.data.arn}/warehouse/*"] },
    # Glue catalog for Iceberg: only this installation's database and its tables.
    { Effect = "Allow",
      Action = ["glue:GetDatabase", "glue:GetTables", "glue:GetTable", "glue:CreateTable", "glue:UpdateTable",
        "glue:DeleteTable", "glue:GetPartitions", "glue:GetPartition", "glue:BatchCreatePartition",
      "glue:BatchUpdatePartition", "glue:BatchDeletePartition"],
      Resource = [aws_glue_catalog_database.ce.arn,
        "arn:aws:glue:${var.region}:${var.account_id}:table/${var.name}/*",
    "arn:aws:glue:${var.region}:${var.account_id}:catalog"] },
    # The Glue database is Terraform's; the desk may read it and manage only its own tables. These explicit denies
    # keep a future broad policy from turning the instance into a catalog/ETL administrator.
    { Effect = "Deny",
      Action = ["glue:CreateDatabase", "glue:DeleteDatabase", "glue:CreateCrawler", "glue:StartCrawler",
        "glue:CreateJob", "glue:StartJobRun", "glue:CreateDevEndpoint", "glue:CreateSecurityConfiguration",
      "glue:PutResourcePolicy", "glue:DeleteResourcePolicy"],
    Resource = "*" },
    {
      # The common read role in any account of this account's own organization (none when not in an organization).
      Effect    = "Allow", Action = "sts:AssumeRole", Resource = "arn:aws:iam::*:role/${var.member_role_name}",
      Condition = { StringEquals = { "aws:ResourceOrgID" = "$${aws:PrincipalOrgID}" } }
    }],
    var.model_secret_arn == "" ? [] : [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.model_secret_arn }],
    length(local.model_kms_key_arns) == 0 ? [] : [{ Effect = "Allow", Action = "kms:Decrypt", Resource = local.model_kms_key_arns, Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com" } } }]
  ) })
}

# Read-only audit role used by the desk for every AWS security read in this account.
resource "aws_iam_role" "audit" {
  name = "${var.name}-audit"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { AWS = aws_iam_role.host.arn }, Action = "sts:AssumeRole"
  }] })
}

resource "aws_iam_role_policy_attachment" "audit_read" {
  for_each   = toset(["SecurityAudit", "job-function/ViewOnlyAccess"])
  role       = aws_iam_role.audit.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}

# Policy evaluations: the IAM simulator and Access Analyzer policy checks return a verdict and change nothing.
resource "aws_iam_role_policy" "audit_evaluate" {
  role = aws_iam_role.audit.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid = "EvaluatePoliciesWithoutChanges", Effect = "Allow", Resource = "*",
    Action = ["iam:SimulatePrincipalPolicy", "iam:SimulateCustomPolicy", "iam:GetContextKeysForPrincipalPolicy",
      "iam:GetContextKeysForCustomPolicy", "access-analyzer:CheckNoPublicAccess", "access-analyzer:CheckAccessNotGranted",
    "access-analyzer:CheckNoNewAccess", "access-analyzer:ValidatePolicy"]
  }] })
}

resource "aws_iam_role_policy" "audit_exclusions" {
  role = aws_iam_role.audit.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid = "NoCredentialsOrApplicationData", Effect = "Deny", Resource = "*",
    Action = ["iam:GenerateCredentialReport", "iam:GenerateServiceLastAccessedDetails", "config:DeliverConfigSnapshot",
      "secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue",
      "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath",
      "ecr:GetAuthorizationToken", "sts:AssumeRole", "sts:GetSessionToken",
      "sts:GetFederationToken", "kms:Decrypt", "kms:GenerateDataKey*",
      "s3:GetObject", "s3:GetObjectVersion", "s3-object-lambda:GetObject",
      "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan",
    "rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"]
  }] })
}

output "bucket" {
  value = aws_s3_bucket.data.id
}

output "bucket_arn" {
  value = aws_s3_bucket.data.arn
}

output "glue_database" {
  value       = aws_glue_catalog_database.ce.name
  description = "Iceberg catalog database for the desk facts."
}

output "warehouse" {
  value = "s3://${aws_s3_bucket.data.id}/warehouse"
}

output "instance_role_arn" {
  value = aws_iam_role.host.arn
}

output "instance_profile_name" {
  value = aws_iam_instance_profile.host.name
}

output "audit_role_arn" {
  value = aws_iam_role.audit.arn
}