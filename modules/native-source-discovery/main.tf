terraform {
  required_providers {
    aws     = { source = "hashicorp/aws" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
}
variable "name" { type = string }
variable "bucket_name" { type = string }
variable "workspace_prefix" { type = string }
variable "region" { type = string }
variable "account_id" { type = string }
data "aws_partition" "current" {}
data "archive_file" "code" {
  type        = "zip"
  source_file = "${path.module}/collector.py"
  output_path = "${path.root}/.terraform/native-source-discovery.zip"
}
resource "aws_iam_role" "collector" {
  name               = "${var.name}-discovery"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_cloudwatch_log_group" "collector" {
  name              = "/aws/lambda/${var.name}-discovery"
  retention_in_days = 1
}
resource "aws_iam_role_policy" "collector" {
  role = aws_iam_role.collector.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["securitylake:ListDataLakes", "securityhub:DescribeHub", "securityhub:GetFindings", "guardduty:ListDetectors", "inspector2:BatchGetAccountStatus", "config:DescribeConfigurationRecorders", "cloudtrail:DescribeTrails"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
    { Effect = "Allow", Action = "s3:PutObject", Resource = [for p in ["raw/*", "normalized/*", "receipts/*", "catalog.json"] : "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}/${var.workspace_prefix}/${p}"] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.collector.arn}:*" }
  ] })
}
resource "aws_lambda_function" "collector" {
  function_name                  = "${var.name}-discovery"
  role                           = aws_iam_role.collector.arn
  filename                       = data.archive_file.code.output_path
  source_code_hash               = data.archive_file.code.output_base64sha256
  handler                        = "collector.handler"
  runtime                        = "python3.12"
  timeout                        = 90
  memory_size                    = 256
  reserved_concurrent_executions = 1
  environment { variables = { REGION = var.region, ACCOUNT_ID = var.account_id, BUCKET = var.bucket_name, PREFIX = var.workspace_prefix } }
  depends_on = [aws_iam_role_policy.collector]
}
output "function_arn" { value = aws_lambda_function.collector.arn }
