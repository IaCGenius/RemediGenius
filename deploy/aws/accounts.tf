# The accounts the collector reads. Each gets one read-only role (onboarding/aws/readonly-role.yaml: AWS
# ViewOnlyAccess + SecurityAudit, then an explicit deny on 167 data-read actions) and one secret that tells
# the collector which role to assume, with which ExternalId, in which regions.
#
# This account ("self") gets the role here, from the same template. Other accounts: you deploy the template
# there yourself with the parameters from the `onboarding` output (Terraform here never touches them).

# ExternalId is not a secret (AWS guidance), so a plain random string that outputs may show.
resource "random_string" "external_id" {
  for_each = toset(concat(["self"], keys(var.accounts)))
  length   = 40
  special  = false
}

resource "aws_cloudformation_stack" "readonly_self" {
  name          = "${var.name_prefix}-readonly-self"
  template_body = file("${local.root}/onboarding/aws/readonly-role.yaml")
  capabilities  = ["CAPABILITY_NAMED_IAM"]
  parameters = {
    ExternalId     = random_string.external_id["self"].result
    TrustedRoleArn = aws_iam_role.host.arn
    RoleName       = var.readonly_role_name
  }
}

locals {
  connected = merge(
    { self = { account_id = var.account_id, regions = var.self_regions } },
    var.accounts,
  )
}

resource "aws_secretsmanager_secret" "account" {
  for_each                = local.connected
  name                    = "${var.name_prefix}/hermes/tenant/${each.key}"
  description             = "Collector target ${each.key}: read-only role, ExternalId, regions."
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = var.secret_recovery_days
}

resource "aws_secretsmanager_secret_version" "account" {
  for_each  = local.connected
  secret_id = aws_secretsmanager_secret.account[each.key].id
  secret_string = jsonencode({
    tenant      = each.key
    account     = each.value.account_id
    role_arn    = "arn:aws:iam::${each.value.account_id}:role/${var.readonly_role_name}"
    external_id = random_string.external_id[each.key].result
    regions     = each.value.regions
  })
}
