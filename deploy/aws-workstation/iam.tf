# IAM definitions; resource addresses retained.

resource "aws_iam_role" "invoker" {
  name               = "${var.name}-invoker"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { AWS = var.operator_arn }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy" "invoker" {
  role = aws_iam_role.invoker.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = module.reader.function_arn },
    { Effect = "Allow", Action = "s3:GetObject", Resource = [for p in ["raw/*", "normalized/*", "receipts/*", "scheduled/*"] : "${aws_s3_bucket.evidence.arn}/${local.prefix}/${p}"] }
  ] })
}
