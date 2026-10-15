# One spot instance running the agents in Docker (Hermes Agent, MIT). Spot with auto-replace, IMDSv2,
# keys only in Secrets Manager rendered to tmpfs at boot, a thin user-data that syncs the boot scripts from
# S3. No open ports: Hermes Desktop and the dashboard are reached through an SSM port forward (connect.sh).
# Agent state lives on the data volume, re-attached on every boot, so it survives a spot replacement.
#
# The agents run in a bridged container. IMDS hop limit 1 plus an iptables drop keeps the container away
# from the instance credentials: the agents hold no AWS keys. Only the host's collector (no AI) reads AWS.

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

# ---------------------------------------------------------------- boot code + profiles (the host syncs them at every boot)
locals {
  profile_names = var.enable_kiosk ? ["desk", "analyst", "builder"] : ["desk", "analyst"]
  profile_files = toset(flatten([
    for p in local.profile_names : [
      for f in fileset("${local.root}/profiles/${p}", "**") : "${p}/${f}"
      if !can(regex("(^|/)(\\.git|\\.env|auth\\.json|__pycache__)|\\.pyc$", f))
    ]
  ]))
  # Files with placeholders for your model and the kiosk name; filled in here, uploaded as content.
  profile_rendered = toset([for f in local.profile_files : f if can(regex("^([a-z]+/config\\.yaml|builder/kiosk\\.json)$", f))])
  profile_static   = setsubtract(local.profile_files, local.profile_rendered)
}

resource "aws_s3_object" "host" {
  for_each    = toset([for f in fileset("${path.module}/host", "**") : f if !can(regex("__pycache__|\\.pyc$", f))])
  bucket      = aws_s3_bucket.main.id
  key         = "engine-code/dist/${each.value}"
  source      = "${path.module}/host/${each.value}"
  source_hash = filemd5("${path.module}/host/${each.value}")
}

resource "aws_s3_object" "profile" {
  for_each    = local.profile_static
  bucket      = aws_s3_bucket.main.id
  key         = "engine-code/profiles/${each.value}"
  source      = "${local.root}/profiles/${each.value}"
  source_hash = filemd5("${local.root}/profiles/${each.value}")
}

resource "aws_s3_object" "profile_rendered" {
  for_each = local.profile_rendered
  bucket   = aws_s3_bucket.main.id
  key      = "engine-code/profiles/${each.value}"
  content = replace(replace(replace(file("${local.root}/profiles/${each.value}"),
    "__MODEL_NAME__", var.model_name), "__MODEL_BASE_URL__", var.model_base_url),
  "__KIOSK_NAME__", var.name_prefix)
}

# ---------------------------------------------------------------- dashboard login (generated, read once by you)
resource "random_password" "dashboard" {
  length  = 32
  special = false
}

resource "random_password" "dashboard_secret" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "dashboard" {
  name                    = "${var.name_prefix}/hermes/dashboard-login"
  description             = "Dashboard username/password for Hermes Desktop (reached only through the SSM port forward)."
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = var.secret_recovery_days
}

resource "aws_secretsmanager_secret_version" "dashboard" {
  secret_id = aws_secretsmanager_secret.dashboard.id
  secret_string = jsonencode({
    username = "owner"
    password = random_password.dashboard.result
    secret   = random_password.dashboard_secret.result
  })
}

