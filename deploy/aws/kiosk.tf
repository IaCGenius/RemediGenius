# Optional (enable_kiosk = true): the lambda kiosk. The builder agent writes small Python functions with tests;
# only the kiosk's gate can deploy them (static checks, tests in a sandbox with no network, code signing,
# canary, auto-rollback, daily caps, a freeze switch). The builder gets 1-hour credentials for its own kiosk
# role from the host; it cannot create, update or invoke functions, or touch IAM, itself.
#
# Build the kiosk's zips before every plan: python modules/lambda-kiosk/build.py   (needs uv)

resource "aws_vpc_ipv4_cidr_block_association" "sandbox" {
  count      = var.enable_kiosk ? 1 : 0
  vpc_id     = aws_vpc.main.id
  cidr_block = var.kiosk_sandbox_cidr
}

resource "aws_subnet" "sandbox" { # a subnet with no route out
  count                   = var.enable_kiosk ? 1 : 0
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.kiosk_sandbox_cidr
  availability_zone       = local.az
  map_public_ip_on_launch = false
  tags                    = { Name = "kiosk-${var.name_prefix}-sandbox" }
  depends_on              = [aws_vpc_ipv4_cidr_block_association.sandbox]
}

resource "aws_route_table" "sandbox" { # local route only: nothing leaves the VPC
  count  = var.enable_kiosk ? 1 : 0
  vpc_id = aws_vpc.main.id
  tags   = { Name = "kiosk-${var.name_prefix}-sandbox" }
}

resource "aws_route_table_association" "sandbox" {
  count          = var.enable_kiosk ? 1 : 0
  subnet_id      = aws_subnet.sandbox[0].id
  route_table_id = aws_route_table.sandbox[0].id
}

resource "aws_security_group" "sandbox" { # no ingress, no egress (Terraform removes the default egress rule)
  count       = var.enable_kiosk ? 1 : 0
  name        = "kiosk-${var.name_prefix}-sandbox"
  description = "Kiosk sandbox: no traffic in or out"
  vpc_id      = aws_vpc.main.id
}

module "kiosk" {
  count      = var.enable_kiosk ? 1 : 0
  source     = "../../modules/lambda-kiosk"
  name       = var.name_prefix
  account_id = var.account_id
  region     = var.region
  agents = {
    builder = {
      trusted_principal_arns = [aws_iam_role.host.arn]
      classes                = ["isolated", "processor"]
      promotion_policy       = "auto"
    }
  }
  sandbox_subnet_ids         = [aws_subnet.sandbox[0].id]
  sandbox_security_group_ids = [aws_security_group.sandbox[0].id]
  alert_email                = var.alert_email
  force_destroy              = var.destroy_data_on_teardown
}
