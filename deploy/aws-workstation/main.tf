terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.80" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
}
variable "account_id" { type = string }
variable "region" { type = string }
variable "operator_arn" {
  type        = string
  description = "Exact IAM role/user ARN of the workstation operator, not an STS session ARN."
  validation {
    condition     = can(regex("^arn:[a-z-]+:iam::[0-9]{12}:(user|role)/[^*?]+$", var.operator_arn))
    error_message = "Use an exact IAM user or role ARN, not an STS session or wildcard."
  }
}
variable "name" {
  type    = string
  default = "rgce-workstation"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.name))
    error_message = "Use a unique lowercase stack name, at most 31 characters."
  }
}
variable "schedule_enabled" { default = true }
variable "schedule_interval_hours" {
  default = 24
  validation {
    condition     = var.schedule_interval_hours >= 1 && var.schedule_interval_hours <= 168 && floor(var.schedule_interval_hours) == var.schedule_interval_hours
    error_message = "Use 1 to 168 whole hours."
  }
}
variable "targets" {
  type    = map(object({ account_id = string, regions = list(string), role_arn = optional(string, ""), external_id = optional(string, "") }))
  default = {}
  validation {
    condition     = alltrue([for target in values(var.targets) : length(target.regions) > 0])
    error_message = "Every configured target needs at least one explicit region."
  }
}
variable "schedule_checks" {
  description = "Optional one to four explicit collector requests. Default checks use the first configured target/region only."
  type        = any
  default     = null
  validation {
    condition     = var.schedule_checks == null ? true : (length(var.schedule_checks) >= 1 && length(var.schedule_checks) <= 4)
    error_message = "Choose one to four scheduled checks; interactive targets remain independently configurable."
  }
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = { Project = "remedigenius-ce", Stack = var.name, ManagedBy = "terraform", CEVersion = "0.1.3" }
  }
}
data "aws_partition" "current" {}
locals {
  prefix          = "ce/evidence"
  schedule_target = length(var.targets) > 0 ? sort(keys(var.targets))[0] : "default"
  schedule_region = length(var.targets) > 0 ? var.targets[local.schedule_target].regions[0] : var.region
}
resource "aws_s3_bucket" "evidence" {
  bucket        = "${var.name}-${var.account_id}-${var.region}"
  force_destroy = var.delete_evidence_on_destroy
}
resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "transport" {
  bucket = aws_s3_bucket.evidence.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.evidence.arn, "${aws_s3_bucket.evidence.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
module "reader" {
  source           = "../../modules/aws-read-executor"
  name             = var.name
  bucket_name      = aws_s3_bucket.evidence.id
  workspace_prefix = local.prefix
  region           = var.region
  account_id       = var.account_id
  targets          = length(var.targets) > 0 ? var.targets : { default = { account_id = var.account_id, regions = [var.region], role_arn = "", external_id = "" } }
}
module "assurance" {
  source         = "../../modules/assurance-schedule"
  name           = var.name
  bucket         = aws_s3_bucket.evidence.id
  prefix         = local.prefix
  reader_arn     = module.reader.function_arn
  enabled        = var.schedule_enabled
  interval_hours = var.schedule_interval_hours
  checks_json = var.schedule_checks != null ? jsonencode(var.schedule_checks) : jsonencode([
    { target = local.schedule_target, region = local.schedule_region, service = "securityhub", operation = "get_findings", parameters = { Filters = { RecordState = [{ Value = "ACTIVE", Comparison = "EQUALS" }] } }, max_pages = 2 },
    { target = local.schedule_target, region = local.schedule_region, service = "config", operation = "describe_configuration_recorders", parameters = {}, max_pages = 1 }
  ])
}
output "workstation_backend" {
  value = { region = var.region, bucket = aws_s3_bucket.evidence.id, prefix = local.prefix, reader_function = module.reader.function_arn, reader_role_arn = aws_iam_role.invoker.arn }
}

variable "delete_evidence_on_destroy" {
  type        = bool
  default     = false
  description = "Destructive opt-in: remove all evidence objects and versions on destroy. Apply true before destroy only after backing up wanted data."
}
