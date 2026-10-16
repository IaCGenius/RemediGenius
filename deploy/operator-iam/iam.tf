# Administrator applies and explicitly attaches these policies to operator identities.
resource "aws_iam_policy" "provision" {
  name   = "${var.name}-provision"
  policy = jsonencode(local.provision)
}
resource "aws_iam_policy" "daily" {
  name   = "${var.name}-daily"
  policy = jsonencode(local.daily)
}
output "provision_policy_arn" { value = aws_iam_policy.provision.arn }
output "daily_use_policy_arn" { value = aws_iam_policy.daily.arn }
