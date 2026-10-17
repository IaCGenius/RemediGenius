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
  inventory_operations = jsondecode(file("${path.module}/../aws-read-executor/operations.json"))
  read_policy = {
    Version = "2012-10-17"
    Statement = concat([
      { Effect = "Allow", Action = distinct(flatten([for methods in values(local.inventory_operations) : values(methods)])), Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.regions } } }
      ], length(var.log_group_arns) == 0 ? [] : [
      { Effect = "Allow", Action = ["logs:FilterLogEvents"], Resource = var.log_group_arns, Condition = { StringEquals = { "aws:RequestedRegion" = var.regions } } }
      ], length(var.object_arns) == 0 ? [] : [
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = var.object_arns, Condition = { StringEquals = { "aws:RequestedRegion" = var.regions } } }
    ])
  }
}

output "role_arn" { value = aws_iam_role.read.arn }
output "policy" { value = local.read_policy }
