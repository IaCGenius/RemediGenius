terraform {
  required_version = ">= 1.10"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.80" } }
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
}
data "aws_partition" "current" {}
data "aws_subnet" "selected" { id = var.subnet_id }
data "aws_ssm_parameter" "ami" { name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" }
locals {
  bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}"
  tags       = { Project = "remedigenius-community", Purpose = "ce-hermes", Name = var.name }
}
resource "aws_iam_role" "host" {
  name               = var.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = local.tags
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "host" {
  role = aws_iam_role.host.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = concat([
      { Effect = "Deny", Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"], Resource = "*" },
      { Effect = "Allow", Action = "s3:ListBucket", Resource = local.bucket_arn, Condition = { StringLike = { "s3:prefix" = "${var.workspace_prefix}/*" } } },
      { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.bucket_arn}/${var.workspace_prefix}/*", "${local.bucket_arn}/${var.console_image_key}", "${local.bucket_arn}/${var.hermes_image_key}"] },
      { Effect = "Allow", Action = "s3:PutObject", Resource = "${local.bucket_arn}/${var.workspace_prefix}/*", Condition = { StringEquals = { "s3:if-none-match" = "*" } } },
      { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.model_secret_arn }
      ], var.secret_kms_key_arn == null ? [] : [
      { Effect = "Allow", Action = "kms:Decrypt", Resource = var.secret_kms_key_arn, Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com", "kms:EncryptionContext:SecretARN" = var.model_secret_arn } } }
  ]) })
}
resource "aws_iam_instance_profile" "host" { role = aws_iam_role.host.name }
resource "aws_security_group" "host" {
  name        = var.name
  description = "CE Hermes: SSM only; no inbound ports"
  vpc_id      = data.aws_subnet.selected.vpc_id
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
  tags = local.tags
}
resource "aws_launch_template" "host" {
  name_prefix   = "${var.name}-"
  image_id      = data.aws_ssm_parameter.ami.value
  instance_type = var.instance_type
  iam_instance_profile { name = aws_iam_instance_profile.host.name }
  network_interfaces {
    associate_public_ip_address = var.associate_public_ip
    security_groups             = [aws_security_group.host.id]
    delete_on_termination       = true
  }
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    http_protocol_ipv6          = "disabled"
    instance_metadata_tags      = "disabled"
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 24
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  user_data = base64encode(templatefile("${path.module}/boot.sh.tftpl", {
    region      = var.region, bucket = var.bucket_name, prefix = var.workspace_prefix,
    console_key = var.console_image_key, console_sha = var.console_archive_sha256, console_id = var.console_image_id,
    hermes_key  = var.hermes_image_key, hermes_sha = var.hermes_archive_sha256, hermes_id = var.hermes_image_id,
    secret_arn  = var.model_secret_arn,
    model_config_b64 = base64encode(jsonencode({
      RGCE_MODEL_PROVIDER = var.model_provider, RGCE_MODEL_NAME = var.model_name,
      RGCE_MODEL_BASE_URL = var.model_base_url, RGCE_MODEL_KEY_ENV = var.model_key_env
    }))
  }))
  tag_specifications {
    resource_type = "instance"
    tags          = local.tags
  }
  tag_specifications {
    resource_type = "volume"
    tags          = local.tags
  }
  tags = local.tags
}
resource "aws_autoscaling_group" "hermes" {
  name                      = var.name
  min_size                  = 0
  max_size                  = var.running ? 1 : 0
  desired_capacity          = var.running ? 1 : 0
  vpc_zone_identifier       = [var.subnet_id]
  capacity_rebalance        = false
  health_check_type         = "EC2"
  health_check_grace_period = 600
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
    }
  }
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0
      max_healthy_percentage = 100
      instance_warmup        = 600
      skip_matching          = true
    }
  }
  depends_on = [aws_iam_role_policy.host, aws_iam_role_policy_attachment.ssm]
}
output "autoscaling_group" { value = aws_autoscaling_group.hermes.name }
output "host_role_arn" { value = aws_iam_role.host.arn }
output "access" { value = "Use SSM StartPortForwardingSession to port 8765 on the active ASG instance; no inbound security-group rules." }
