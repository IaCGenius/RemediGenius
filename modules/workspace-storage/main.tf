variable "bucket_name" { type = string }
variable "prefix" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.prefix))
    error_message = "Use a workspace prefix without leading/trailing slash."
  }
}
variable "trusted_principal_arn" { type = string }
variable "external_id" {
  type      = string
  sensitive = true
}
variable "role_name" { type = string }
data "aws_partition" "current" {}
locals { bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}" }
output "role_arn" { value = aws_iam_role.storage.arn }
