variable "audit_principal_arn" {
  description = "Existing operator IAM role/user ARN allowed to assume the optional broad reader role."
  type        = string
  default     = ""
}
# Investigation credentials are separate from CE storage/recovery permissions.
resource "aws_iam_role" "audit" {
  count = var.audit_principal_arn == "" ? 0 : 1
  name  = "${var.name}-audit"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { AWS = var.audit_principal_arn }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy_attachment" "audit_read" {
  for_each   = var.audit_principal_arn == "" ? toset([]) : toset(["SecurityAudit", "job-function/ViewOnlyAccess"])
  role       = aws_iam_role.audit[0].name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_iam_role_policy" "audit_exclusions" {
  count = var.audit_principal_arn == "" ? 0 : 1
  role  = aws_iam_role.audit[0].name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid = "NoCredentialsOrApplicationBodies", Effect = "Deny", Resource = "*",
    Action = ["iam:GenerateCredentialReport", "iam:GenerateServiceLastAccessedDetails", "config:DeliverConfigSnapshot",
      "secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue",
      "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath",
      "ecr:GetAuthorizationToken", "sts:AssumeRole", "sts:GetSessionToken",
      "sts:GetFederationToken", "kms:Decrypt", "kms:GenerateDataKey*",
      "s3:GetObject", "s3:GetObjectVersion", "s3-object-lambda:GetObject",
      "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan",
    "rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"]
  }] })
}

output "audit_role_arn" { value = try(aws_iam_role.audit[0].arn, "") }
