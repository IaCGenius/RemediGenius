variable "name" { type = string }
variable "bucket" { type = string }
variable "prefix" { type = string }
variable "reader_arn" { type = string }
variable "enabled" { type = bool }
variable "interval_hours" { type = number }
variable "checks_json" { type = string }
data "aws_partition" "current" {}
data "archive_file" "code" {
  type        = "zip"
  output_path = "${path.module}/.build/schedule.zip"
  source {
    content  = file("${path.module}/check.py")
    filename = "check.py"
  }
  source {
    content  = file("${path.module}/../../profiles/ce/desk/skills/ce-aws-read/scripts/evidence_compare.py")
    filename = "evidence_compare.py"
  }
}
resource "aws_iam_role" "check" {
  name               = "${var.name}-scheduled-check"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_cloudwatch_log_group" "check" {
  name              = "/aws/lambda/${var.name}-scheduled-check"
  retention_in_days = 7
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
resource "aws_lambda_function" "check" {
  function_name                  = "${var.name}-scheduled-check"
  role                           = aws_iam_role.check.arn
  filename                       = data.archive_file.code.output_path
  source_code_hash               = data.archive_file.code.output_base64sha256
  handler                        = "check.handler"
  runtime                        = "python3.12"
  timeout                        = 600
  memory_size                    = 256
  reserved_concurrent_executions = 1
  environment { variables = { BUCKET = var.bucket, PREFIX = var.prefix, READER = var.reader_arn, CHECKS = var.checks_json, INTERVAL_HOURS = tostring(var.interval_hours) } }
  depends_on = [aws_iam_role_policy.check]
}
resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_lambda_function_event_invoke_config" "check" {
  function_name                = aws_lambda_function.check.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600
}
resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.check.arn }] })
}
resource "aws_scheduler_schedule" "daily" {
  name                = "${var.name}-assurance"
  state               = var.enabled ? "ENABLED" : "DISABLED"
  schedule_expression = "rate(${var.interval_hours} ${var.interval_hours == 1 ? "hour" : "hours"})"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.check.arn
    role_arn = aws_iam_role.scheduler.arn
    # Preserve literal angle brackets for Scheduler context substitution.
    input = "{\"scheduled_time\":\"<aws.scheduler.scheduled-time>\"}"
    retry_policy { maximum_retry_attempts = 0 }
  }
  depends_on = [aws_iam_role_policy.scheduler]
}
output "function_name" { value = aws_lambda_function.check.function_name }