# ---------------------------------------------------------------- instance role
resource "aws_iam_role" "host" {
  name = "${local.name}-host"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "host" {
  name = "${local.name}-runtime"
  role = aws_iam_role.host.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadOwnSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.model_key.arn, aws_secretsmanager_secret.dashboard.arn]
      },
      {
        # Collector only (host, not the container): which accounts to read and how.
        Sid      = "ReadAccountSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:${var.name_prefix}/hermes/tenant/*"]
      },
      {
        # collect.py --all finds the accounts by listing secret names (values still need the grant above).
        Sid      = "ListAccountSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:ListSecrets"]
        Resource = "*"
      },
      {
        Sid      = "UseOwnKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = [aws_kms_key.main.arn]
      },
      {
        # Attaching the encrypted data volume makes EC2 create a grant on the key.
        Sid       = "GrantForDataVolumeAttach"
        Effect    = "Allow"
        Action    = ["kms:CreateGrant"]
        Resource  = [aws_kms_key.main.arn]
        Condition = { Bool = { "kms:GrantIsForAWSResource" = "true" } }
      },
      {
        Sid      = "ReadBootCode"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.main.arn}/engine-code/*"]
      },
      {
        Sid      = "ReadWriteResults"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.main.arn}/results/*"]
      },
      {
        Sid       = "ListOwnPrefixes"
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = [aws_s3_bucket.main.arn]
        Condition = { StringLike = { "s3:prefix" = ["engine-code/*", "results/*"] } }
      },
      {
        Sid      = "FindDataVolume"
        Effect   = "Allow"
        Action   = ["ec2:DescribeVolumes"]
        Resource = "*"
      },
      {
        Sid      = "AttachOwnDataVolume"
        Effect   = "Allow"
        Action   = ["ec2:AttachVolume"]
        Resource = [aws_ebs_volume.data.arn]
      },
      {
        Sid       = "AttachToEngineInstanceOnly"
        Effect    = "Allow"
        Action    = ["ec2:AttachVolume"]
        Resource  = ["arn:aws:ec2:${var.region}:${var.account_id}:instance/*"]
        Condition = { StringEquals = { "aws:ResourceTag/Name" = local.name } }
      },
      {
        # The only way into an assessed account: its read-only role (onboarding/aws/readonly-role.yaml).
        Sid      = "AssumeReadOnlyRoles"
        Effect   = "Allow"
        Action   = ["sts:AssumeRole"]
        Resource = ["arn:aws:iam::*:role/${var.readonly_role_name}"]
      },
      {
        # Kiosk agents: kiosk-creds.sh hands each profile with kiosk.json a 1-hour session, never the instance role.
        Sid      = "AssumeKioskAgentRoles"
        Effect   = "Allow"
        Action   = ["sts:AssumeRole", "sts:SetSourceIdentity"]
        Resource = ["arn:aws:iam::${var.account_id}:role/kiosk-${var.name_prefix}-agent-*"]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "host" {
  name = "${local.name}-host"
  role = aws_iam_role.host.name
}

# ---------------------------------------------------------------- launch template + spot Auto Scaling group
resource "aws_launch_template" "host" {
  name                   = local.name
  image_id               = data.aws_ami.ubuntu.id
  update_default_version = true

  iam_instance_profile { name = aws_iam_instance_profile.host.name }

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [aws_security_group.host.id]
    delete_on_termination       = true
  }

  # IMDSv2 only, hop limit 1: a bridged container cannot reach the instance credentials.
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = var.root_volume_gb
      volume_type           = "gp3"
      encrypted             = true # the root disk holds no secrets (they live in tmpfs)
      delete_on_termination = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/host-user-data.sh.tftpl", {
    region              = var.region
    bucket              = aws_s3_bucket.main.id
    data_volume_id      = aws_ebs_volume.data.id
    secret_model        = aws_secretsmanager_secret.model_key.name
    secret_login        = aws_secretsmanager_secret.dashboard.name
    hermes_image        = var.hermes_image
    dashboard_port      = var.dashboard_port
    name_prefix         = var.name_prefix
    schedule_enabled    = var.schedule_enabled
    collect_on_calendar = var.collect_on_calendar
  }))

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = local.name }
  }
  tag_specifications {
    resource_type = "volume"
    tags          = { Name = "${local.name}-root" }
  }

  # The host reads boot code, profiles and secrets at first boot.
  depends_on = [aws_s3_object.host, aws_s3_object.profile, aws_s3_object.profile_rendered, aws_secretsmanager_secret_version.dashboard]
}

resource "aws_autoscaling_group" "host" {
  name                = local.name
  min_size            = 0
  max_size            = 1
  desired_capacity    = var.running ? 1 : 0
  vpc_zone_identifier = [aws_subnet.public.id]
  health_check_type   = "EC2"

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.host.id
        version            = aws_launch_template.host.latest_version # "$Latest" would never trigger the refresh below
      }
      dynamic "override" {
        for_each = var.instance_types
        content { instance_type = override.value }
      }
    }
  }

  # A new launch template version replaces the instance (state is on the data volume).
  instance_refresh {
    strategy = "Rolling"
    preferences { min_healthy_percentage = 0 }
  }

  tag {
    key                 = "Name"
    value               = local.name
    propagate_at_launch = true
  }
}
