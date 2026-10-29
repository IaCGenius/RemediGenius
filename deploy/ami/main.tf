# Baked image: Amazon Linux 2023 with the host runtime and the pinned Hermes image already on disk.
#
# Why: the 300 s first boot was install work (dnf, pip wheels, docker pull), not virtualisation. One image per release
# removes all of it, so a Spot replacement costs launch + restore instead of a download.
#
#   terraform init -backend-config=../backend.hcl
#   terraform apply -var account_id=<id> -var release=0.6.0 -var source_zip=... -var subnet_id=...
#   terraform output ami_id          # feed this to deploy/aws-private or deploy/aws-single (ami_id)
#
# The image contains: docker + enabled, the pinned wheel set in /opt/rgtriage/venv, Terraform and tflint binaries,
# nousresearch/hermes-agent by digest, and the release zip at /opt/remedigenius/source.zip. It contains no data:
# /data is restored from S3 at boot, and the bake removes cloud-init state and machine identity.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }
  backend "s3" {
    key = "aws-ami/terraform.tfstate"
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
  description = "Installation name, used for the image name and its tags."
}

variable "release" {
  type        = string
  description = "Release version this image is baked from (for example 0.6.0). Part of the image name."
}

variable "source_zip" {
  type        = string
  description = "Release package from tools/package_release.py. The same bytes are baked and then mounted at boot."
}

variable "state_bucket" {
  type        = string
  description = "Terraform state bucket from deploy/bootstrap (the release zip is staged in the data bucket)."
}

variable "static_key" {
  type    = string
  default = "aws-static/terraform.tfstate"
}

variable "subnet_id" {
  type        = string
  default     = ""
  description = "Optional subnet for the bake instance (needs outbound HTTPS). Empty uses the default VPC."
}

variable "instance_types" {
  type    = list(string)
  default = ["c7i.large", "m7i.large", "c6i.large"]
}

variable "security_group_ids" {
  type        = list(string)
  default     = []
  description = "Security groups for the bake instance. Required when subnet_id is set; leave both empty to use the default VPC."
}

# Image Builder rejects a subnet without security groups (InvalidParameterCombinationException), so say it here
# instead of failing halfway through an apply.
check "bake_network" {
  assert {
    condition     = (var.subnet_id == "" && length(var.security_group_ids) == 0) || (var.subnet_id != "" && length(var.security_group_ids) > 0)
    error_message = "Set security_group_ids whenever subnet_id is set, and leave both empty to bake in the default VPC."
  }
}

variable "architecture" {
  type    = string
  default = "x86_64"
  validation {
    condition     = contains(["x86_64", "arm64"], var.architecture)
    error_message = "Choose x86_64 or arm64; the Spot stack's instance types must match."
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

locals {
  bucket      = data.terraform_remote_state.static.outputs.bucket
  hermes      = "nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b"
  archive_key = "bake/remedigenius-ce-${var.release}.zip"
  archive_sha = filesha256(var.source_zip)
  parent = {
    x86_64 = "arn:aws:imagebuilder:${var.region}:aws:image/amazon-linux-2023-x86/x.x.x"
    arm64  = "arn:aws:imagebuilder:${var.region}:aws:image/amazon-linux-2023-arm64/x.x.x"
  }
}

resource "aws_s3_object" "source" {
  bucket      = local.bucket
  key         = local.archive_key
  source      = var.source_zip
  source_hash = local.archive_sha
}

# The build instance reads exactly this one archive and nothing else.
resource "aws_iam_role" "bake" {
  name               = "${var.name}-image-bake"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy_attachment" "bake_builder" {
  role       = aws_iam_role.bake.name
  policy_arn = "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilder"
}

resource "aws_iam_role_policy_attachment" "bake_ssm" {
  role       = aws_iam_role.bake.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "bake_source" {
  role = aws_iam_role.bake.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = data.terraform_remote_state.static.outputs.bucket_arn },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${data.terraform_remote_state.static.outputs.bucket_arn}/${local.archive_key}" }
  ] })
}

