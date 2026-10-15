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
}
data "aws_partition" "current" {}
data "aws_subnet" "selected" { id = var.subnet_id }
data "aws_ssm_parameter" "ami" { name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" }
locals {
  arn    = "arn:${data.aws_partition.current.partition}"
  bucket = "${local.arn}:s3:::${var.bucket_name}"
  tags   = { Name = var.name, Project = "remedigenius-community", Purpose = "native-hermes-sketch" }
  config = {
    region              = var.region, bucket = var.bucket_name, prefix = var.workspace_prefix,
    archive_key         = var.source_archive_key, archive_sha256 = var.source_archive_sha256,
    image               = var.hermes_image, model_secret = var.model_secret_arn, dashboard_secret = aws_secretsmanager_secret.dashboard.arn,
    toolsets            = var.hermes_toolsets,
    container_memory_mb = var.container_memory_mb,
    model_name          = var.model_name, model_base_url = var.model_base_url, profiles_dir = var.profiles_dir,
    reader_function     = module.aws_read.function_arn, reader_invoker_role = aws_iam_role.reader_invoker.arn,
    knowledge_view      = var.knowledge_view,
    volume_id           = aws_ebs_volume.sessions.id, collector_arn = module.discovery.function_arn
  }
}
module "discovery" {
  source           = "../../modules/native-source-discovery"
  name             = var.name
  bucket_name      = var.bucket_name
  workspace_prefix = var.workspace_prefix
  region           = var.region
  account_id       = var.account_id
}
resource "random_password" "dashboard" {
  length  = 32
  special = false
}
resource "random_password" "session" {
  length  = 48
  special = false
}
resource "aws_secretsmanager_secret" "dashboard" {
  name                    = "${var.name}/dashboard"
  recovery_window_in_days = 7
  tags                    = local.tags
}
resource "aws_secretsmanager_secret_version" "dashboard" {
  secret_id     = aws_secretsmanager_secret.dashboard.id
  secret_string = jsonencode({ username = "owner", password = random_password.dashboard.result, secret = random_password.session.result })
}
resource "aws_ebs_volume" "sessions" {
  availability_zone = data.aws_subnet.selected.availability_zone
  size              = 20
  type              = "gp3"
  encrypted         = true
  tags              = merge(local.tags, { Name = "${var.name}-sessions" })
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role" "host" {
  name               = var.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = local.tags
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "${local.arn}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "host" {
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Deny", Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"], Resource = "*" },
    { Effect = "Allow", Action = "s3:ListBucket", Resource = local.bucket, Condition = { StringLike = { "s3:prefix" = "${var.workspace_prefix}/*" } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = ["${local.bucket}/${var.workspace_prefix}/*", "${local.bucket}/${var.source_archive_key}"] },
    { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = module.discovery.function_arn },
    { Effect = "Allow", Action = "sts:AssumeRole", Resource = aws_iam_role.reader_invoker.arn },
    { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = [var.model_secret_arn, aws_secretsmanager_secret.dashboard.arn] },
    { Effect = "Allow", Action = "ec2:DescribeVolumes", Resource = "*" },
    { Effect = "Allow", Action = "ec2:AttachVolume", Resource = aws_ebs_volume.sessions.arn },
    { Effect = "Allow", Action = "ec2:AttachVolume", Resource = "${local.arn}:ec2:${var.region}:${var.account_id}:instance/*", Condition = { StringEquals = { "ec2:ResourceTag/Name" = var.name } } }
    ], length(var.read_role_arns) == 0 ? [] : [
    { Effect = "Allow", Action = ["sts:AssumeRole", "sts:SetSourceIdentity"], Resource = var.read_role_arns }
    ], length(var.secret_kms_key_arns) == 0 ? [] : [
    { Effect = "Allow", Action = "kms:Decrypt", Resource = var.secret_kms_key_arns, Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com", "kms:EncryptionContext:SecretARN" = [var.model_secret_arn, aws_secretsmanager_secret.dashboard.arn] } } }
  ]) })
}
resource "aws_iam_instance_profile" "host" { role = aws_iam_role.host.name }
resource "aws_security_group" "host" {
  name        = var.name
  description = "Native Hermes via SSM only"
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
  user_data = base64encode(templatefile("${path.module}/user-data.sh.tftpl", { config_b64 = base64encode(jsonencode(local.config)) }))
  tag_specifications {
    resource_type = "instance"
    tags          = local.tags
  }
  tags = local.tags
}
resource "aws_autoscaling_group" "native" {
  name                = var.name
  min_size            = 0
  max_size            = 1
  desired_capacity    = var.running ? 1 : 0
  vpc_zone_identifier = [var.subnet_id]
  capacity_rebalance  = false
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
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0
      max_healthy_percentage = 100
      instance_warmup        = 600
    }
  }
  depends_on = [aws_iam_role_policy.host, aws_iam_role_policy_attachment.ssm, aws_secretsmanager_secret_version.dashboard]
}
output "autoscaling_group" { value = aws_autoscaling_group.native.name }
output "host_role_arn" { value = aws_iam_role.host.arn }
output "session_volume_id" { value = aws_ebs_volume.sessions.id }
output "gateway_port" { value = 9120 }
output "dashboard_secret_arn" { value = aws_secretsmanager_secret.dashboard.arn }

module "aws_read" {
  source           = "../../modules/aws-read-executor"
  name             = var.name
  bucket_name      = var.bucket_name
  workspace_prefix = var.workspace_prefix
  region           = var.region
  account_id       = var.account_id
  targets          = length(var.aws_read_targets) > 0 ? var.aws_read_targets : { default = { account_id = var.account_id, regions = [var.region], role_arn = "", external_id = "" } }
}
resource "aws_iam_role" "reader_invoker" {
  name               = "${var.name}-reader-invoker"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { AWS = aws_iam_role.host.arn }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "reader_invoker" {
  role   = aws_iam_role.reader_invoker.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = module.aws_read.function_arn }, { Effect = "Allow", Action = "s3:GetObject", Resource = [for p in ["raw/*", "normalized/*", "receipts/*", "scheduled/*"] : "${local.bucket}/${var.workspace_prefix}/${p}"] }] })
}

module "assurance" {
  source         = "../../modules/assurance-schedule"
  name           = var.name
  bucket         = var.bucket_name
  prefix         = var.workspace_prefix
  reader_arn     = module.aws_read.function_arn
  enabled        = var.schedule_enabled
  interval_hours = var.schedule_interval_hours
  checks_json = length(var.scheduled_checks) > 0 ? jsonencode(var.scheduled_checks) : jsonencode([
    { target = "default", region = var.region, service = "securityhub", operation = "get_findings", parameters = { Filters = { RecordState = [{ Value = "ACTIVE", Comparison = "EQUALS" }] } }, max_pages = 2 },
    { target = "default", region = var.region, service = "config", operation = "describe_configuration_recorders", parameters = {}, max_pages = 1 }
  ])
}
