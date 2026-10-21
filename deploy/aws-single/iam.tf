# Instance role: SSM, its own bucket, the model secret, and assuming the read-only roles.
# AWS security reads go through the audit role (and member read roles), never the instance role.
resource "aws_iam_role" "host" {
  name               = var.name
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_instance_profile" "host" {
  name = var.name
  role = aws_iam_role.host.name
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The model secret may be encrypted with a customer-managed KMS key; grant decrypt for exactly that key.
data "aws_secretsmanager_secret" "model" {
  count = var.model_secret_arn == "" ? 0 : 1
  arn   = var.model_secret_arn
}
data "aws_kms_key" "model" {
  count  = var.model_secret_arn != "" && try(data.aws_secretsmanager_secret.model[0].kms_key_id, "") != "" ? 1 : 0
  key_id = data.aws_secretsmanager_secret.model[0].kms_key_id
}
locals {
  model_kms_key_arns = [for k in data.aws_kms_key.model : k.arn if k.key_manager == "CUSTOMER"]
}

resource "aws_iam_role_policy" "host" {
  role = aws_iam_role.host.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = "sts:AssumeRole", Resource = concat([aws_iam_role.audit.arn], var.member_role_arns) },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.data.arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.data.arn}/state/*" },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.data.arn}/source/*" },
    {
      # The common read role in any account of this account's own organization (none when not in an organization).
      Effect    = "Allow", Action = "sts:AssumeRole", Resource = "arn:aws:iam::*:role/${var.member_role_name}",
      Condition = { StringEquals = { "aws:ResourceOrgID" = "$${aws:PrincipalOrgID}" } }
    }],
    var.model_secret_arn == "" ? [] : [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.model_secret_arn }],
    length(local.model_kms_key_arns) == 0 ? [] : [{ Effect = "Allow", Action = "kms:Decrypt", Resource = local.model_kms_key_arns, Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.${var.region}.amazonaws.com" } } }]
  ) })
}

# Read-only audit role used by the desk for every AWS security read in this account.
resource "aws_iam_role" "audit" {
  name = "${var.name}-audit"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { AWS = aws_iam_role.host.arn }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy_attachment" "audit_read" {
  for_each   = toset(["SecurityAudit", "job-function/ViewOnlyAccess"])
  role       = aws_iam_role.audit.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_iam_role_policy" "audit_exclusions" {
  role = aws_iam_role.audit.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid = "NoCredentialsOrApplicationData", Effect = "Deny", Resource = "*",
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
