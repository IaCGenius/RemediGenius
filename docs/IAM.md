# Permissions and credential boundaries — RemediGenius Community Edition

The rule in every deployment: **only the desk service holds AWS credentials, and every AWS call it makes is a read.**
The Hermes agent never holds AWS credentials.

## Read-only enforcement (all deployments)

1. **Code:** every boto3 session the desk creates carries a `before-call` hook that refuses any operation that is not
   Describe/Get/List/BatchGet/Lookup/Search, and also refuses reads that return secrets or data (`GetSecretValue`,
   `GetParameter*`, `GetObject`, `Decrypt`, DynamoDB item reads, log event reads, `GetFunction`, …). This applies even
   when the underlying credentials could write.
2. **IAM:** the deployments read through a role with `SecurityAudit` + `ViewOnlyAccess` and an explicit deny on
   credential and data reads.
3. **Agent surface:** the agent can only send the desk a fixed list of triage commands over a Unix socket. It has no
   shell, cannot read credential files, and can write only to its proposals folder.

## Spot ([iam.tf](../deploy/aws-single/iam.tf))

| Identity | Permissions | Used by |
| --- | --- | --- |
| Instance role `<name>` | SSM core; its bucket (`state/` read/write, `source/` read); the model secret, plus `kms:Decrypt` on that secret's customer-managed key via Secrets Manager only; `sts:AssumeRole` on the audit role, plus `RemediGeniusReadOnly` in any account of your organization (`organization_id`, conditioned on `aws:ResourceOrgID`) or explicit `member_role_arns` | the host bootstrap and desk service (state, secret, role assumption) |
| Audit role `<name>-audit` | `SecurityAudit`, `ViewOnlyAccess`, explicit deny on credential/data reads | every AWS read in this account |
| Member read role `RemediGeniusReadOnly` ([template](../deploy/aws-single/member-read-role.yaml), deploy as a StackSet) | same as the audit role; trusts only the instance role within your organization | AWS reads in member accounts; see [MULTI-ACCOUNT.md](MULTI-ACCOUNT.md) |
| Hermes container | none. IMDSv2 hop limit 1 and the egress firewall block instance metadata | — |

The instance role itself has no AWS security read permissions. No inbound port is open; operators reach the dashboard
through SSM port forwarding, which needs `ssm:StartSession` on the instance.

The S3 bucket holds checkpoints of conversations, decisions and settings, which may include the model key.
Restrict access to the whole bucket.

## Docker workstation

| Identity | Permissions | Used by |
| --- | --- | --- |
| `--read-role-arn` role (recommended) | `SecurityAudit` + `ViewOnlyAccess`, ideally with the same denies as the audit role | assumed by `tools/workstation.py`; temporary credentials go only to the desk container |
| your AWS profile (no role given) | whatever the profile has | copied into the desk container's credential volume; the botocore guard still blocks writes |
| Hermes container | none | — |

## Existing Hermes ([LOCAL-HERMES.md](LOCAL-HERMES.md))

The desk runs as a subprocess of Hermes using your AWS profile. The botocore guard and the agent's guards apply, but
there is no process separation. Use a read-only profile.
