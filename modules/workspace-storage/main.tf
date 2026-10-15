variable "bucket_name" { type = string }
variable "prefix" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.prefix))
    error_message = "Use a workspace prefix without leading/trailing slash."
  }
}
variable "trusted_principal_arn" { type = string }
variable "external_id" {
  type      = string
  sensitive = true
}
variable "role_name" { type = string }
data "aws_partition" "current" {}
locals { bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}" }
resource "aws_iam_role" "storage" {
  name               = var.role_name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { AWS = var.trusted_principal_arn }, Action = "sts:AssumeRole", Condition = { StringEquals = { "sts:ExternalId" = var.external_id } } }] })
}
resource "aws_iam_role_policy" "storage" {
  role = aws_iam_role.storage.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:ListBucket", Resource = local.bucket_arn, Condition = { StringLike = { "s3:prefix" = "${var.prefix}/*" } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = "${local.bucket_arn}/${var.prefix}/*" },
    { Effect = "Allow", Action = "s3:PutObject", Resource = "${local.bucket_arn}/${var.prefix}/*", Condition = { StringEquals = { "s3:if-none-match" = "*" } } }
  ] })
}
output "role_arn" { value = aws_iam_role.storage.arn }
