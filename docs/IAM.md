# Permissions and credential boundaries — RemediGenius Community Edition

The rule in every deployment: **only the desk service holds AWS credentials, and every AWS call it makes is a read.**
The Hermes agent never holds AWS credentials.

## Read-only enforcement (all deployments)

1. **Code:** every boto3 session the desk creates carries a `before-call` hook that refuses any operation that is not
   Describe/Get/List/BatchGet/Lookup/Search or a policy evaluation (IAM `SimulatePrincipalPolicy`/`SimulateCustomPolicy`,
   Access Analyzer `CheckNoPublicAccess`/`CheckAccessNotGranted`/`CheckNoNewAccess`/`ValidatePolicy`, which return a
   verdict and change nothing), and also refuses reads that return secrets or data (`GetSecretValue`,
   `GetParameter*`, `GetObject`, `Decrypt`, DynamoDB item reads, log event reads, `GetFunction`, …). This applies even
   when the underlying credentials could write.
2. **IAM:** the deployments read through a role with `SecurityAudit` + `ViewOnlyAccess`, an allow for the policy
   evaluations above (`EvaluatePoliciesWithoutChanges`) and an explicit deny on credential and data reads. The agent's
   AWS reads also refuse calls that return credentials (`AssumeRole*`, `GetSessionToken`, `GetFederationToken`).
3. **Agent surface:** the agent can only send the desk a fixed list of triage commands over a Unix socket. It has no
   shell, cannot read credential files, and can write only to its proposals folder.

## Spot ([iam.tf](../deploy/aws-single/iam.tf))

| Identity | Permissions | Used by |
| --- | --- | --- |
| Instance role `<name>` | SSM core; its bucket (`state/` read/write, `source/` read, `raw/` and `warehouse/` read/write/delete); the Glue database `<name>` and its tables; the model secret, plus `kms:Decrypt` on that secret's customer-managed key via Secrets Manager only; `sts:AssumeRole` on the audit role, plus `RemediGeniusReadOnly` in any account of its own organization (`aws:ResourceOrgID` = `${aws:PrincipalOrgID}`; nothing when not in an organization) or explicit `member_role_arns` | the host bootstrap and desk service (raw evidence, Iceberg facts, checkpoints, secret, role assumption) |
| Audit role `<name>-audit` | `SecurityAudit`, `ViewOnlyAccess`, policy evaluations (IAM simulator, Access Analyzer checks), explicit deny on credential/data reads | every AWS read in this account |
| Member read role `RemediGeniusReadOnly` ([template](../deploy/aws-single/member-read-role.yaml), deploy as a StackSet) | same as the audit role; trusts only the desk identity (`TrustedPrincipalArn`) within your organization | AWS reads in member accounts; see [MULTI-ACCOUNT.md](MULTI-ACCOUNT.md) |
| Hermes container | none. IMDSv2 hop limit 1 and the egress firewall block instance metadata | — |

The instance role itself has no AWS security read permissions. No inbound port is open; operators reach the dashboard
through SSM port forwarding, which needs `ssm:StartSession` on the instance.

The S3 bucket holds raw AWS responses, the Iceberg warehouse and Hermes home checkpoints, which may include the model
key. Restrict access to the whole bucket. The instance role's Glue grant names only the `<name>` database, its table
prefix and the catalog ARN; it cannot read or change another Glue database. The desk's Iceberg writes are the only
writes in that scope; collection in target accounts stays read-only through the audit and member roles.

## Docker workstation

| Identity | Permissions | Used by |
| --- | --- | --- |
| `--read-role-arn` role (recommended) | `SecurityAudit` + `ViewOnlyAccess`, ideally with the same denies as the audit role | assumed by `tools/workstation.py`; temporary credentials go only to the desk container |
| your AWS profile (no role given) | whatever the profile has | copied into the desk container's credential volume; the botocore guard still blocks writes |
| Hermes container | none | — |

## Existing Hermes ([LOCAL-HERMES.md](LOCAL-HERMES.md))

The desk runs as a subprocess of Hermes using your AWS profile. The botocore guard and the agent's guards apply, but
there is no process separation. Use a read-only profile.
