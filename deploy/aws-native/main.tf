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
  default_tags {
    tags = { Project = "remedigenius-ce", Stack = var.name, ManagedBy = "terraform", CEVersion = "0.1.3" }
  }
}
data "aws_partition" "current" {}
data "aws_subnet" "selected" { id = var.subnet_id }
data "aws_ssm_parameter" "ami" { name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" }
locals {
  arn    = "arn:${data.aws_partition.current.partition}"
  bucket = "${local.arn}:s3:::${var.bucket_name}"
  tags   = { Name = var.name, Project = "remedigenius-ce", Purpose = "native-hermes", Stack = var.name, ManagedBy = "terraform", CEVersion = "0.1.3" }
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
  recovery_window_in_days = var.dashboard_recovery_days
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
  final_snapshot    = true
}
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
  tag_specifications {
    resource_type = "volume"
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
  dynamic "tag" {
    for_each = local.tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }
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
