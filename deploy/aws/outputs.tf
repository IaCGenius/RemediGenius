output "host_role_arn" {
  description = "The engine's role; every read-only role trusts exactly this ARN"
  value       = aws_iam_role.host.arn
}

output "bucket" { value = aws_s3_bucket.main.id }
output "asg_name" { value = aws_autoscaling_group.host.name }

output "set_model_key" {
  description = "Run once (reads MODEL_API_KEY from your shell; never put the key in tfvars or the repo)"
  value       = "aws secretsmanager put-secret-value --region ${var.region} --secret-id ${aws_secretsmanager_secret.model_key.name} --secret-string \"$MODEL_API_KEY\" --query VersionId --output text"
}

output "dashboard_login" {
  description = "Read once for the Hermes Desktop / dashboard sign-in"
  value       = "aws secretsmanager get-secret-value --region ${var.region} --secret-id ${aws_secretsmanager_secret.dashboard.name} --query SecretString --output text"
}

output "connect" {
  description = "Tunnel for Hermes Desktop and the dashboard (http://127.0.0.1:<port>), or a shell on the host"
  value       = "REGION=${var.region} ASG=${aws_autoscaling_group.host.name} PORT=${var.dashboard_port} ./connect.sh   # add 'shell' for a host shell"
}

output "onboarding" {
  description = "For each account in var.accounts: deploy the read-only role there with these parameters (run with that account's credentials)"
  value = {
    for k, a in var.accounts : k => join(" ", [
      "aws cloudformation deploy --stack-name ${var.name_prefix}-readonly --capabilities CAPABILITY_NAMED_IAM",
      "--template-file onboarding/aws/readonly-role.yaml --region ${var.region} --parameter-overrides",
      "ExternalId=${random_string.external_id[k].result} TrustedRoleArn=${aws_iam_role.host.arn} RoleName=${var.readonly_role_name}",
    ])
  }
}

output "kiosk_freeze" {
  description = "Stop all kiosk submissions and promotions (live functions keep running); value false to unfreeze"
  value       = var.enable_kiosk ? module.kiosk[0].freeze_command : "kiosk not enabled"
}
