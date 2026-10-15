# The read-only role

`readonly-role.yaml` creates one IAM role in an AWS account so the engine can assess it. The same template is used for
the account the engine runs in (Terraform deploys it) and for every other account you connect (you deploy it there).

**It can see how the account is configured:**
- IAM users, roles and policies;
- security groups and network settings;
- S3 bucket settings, not the files in them;
- logging settings;
- findings your security services already produced.

AWS defines this access in its own read-only policies, `ViewOnlyAccess` and `SecurityAudit`.

**It cannot read your data.** An explicit deny (`NeverReadClientData`, 167 actions) blocks it even where the AWS
policies would allow it:
- S3 objects and object listings;
- DynamoDB items;
- secrets, parameters and decryption;
- logs and query results;
- code, images and console output;
- messages, documents and media.

**It cannot change anything.** It has no write actions.

**Only your engine can use it.** The trust policy requires the engine's host role (`aws:PrincipalArn`) and the
ExternalId Terraform generated for this account. Sessions last at most one hour.

## Deploy in another account

Run the command from `terraform output onboarding` with that account's credentials, or use the console: CloudFormation,
create stack, upload this file, and enter `ExternalId` and `TrustedRoleArn` from that output.

## Remove

Delete the stack. The engine then reports that account's checks as ERROR (assume-role denied) until you remove it from
`accounts` in Terraform.

The deny list comes from the RemediGenius client role 1.0.0, which was reviewed action by action against the AWS
service authorization reference.
