# RDS exposure and protection (RDS.1 public snapshot, RDS.2 publicly accessible, RDS.3 encryption, RDS.5 multi-AZ, RDS.11 backups)

**Verify:** `rgtriage aws rds describe_db_instances --params '{"DBInstanceIdentifier":"<id>"}'` (PubliclyAccessible,
StorageEncrypted, VpcSecurityGroups) and `describe_db_snapshot_attributes` for public snapshots.

**Terraform (aws_db_instance / aws_rds_cluster):**
```hcl
publicly_accessible     = false
storage_encrypted       = true # existing DB: REPLACEMENT (snapshot -> encrypted copy -> restore)
kms_key_id              = aws_kms_key.db.arn
backup_retention_period = 7
deletion_protection     = true
multi_az                = true
```
**CloudFormation:** `PubliclyAccessible: false`, `StorageEncrypted: true` (replacement), `DeletionProtection: true`.

**Trade-offs:** encrypting an existing instance is a migration with downtime; plan it.
`publicly_accessible = false` applies in place but clients outside the VPC lose access.
