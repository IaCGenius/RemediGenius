# IAM definitions; resource addresses retained.

resource "aws_iam_role" "read" {
  name = "RemediGeniusCommunityReadOnly"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { AWS = concat([var.trusted_principal_arn], var.additional_principal_arns) }, Action = "sts:AssumeRole", Condition = { StringEquals = { "sts:ExternalId" = var.external_id } } }]
  })
  tags = { Project = "remedigenius-community", Purpose = "operator-initiated-read" }
}

resource "aws_iam_role_policy" "read" {
  name   = "SelectedCommunitySources"
  role   = aws_iam_role.read.id
  policy = jsonencode(local.read_policy)
}

data "aws_partition" "current" {}

resource "aws_iam_role_policy_attachment" "inventory" {
  for_each   = toset(["SecurityAudit", "job-function/ViewOnlyAccess"])
  role       = aws_iam_role.read.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/${each.value}"
}
