output "bucket" { value = aws_s3_bucket.kiosk.id }
output "config_parameter" { value = aws_ssm_parameter.config.name }
output "frozen_parameter" { value = aws_ssm_parameter.frozen.name }
output "agent_role_arns" { value = { for a, r in aws_iam_role.agent : a => r.arn } }
output "state_machines" { value = { for m, s in aws_sfn_state_machine.m : m => s.arn } }
output "alert_topic" { value = aws_sns_topic.alerts.arn }
output "freeze_command" {
  description = "Admin: stop all submissions and promotions (runs keep using live versions)"
  value       = "aws ssm put-parameter --region ${var.region} --name ${aws_ssm_parameter.frozen.name} --value true --overwrite"
}
