resource "aws_iam_role" "host" {

  name = var.name

  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_instance_profile" "host" {
  name = var.name
  role = aws_iam_role.host.name
}
resource "aws_iam_role_policy_attachment" "read" {

  for_each = toset(["SecurityAudit", "job-function/ViewOnlyAccess"])

  role = aws_iam_role.host.name

  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_iam_role_policy_attachment" "ssm" {

  role = aws_iam_role.host.name

  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "host" {

  role = aws_iam_role.host.id

  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = "sts:AssumeRole", Resource = aws_iam_role.audit.arn },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.data.arn },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.data.arn}/*" },
    { Effect = "Allow", Action = "ec2:AttachVolume", Resource = aws_ebs_volume.sessions.arn },
    { Effect = "Allow", Action = "ec2:AttachVolume", Resource = "arn:aws:ec2:us-east-1:${var.account_id}:instance/*", Condition = { StringEquals = { "ec2:ResourceTag/Name" = var.name } } }
  ], var.model_secret_arn == "" ? [] : [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.model_secret_arn }], length(var.model_secret_kms_keys) == 0 ? [] : [{ Effect = "Allow", Action = "kms:Decrypt", Resource = var.model_secret_kms_keys, Condition = { StringEquals = { "kms:ViaService" = "secretsmanager.us-east-1.amazonaws.com", "kms:EncryptionContext:SecretARN" = var.model_secret_arn } } }]) })
}


# Investigation credentials are separate from CE storage/recovery permissions.
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
