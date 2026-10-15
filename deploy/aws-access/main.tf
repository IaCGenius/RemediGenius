terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
}
variable "account_id" { type = string }
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "trusted_principal_arn" { type = string }
variable "external_id" {
  type      = string
  sensitive = true
}
variable "log_group_arns" {
  type    = list(string)
  default = []
}
variable "object_arns" {
  type    = list(string)
  default = []
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
}
module "access" {
  source                = "../../modules/aws-read-access"
  trusted_principal_arn = var.trusted_principal_arn
  external_id           = var.external_id
  regions               = [var.region]
  log_group_arns        = var.log_group_arns
  object_arns           = var.object_arns
}
output "role_arn" { value = module.access.role_arn }
