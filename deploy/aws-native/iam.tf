# IAM definitions; resource addresses retained.

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

resource "aws_iam_instance_profile" "host" {
  name = coalesce(var.instance_profile_name, var.name)
  role = aws_iam_role.host.name
}

resource "aws_iam_role" "reader_invoker" {
  name               = "${var.name}-reader-invoker"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { AWS = aws_iam_role.host.arn }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "reader_invoker" {
  role   = aws_iam_role.reader_invoker.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = module.aws_read.function_arn }, { Effect = "Allow", Action = "s3:GetObject", Resource = [for p in ["raw/*", "normalized/*", "receipts/*", "scheduled/*"] : "${local.bucket}/${var.workspace_prefix}/${p}"] }] })
}
