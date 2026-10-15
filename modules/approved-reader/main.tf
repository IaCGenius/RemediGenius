terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
}
variable "name" { type = string }
variable "read_role_arn" { type = string }
variable "source_spec" { type = any }
variable "external_id" {
  type      = string
  sensitive = true
}
variable "output_bucket" { type = string }
variable "output_bucket_arn" { type = string }
variable "enabled" {
  type    = bool
  default = false
}
resource "aws_iam_role" "execution" {
  name               = "${var.name}-reader-exec"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_cloudwatch_log_group" "reader" {
  name              = "/aws/lambda/${var.name}-reader"
  retention_in_days = 1
}
resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "sts:AssumeRole", Resource = var.read_role_arn, Condition = { StringEquals = { "sts:ExternalId" = var.external_id } } },
    { Effect = "Allow", Action = "s3:PutObject", Resource = "${var.output_bucket_arn}/outputs/reader/*" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.reader.arn}:*" }
  ] })
}
resource "aws_lambda_layer_version" "runtime" {
  layer_name          = "${var.name}-reader-runtime"
  filename            = "${path.module}/build/runtime-layer.zip"
  source_code_hash    = filebase64sha256("${path.module}/build/runtime-layer.zip")
  compatible_runtimes = ["python3.13"]
}
resource "aws_lambda_function" "reader" {
  function_name                  = "${var.name}-reader"
  role                           = aws_iam_role.execution.arn
  filename                       = "${path.module}/build/reader.zip"
  source_code_hash               = filebase64sha256("${path.module}/build/reader.zip")
  handler                        = "handler.main"
  runtime                        = "python3.13"
  timeout                        = 60
  memory_size                    = 256
  reserved_concurrent_executions = var.enabled ? 1 : 0
  layers                         = [aws_lambda_layer_version.runtime.arn]
  environment {
    variables = {
      RGCE_ENABLED       = tostring(var.enabled)
      RGCE_SOURCE        = jsonencode(var.source_spec)
      RGCE_EXTERNAL_ID   = var.external_id
      RGCE_OUTPUT_BUCKET = var.output_bucket
      RGCE_CODE_SHA256   = filesha256("${path.module}/build/reader.zip")
    }
  }
  depends_on = [aws_iam_role_policy.execution]
}
output "execution_role_arn" { value = aws_iam_role.execution.arn }
output "function_name" { value = aws_lambda_function.reader.function_name }
output "enabled" { value = var.enabled }
