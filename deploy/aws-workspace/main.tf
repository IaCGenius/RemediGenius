terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
}
variable "account_id" { type = string }
variable "region" {
  type = string
  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.region))
    error_message = "Use a plain identifier without shell metacharacters."
  }
}
variable "subnet_id" { type = string }
variable "name" { type = string }
variable "bucket_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.bucket_name))
    error_message = "Use a plain identifier without shell metacharacters."
  }
}
variable "workspace_prefix" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.workspace_prefix))
    error_message = "Use a plain identifier without shell metacharacters."
  }
}
variable "image_key" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_./-]+$", var.image_key))
    error_message = "Use a plain identifier without shell metacharacters."
  }
}
variable "image_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.image_sha256))
    error_message = "Provide the SHA256 of the uploaded Docker image archive."
  }
}
variable "image_tag" {
  type    = string
  default = "remedigenius-ce:0.1.0rc9"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.:/-]+$", var.image_tag))
    error_message = "Use a plain Docker image tag."
  }
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
}
data "aws_partition" "current" {}
data "aws_subnet" "selected" { id = var.subnet_id }
data "aws_ssm_parameter" "ami" { name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" }
locals { bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}" }
resource "aws_iam_role" "host" {
  name               = var.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "storage" {
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Deny", Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"], Resource = "*" },
    { Effect = "Allow", Action = "s3:ListBucket", Resource = local.bucket_arn, Condition = { StringLike = { "s3:prefix" = "${var.workspace_prefix}/*" } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.bucket_arn}/${var.workspace_prefix}/*", "${local.bucket_arn}/${var.image_key}"] },
    { Effect = "Allow", Action = "s3:PutObject", Resource = "${local.bucket_arn}/${var.workspace_prefix}/*", Condition = { StringEquals = { "s3:if-none-match" = "*" } } }
  ] })
}
resource "aws_iam_instance_profile" "host" { role = aws_iam_role.host.name }
resource "aws_security_group" "host" {
  name        = var.name
  vpc_id      = data.aws_subnet.selected.vpc_id
  description = "CE private console via SSM; no inbound ports"
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
resource "aws_instance" "workspace" {
  ami                         = data.aws_ssm_parameter.ami.value
  instance_type               = "t3.small"
  subnet_id                   = var.subnet_id
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.host.id]
  iam_instance_profile        = aws_iam_instance_profile.host.name
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    volume_size = 16
    encrypted   = true
  }
  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/boot.sh.tftpl", {
    region    = var.region, bucket = var.bucket_name, prefix = var.workspace_prefix,
    image_key = var.image_key, image_sha = var.image_sha256, image_tag = var.image_tag
  })
  tags       = { Name = var.name, Project = "remedigenius-community", Purpose = "ce-workspace" }
  depends_on = [aws_iam_role_policy.storage, aws_iam_role_policy_attachment.ssm]
}
output "instance_id" { value = aws_instance.workspace.id }
