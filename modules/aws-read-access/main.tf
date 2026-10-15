terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
}

variable "trusted_principal_arn" { type = string }
variable "external_id" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.external_id) >= 16
    error_message = "Use a unique external ID of at least 16 characters."
  }
}
variable "additional_principal_arns" {
  type    = list(string)
  default = []
}
variable "regions" { type = list(string) }
variable "log_group_arns" {
  type    = list(string)
  default = []
}
variable "object_arns" {
  type    = list(string)
  default = []
}

locals {
  read_policy = {
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = ["ec2:DescribeSecurityGroups", "ec2:DescribeNetworkInterfaces", "securityhub:GetFindings", "cloudtrail:LookupEvents"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.regions } } }
      ], length(var.log_group_arns) == 0 ? [] : [
      { Effect = "Allow", Action = ["logs:FilterLogEvents"], Resource = var.log_group_arns, Condition = { StringEquals = { "aws:RequestedRegion" = var.regions } } }
      ], length(var.object_arns) == 0 ? [] : [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = var.object_arns, Condition = { StringEquals = { "aws:RequestedRegion" = var.regions } } }
    ])
  }
}

resource "aws_iam_role" "read" {
  name = "RemediGeniusCommunityReadOnly"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { AWS = concat([var.trusted_principal_arn], var.additional_principal_arns) }, Action = "sts:AssumeRole", Condition = { StringEquals = { "sts:ExternalId" = var.external_id } } }]
  })
  tags = { Project = "remedigenius-community", Purpose = "operator-initiated-read" }
}
resource "aws_iam_role_policy" "read" {
  name   = "SelectedCommunitySources"
  role   = aws_iam_role.read.id
  policy = jsonencode(local.read_policy)
}
output "role_arn" { value = aws_iam_role.read.arn }
output "policy" { value = local.read_policy }
