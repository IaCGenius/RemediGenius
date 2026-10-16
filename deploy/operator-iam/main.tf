terraform {
  required_version = ">= 1.10"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.80" } }
}
variable "account_id" { type = string }
variable "region" { type = string }
variable "stack_names" { type = list(string) }
variable "bucket_names" { type = list(string) }
variable "model_secret_arns" { type = list(string) }
variable "name" { default = "ce-operator" }
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = "remedigenius-ce", Stack = var.name, ManagedBy = "terraform", CEVersion = "0.1.2" } }
}
data "aws_partition" "current" {}
locals {
  arn      = "arn:${data.aws_partition.current.partition}"
  roles    = [for n in var.stack_names : "${local.arn}:iam::${var.account_id}:role/${n}*"]
  profiles = [for n in var.stack_names : "${local.arn}:iam::${var.account_id}:instance-profile/${n}*"]
  buckets  = flatten([for b in var.bucket_names : ["${local.arn}:s3:::${b}", "${local.arn}:s3:::${b}/*"]])
  secrets  = concat(var.model_secret_arns, [for n in var.stack_names : "${local.arn}:secretsmanager:${var.region}:${var.account_id}:secret:${n}/dashboard-*"])
  daily = { Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sts:AssumeRole"], Resource = [for n in var.stack_names : "${local.arn}:iam::${var.account_id}:role/${n}-invoker"] },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = local.secrets },
    { Effect = "Allow", Action = ["autoscaling:DescribeAutoScalingGroups", "ec2:DescribeInstances", "ssm:DescribeInstanceInformation"], Resource = "*" },
    { Effect = "Allow", Action = "ssm:StartSession", Resource = "${local.arn}:ec2:${var.region}:${var.account_id}:instance/*", Condition = { StringEquals = { "ssm:resourceTag/Project" = "remedigenius-ce", "ssm:resourceTag/Stack" = var.stack_names } } },
    { Effect = "Allow", Action = "ssm:StartSession", Resource = "${local.arn}:ssm:${var.region}::document/AWS-StartPortForwardingSession" },
    { Effect = "Allow", Action = ["ssm:TerminateSession", "ssm:ResumeSession"], Resource = "${local.arn}:ssm:${var.region}:${var.account_id}:session/$${aws:userid}-*" }
  ] }
  provision = { Version = "2012-10-17", Statement = concat(local.daily.Statement, [
    { Effect = "Allow", Action = ["iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateAssumeRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:TagRole", "iam:UntagRole", "iam:ListInstanceProfilesForRole"], Resource = local.roles },
    { Effect = "Allow", Action = ["iam:CreateInstanceProfile", "iam:DeleteInstanceProfile", "iam:GetInstanceProfile", "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile", "iam:TagInstanceProfile", "iam:UntagInstanceProfile"], Resource = local.profiles },
    { Effect = "Allow", Action = "iam:PassRole", Resource = local.roles, Condition = { StringEquals = { "iam:PassedToService" = ["ec2.amazonaws.com", "lambda.amazonaws.com", "scheduler.amazonaws.com"] } } },
    { Effect = "Allow", Action = ["s3:CreateBucket", "s3:DeleteBucket", "s3:DeleteBucketPolicy", "s3:Get*", "s3:List*", "s3:PutBucket*", "s3:PutEncryptionConfiguration", "s3:PutLifecycleConfiguration", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion"], Resource = local.buckets },
    { Effect = "Allow", Action = ["lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration", "lambda:GetFunctionCodeSigningConfig", "lambda:GetFunctionConcurrency", "lambda:PutFunctionEventInvokeConfig", "lambda:GetFunctionEventInvokeConfig", "lambda:DeleteFunctionEventInvokeConfig", "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency", "lambda:ListVersionsByFunction", "lambda:ListTags", "lambda:TagResource", "lambda:UntagResource", "lambda:InvokeFunction"], Resource = [for n in var.stack_names : "${local.arn}:lambda:${var.region}:${var.account_id}:function:${n}*"] },
    { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy", "logs:ListTagsLogGroup", "logs:ListTagsForResource", "logs:TagResource", "logs:UntagResource", "logs:TagLogGroup", "logs:UntagLogGroup"], Resource = [for n in var.stack_names : "${local.arn}:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${n}*"] },
    { Effect = "Allow", Action = "logs:DescribeLogGroups", Resource = "*" },
    { Effect = "Allow", Action = ["scheduler:CreateSchedule", "scheduler:UpdateSchedule", "scheduler:GetSchedule", "scheduler:DeleteSchedule"], Resource = [for n in var.stack_names : "${local.arn}:scheduler:${var.region}:${var.account_id}:schedule/default/${n}*"] },
    { Effect = "Allow", Action = ["secretsmanager:CreateSecret", "secretsmanager:DeleteSecret", "secretsmanager:RestoreSecret", "secretsmanager:DescribeSecret", "secretsmanager:PutSecretValue", "secretsmanager:UpdateSecretVersionStage", "secretsmanager:TagResource", "secretsmanager:UntagResource", "secretsmanager:GetResourcePolicy"], Resource = [for n in var.stack_names : "${local.arn}:secretsmanager:${var.region}:${var.account_id}:secret:${n}/dashboard-*"] },
    { Effect = "Allow", Action = ["ec2:Describe*", "ec2:CreateTags", "ec2:DeleteTags", "ec2:CreateVolume", "ec2:DeleteVolume", "ec2:ModifyVolume", "ec2:CreateSnapshot", "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup", "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupEgress", "ec2:CreateLaunchTemplate", "ec2:CreateLaunchTemplateVersion", "ec2:DeleteLaunchTemplate", "ec2:DeleteLaunchTemplateVersions", "ec2:ModifyLaunchTemplate", "ec2:RunInstances", "ec2:TerminateInstances", "autoscaling:CreateAutoScalingGroup", "autoscaling:UpdateAutoScalingGroup", "autoscaling:DeleteAutoScalingGroup", "autoscaling:Describe*", "autoscaling:CreateOrUpdateTags", "autoscaling:DeleteTags", "autoscaling:StartInstanceRefresh"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.region } } },
    { Effect = "Allow", Action = "ssm:GetParameter", Resource = "${local.arn}:ssm:${var.region}::parameter/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64" }
  ]) }
}
output "provision_json" { value = jsonencode(local.provision) }
output "daily_use_json" { value = jsonencode(local.daily) }
