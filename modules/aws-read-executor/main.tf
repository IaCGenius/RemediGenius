variable "name" { type = string }
variable "bucket_name" { type = string }
variable "workspace_prefix" { type = string }
variable "region" { type = string }
variable "account_id" { type = string }
variable "targets" { type = map(object({ account_id = string, regions = list(string), role_arn = optional(string, ""), external_id = optional(string, "") })) }
locals {
  operations   = jsondecode(file("${path.module}/operations.json"))
  read_actions = distinct(flatten([for methods in values(local.operations) : values(methods)]))
  regions      = distinct(flatten([for target in values(var.targets) : target.regions]))
  roles        = compact([for target in values(var.targets) : target.role_arn])
}
data "aws_partition" "current" {}
data "archive_file" "code" {
  type        = "zip"
  output_path = "${path.root}/.terraform/aws-read-executor.zip"
  source {
    content  = file("${path.module}/executor.py")
    filename = "executor.py"
  }
  source {
    content  = file("${path.module}/operations.json")
    filename = "operations.json"
  }
}
resource "aws_cloudwatch_log_group" "executor" {
  name              = "/aws/lambda/${var.name}-aws-read"
  retention_in_days = 7
}
resource "aws_lambda_function" "executor" {
  function_name                  = "${var.name}-aws-read"
  role                           = aws_iam_role.executor.arn
  filename                       = data.archive_file.code.output_path
  source_code_hash               = data.archive_file.code.output_base64sha256
  handler                        = "executor.handler"
  runtime                        = "python3.12"
  timeout                        = 90
  memory_size                    = 512
  reserved_concurrent_executions = 2
  environment { variables = { ACCOUNT_ID = var.account_id, BUCKET = var.bucket_name, PREFIX = var.workspace_prefix, TARGETS = jsonencode(var.targets) } }
  depends_on = [aws_iam_role_policy.executor]
}
output "function_arn" { value = aws_lambda_function.executor.arn }
