# Reused tools and optional AWS companions

CE is an integration, not a new AWS scanner or infrastructure language. Hermes
provides the agent, model selection, sessions and dashboard. The optional UI is
przbadu/hermes-ui, pinned and attributed in deploy/hermes-ui. CE adds the selected
skills, bounded execution, evidence receipts, knowledge handling and validation.

| Tool | Role in this build | Execution boundary |
| --- | --- | --- |
| Hermes Agent | Agent runtime and official dashboard | No AWS credentials; admitted CE tools |
| hermes-ui | Optional browser interface to the same Hermes profile | No model key or AWS credentials in UI container |
| boto3 / botocore | Deterministic AWS reads and input schemas | Local collector; exact dependency pins |
| Terraform, AWS CLI, cfn-lint | Check proposed fixes with real tools | Separate Linux validator; no apply permissions |
| Prowler | Optional independent posture scan | Operator runs and supplies supported report files; not installed or auto-executed |
| Cloud Custodian | Optional policy validation and resource selection | Operator reviews policy and uses validate/dryrun; not an autonomous remediation permission |

[Prowler](https://prowler.com/cloud-security-solutions/aws-security-audit) is useful
when an organization needs additional deterministic security checks. Its own
permission requirements must be reviewed; CE does not claim that every Prowler
check is covered by its current role.

[Cloud Custodian](https://cloudcustodian.io/docs/deployment.html) supplies policy
validation and dry-run support. This is a useful companion for repeatable resource
selection and reviewed policy proposals. A dry run is not approval to execute a
policy's actions. Keep action execution with the operator.

Do not install another Python environment inside Hermes for each companion tool.
Use a separately pinned tool container when adding one. Bring its report into the
supported evidence intake, preserve tool/version/time/scope, and distinguish
scanner results from organization policy. Unrecognized report formats must be
identified as unsupported, not silently claimed as normalized.

No Prowler or Cloud Custodian integration is claimed as newly live-tested by this
migration. The live tests exercise the AWS SDK collector and existing validator.
