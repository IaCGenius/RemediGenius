# IAM definitions; resource addresses retained.

resource "aws_iam_role" "storage" {
  name               = var.role_name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { AWS = var.trusted_principal_arn }, Action = "sts:AssumeRole", Condition = { StringEquals = { "sts:ExternalId" = var.external_id } } }] })
}

resource "aws_iam_role_policy" "storage" {
  role = aws_iam_role.storage.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:ListBucket", Resource = local.bucket_arn, Condition = { StringLike = { "s3:prefix" = "${var.prefix}/*" } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = "${local.bucket_arn}/${var.prefix}/*" },
    { Effect = "Allow", Action = "s3:PutObject", Resource = "${local.bucket_arn}/${var.prefix}/*", Condition = { StringEquals = { "s3:if-none-match" = "*" } } }
  ] })
}
