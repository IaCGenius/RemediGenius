# IAM and credential boundaries

## Spot

The single-compute stack creates one instance role and instance profile. Review
[its policy source](../deploy/aws-single/iam.tf) before provisioning.

| Identity | Granted access | Boundary |
| --- | --- | --- |
| EC2 host role | SecurityAudit, ViewOnlyAccess, SSM; own CE bucket read/write; attach own retained volume | Operational writes exist; not a globally read-only role |
| Local collector | Temporary instance-role credentials from IMDSv2 | SDK calls admitted by CE scope and operation checks |
| Hermes and optional UI | No AWS credentials; no metadata route from isolated Hermes network | Hermes requests bounded collection through a Unix socket |
| Validator | No customer AWS credentials | Validate proposal syntax/schema; no apply |
| Optional model secret | Exact configured secret, plus exact KMS grant when supplied | Host boot reads it; model key belongs to Hermes, not AWS evidence |

The host uses AmazonSSMManagedInstanceCore for the private tunnel. No inbound SSH
or dashboard port is opened. The user who opens a tunnel must have the appropriate
SSM permissions. A host administrator remains trusted and can access the state.

S3 contains private evidence, chat, knowledge and possibly model keys in backups.
Its evidence reader admits only evidence prefixes; a model cannot request the
state backup prefix through that reader. Protect IAM access to the whole bucket.

## Workstation

An administrator provisions the private bucket with
[workstation storage Terraform](../deploy/workstation-storage/main.tf). The module
prints a scoped storage policy for the existing operator role; it does not attach
it or create a new user. The operator's AWS profile must have the intended metadata
reads plus that storage access. Prefer short-lived SSO credentials.

Only the collector mounts the private exported credential volume. Hermes does not.
Use the launcher's `run` mode to refresh credentials. When the upstream AWS login
expires, renew it; CE cannot grant itself access. The role/SCP/resource policy and
KMS policy remain authoritative. A configured operation is not proof a read succeeds.

## Existing deployments

The earlier executor, Lambda collector, schedule and invoker roles belong to the
archived deployment. They are not created by the new stacks. Keep their Terraform
state and remove them separately when you have confirmed migration. Do not destroy
an old stack merely because its source was moved out of this CE working tree.
