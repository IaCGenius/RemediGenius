module "workspace_storage" {
  source                = "../../modules/workspace-storage"
  bucket_name           = aws_s3_bucket.fixture.id
  prefix                = "ce-workspace"
  trusted_principal_arn = var.trusted_principal_arn
  external_id           = var.external_id
  role_name             = "RemediGeniusCommunityWorkspaceTest"
}
output "workspace_storage_role" { value = module.workspace_storage.role_arn }
