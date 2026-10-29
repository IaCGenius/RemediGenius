# RemediGenius-CE compute only: the Spot instance that comes and goes.
#
# Everything durable (bucket, Glue database, IAM roles) lives in deploy/aws-static and is read through
# terraform_remote_state. This root module can therefore be applied and destroyed in a couple of minutes without
# touching the installation's data:
#
#   terraform init -backend-config=../backend.hcl
#   terraform apply  -var account_id=<id> -var subnet_id=... -var ami_id=... -var source_zip=...   # start
#   terraform apply  ... -var running=false                                                        # park, keep data
#   terraform destroy ...                                                                          # remove compute only
#
# tools/spot_cycle.py wraps up/down/status. The full from-nothing apply of deploy/aws-single stays the release gate.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }
  backend "s3" {
    key = "aws-private/terraform.tfstate"
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
  description = "Installation name. Must match the name used by deploy/aws-static."
}

variable "state_bucket" {
  type        = string
  description = "Terraform state bucket from deploy/bootstrap."
}

variable "static_key" {
  type        = string
  default     = "aws-static/terraform.tfstate"
  description = "Key of the deploy/aws-static state inside state_bucket."
}

variable "subnet_id" {
  type        = string
  description = "Existing subnet with outbound HTTPS (public with an internet gateway, or private with NAT)."
}

variable "ami_id" {
  type        = string
  description = "Baked image from deploy/ami (contains the pinned Hermes image and the host runtime)."
  validation {
    condition     = can(regex("^ami-[0-9a-f]{8,}$", var.ami_id))
    error_message = "Pass the ami_id output of deploy/ami; the baked image is what removes the boot-time install."
  }
}

variable "source_zip" {
  type        = string
  description = "Release package from tools/package_release.py. Must be the same release the image was baked from."
}

variable "running" {
  type        = bool
  default     = true
  description = "false parks the stack: the ASG scales to zero and no instance runs; data and IAM stay."
}

variable "model_secret_arn" {
  type    = string
  default = ""
}

variable "model_name" {
  type    = string
  default = "deepseek-v4.1-flash"
}

variable "model_base_url" {
  type    = string
  default = ""
}

variable "regions" {
  type    = list(string)
  default = []
}

variable "member_role_name" {
  type    = string
  default = "RemediGeniusReadOnly"
}

variable "member_account_ids" {
  type    = list(string)
  default = []
}

variable "member_role_arns" {
  type    = list(string)
  default = []
}

variable "scan_interval_hours" {
  type    = number
  default = 6
  validation {
    condition     = var.scan_interval_hours >= 1 && var.scan_interval_hours <= 168 && floor(var.scan_interval_hours) == var.scan_interval_hours
    error_message = "Choose a whole number of hours from 1 to 168."
  }
}

variable "watch_deliver" {
  type    = string
  default = "local"
}

variable "public_ip" {
  type    = bool
  default = true
}

variable "spot_instance_types" {
  type    = list(string)
  default = ["t3.large", "t3a.large"]
}

variable "container_memory_mb" {
  type    = number
  default = 6144
}

check "model_endpoint" {
  assert {
    condition     = var.model_secret_arn == "" || var.model_base_url != ""
    error_message = "Set model_base_url (OpenAI-compatible endpoint) when model_secret_arn is set."
  }
}

data "terraform_remote_state" "static" {
  backend = "s3"
  config = {
    bucket = var.state_bucket
    key    = var.static_key
    region = var.region
  }
}

data "aws_subnet" "selected" {
  id = var.subnet_id
}

resource "aws_security_group" "host" {
  name_prefix = "${var.name}-"
  vpc_id      = data.aws_subnet.selected.vpc_id
  description = "RemediGenius-CE: SSM only, no inbound rules"
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# The archive is versioned per release so a parked stack can be started again without rebuilding anything.
resource "aws_s3_object" "source" {
  bucket      = data.terraform_remote_state.static.outputs.bucket
  key         = "source/remedigenius-ce.zip"
  source      = var.source_zip
  source_hash = filesha256(var.source_zip)
}

locals {
  bucket = data.terraform_remote_state.static.outputs.bucket
  config = {
    name                = var.name, region = var.region, account_id = var.account_id, bucket = local.bucket,
    audit_role_arn      = data.terraform_remote_state.static.outputs.audit_role_arn,
    member_role_arns    = var.member_role_arns, regions = var.regions,
    member_role_name    = var.member_role_name, member_account_ids = var.member_account_ids,
    archive_key         = aws_s3_object.source.key, archive_sha256 = filesha256(var.source_zip),
    model_secret        = var.model_secret_arn, model_name = var.model_name, model_base_url = var.model_base_url,
    scan_interval_hours = var.scan_interval_hours, watch_deliver = var.watch_deliver,
    container_memory_mb = var.container_memory_mb,
    glue_database       = data.terraform_remote_state.static.outputs.glue_database,
    warehouse           = data.terraform_remote_state.static.outputs.warehouse,
    image               = "nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b"
  }
}

resource "aws_launch_template" "host" {
  name_prefix   = "${var.name}-"
  image_id      = var.ami_id
  instance_type = var.spot_instance_types[0]
  iam_instance_profile {
    name = data.terraform_remote_state.static.outputs.instance_profile_name
  }
  network_interfaces {
    associate_public_ip_address = var.public_ip
    security_groups             = [aws_security_group.host.id]
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1 # containers cannot reach instance metadata
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true # disposable; durable state is in S3
    }
  }
  # Same first-boot script as the community stack; it detects the baked image and skips the install work.
  user_data = base64encode(templatefile("${path.module}/../aws-single/user-data.sh.tftpl", { config_b64 = base64encode(jsonencode(local.config)) }))
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = var.name }
  }
  tag_specifications {
    resource_type = "volume"
    tags          = { Name = var.name }
  }
}

resource "aws_autoscaling_group" "host" {
  name                = var.name
  min_size            = 0
  max_size            = 1
  desired_capacity    = var.running ? 1 : 0
  vpc_zone_identifier = [var.subnet_id]
  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.host.id
        version            = aws_launch_template.host.latest_version
      }
      dynamic "override" {
        for_each = var.spot_instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }
}

output "autoscaling_group" {
  value = aws_autoscaling_group.host.name
}

output "bucket" {
  value = local.bucket
}

output "glue_database" {
  value = data.terraform_remote_state.static.outputs.glue_database
}

output "warehouse" {
  value = data.terraform_remote_state.static.outputs.warehouse
}

output "ami_id" {
  value = var.ami_id
}

output "archive_key" {
  value = aws_s3_object.source.key
}