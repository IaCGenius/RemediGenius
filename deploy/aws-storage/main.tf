terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
}
variable "account_id" { type = string }
variable "region" { type = string }
variable "bucket_name" { type = string }
variable "workspace_prefix" {
  type    = string
  default = "community"
}
variable "trusted_principal_arn" { type = string }
variable "external_id" {
  type      = string
  sensitive = true
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
}
resource "aws_s3_bucket" "workspace" {
  bucket        = var.bucket_name
  force_destroy = false
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_public_access_block" "workspace" {
  bucket                  = aws_s3_bucket.workspace.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "workspace" {
  bucket = aws_s3_bucket.workspace.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "workspace" {
  bucket = aws_s3_bucket.workspace.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.workspace.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.workspace.arn, "${aws_s3_bucket.workspace.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
module "access" {
  source                = "../../modules/workspace-storage"
  bucket_name           = aws_s3_bucket.workspace.id
  prefix                = var.workspace_prefix
  trusted_principal_arn = var.trusted_principal_arn
  external_id           = var.external_id
  role_name             = "RemediGeniusCommunityStorage"
}
output "bucket" { value = aws_s3_bucket.workspace.id }
output "prefix" { value = var.workspace_prefix }
output "role_arn" { value = module.access.role_arn }