resource "aws_iam_instance_profile" "bake" {
  name = "${var.name}-image-bake"
  role = aws_iam_role.bake.name
}

# Runs the same host.py the instance runs, with --bake: install the runtime, pull the image, write the marker, stop.
# No desk config, no state restore and no systemd units are written into the image.
resource "aws_imagebuilder_component" "bake" {
  name     = "${var.name}-runtime"
  version  = var.release
  platform = "Linux"
  data = jsonencode({
    name          = "rgce-runtime"
    description   = "RemediGenius-CE host runtime and pinned Hermes image"
    schemaVersion = "1.0"
    phases = [{
      name = "build"
      steps = [{
        name   = "install-runtime"
        action = "ExecuteBash"
        inputs = {
          commands = [
            "set -euxo pipefail",
            "dnf install -y docker python3 unzip iptables util-linux",
            "systemctl enable docker",
            "systemctl start docker",
            "install -d -m 0700 /opt/remedigenius",
            "command -v aws || dnf install -y awscli-2 || pip3 install --quiet awscli",
            "aws s3 cp s3://${local.bucket}/${local.archive_key} /opt/remedigenius/source.zip --region ${var.region}",
            "echo '${local.archive_sha}  /opt/remedigenius/source.zip' | sha256sum -c -",
            "python3 -c \"import zipfile; zipfile.ZipFile('/opt/remedigenius/source.zip').extractall('/opt/remedigenius/source')\"",
            "python3 /opt/remedigenius/source/deploy/aws-single/host.py --bake --image ${local.hermes} --version ${var.release}"
          ]
        }
      }]
    }]
  })
}

resource "aws_imagebuilder_image_recipe" "bake" {
  name         = "${var.name}-runtime"
  version      = var.release
  parent_image = local.parent[var.architecture]
  component {
    component_arn = aws_imagebuilder_component.bake.arn
  }
  # The bake instance is the only thing that changes: keep the disk big enough for the image pull.
  block_device_mapping {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      delete_on_termination = true
    }
  }
}

resource "aws_imagebuilder_infrastructure_configuration" "bake" {
  name                          = "${var.name}-image-bake"
  instance_profile_name         = aws_iam_instance_profile.bake.name
  instance_types                = var.instance_types
  subnet_id                     = var.subnet_id == "" ? null : var.subnet_id
  security_group_ids            = length(var.security_group_ids) == 0 ? null : var.security_group_ids
  terminate_instance_on_failure = true
}

resource "aws_imagebuilder_distribution_configuration" "bake" {
  name = "${var.name}-image"
  distribution {
    region = var.region
    ami_distribution_configuration {
      name        = "rgce-v${var.release}-{{ imagebuilder:buildDate }}"
      description = "RemediGenius-CE v${var.release} host image (Hermes pinned by digest, runtime pre-installed)"
      ami_tags = {
        Project          = "remedigenius-ce"
        RemediGeniusVer  = var.release
        RemediGeniusKind = "host-image"
      }
    }
  }
}

# Building on apply keeps "one image per release" honest: apply once, then pin the ami_id everywhere.
resource "aws_imagebuilder_image" "bake" {
  infrastructure_configuration_arn = aws_imagebuilder_infrastructure_configuration.bake.arn
  image_recipe_arn                 = aws_imagebuilder_image_recipe.bake.arn
  distribution_configuration_arn   = aws_imagebuilder_distribution_configuration.bake.arn
}

output "ami_id" {
  value       = try(tolist(tolist(aws_imagebuilder_image.bake.output_resources)[0].amis)[0].image, "")
  description = "Pass to deploy/aws-private -var ami_id=... or deploy/aws-single -var ami_id=..."
}

output "archive_key" {
  value = local.archive_key
}

output "archive_sha256" {
  value = local.archive_sha
}

output "hermes_image" {
  value = local.hermes
}