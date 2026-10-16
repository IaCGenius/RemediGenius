# IAM definitions; resource addresses retained.

resource "aws_iam_role" "collector" {
  name               = "${var.name}-discovery"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "collector" {
  role = aws_iam_role.collector.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["securitylake:ListDataLakes", "securityhub:DescribeHub", "securityhub:GetFindings", "guardduty:ListDetectors", "inspector2:BatchGetAccountStatus", "config:DescribeConfigurationRecorders", "cloudtrail:DescribeTrails"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
    { Effect = "Allow", Action = "s3:PutObject", Resource = [for p in ["raw/*", "normalized/*", "receipts/*", "catalog.json"] : "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}/${var.workspace_prefix}/${p}"] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.collector.arn}:*" }
  ] })
}
