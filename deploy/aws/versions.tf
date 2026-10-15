/**
 * RemediGenius Community on AWS: everything in your own account, one root module.
 *
 *   network.tf   one small VPC, no inbound rules (you connect through SSM)
 *   storage.tf   KMS key, bucket (boot code + results), model-key secret, data volume + daily snapshots
 *   engine.tf    one spot instance running the agents (Docker), its role, boot code and profiles
 *   accounts.tf  the read-only role in this account + secrets for every account you connect
 *   kiosk.tf     optional: the lambda kiosk and the builder agent (enable_kiosk)
 *
 * State is local by default. For a team, add an S3 backend (docs/OPERATE.md).
 */
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.80" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = "remedigenius-community", ManagedBy = "terraform" } }
}

data "aws_availability_zones" "up" {
  state = "available"
}

locals {
  name   = "${var.name_prefix}-hermes"
  bucket = "${var.name_prefix}-hermes-${var.account_id}-${var.region}"
  az     = var.az != "" ? var.az : data.aws_availability_zones.up.names[0]
  root   = "${path.module}/../.."
}
