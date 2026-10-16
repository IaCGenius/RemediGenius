# IAM definitions; resource addresses retained.

resource "aws_iam_role" "executor" {
  name               = "${var.name}-aws-read"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "executor" {
  role = aws_iam_role.executor.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = local.read_actions, Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = local.regions } } },
    { Effect = "Allow", Action = "s3:PutObject", Resource = [for p in ["raw/*", "normalized/*", "receipts/*", "catalog.json"] : "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}/${var.workspace_prefix}/${p}"] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.executor.arn}:*" }
  ], length(local.roles) == 0 ? [] : [{ Effect = "Allow", Action = "sts:AssumeRole", Resource = local.roles }]) })
}
