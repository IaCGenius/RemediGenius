# IAM definitions; resource addresses retained.

resource "aws_iam_role" "check" {
  name               = "${var.name}-scheduled-check"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "check" {
  role = aws_iam_role.check.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = var.reader_arn },
    { Effect = "Allow", Action = "s3:ListBucket", Resource = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket}", Condition = { StringLike = { "s3:prefix" = ["${var.prefix}/scheduled/*", "${var.prefix}/raw/*"] } } },
    { Effect = "Allow", Action = "s3:GetObject", Resource = [for p in ["scheduled/*", "raw/*"] : "arn:${data.aws_partition.current.partition}:s3:::${var.bucket}/${var.prefix}/${p}"] },
    { Effect = "Allow", Action = "s3:PutObject", Resource = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket}/${var.prefix}/scheduled/*" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.check.arn}:*" }
  ] })
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.check.arn }] })
}
