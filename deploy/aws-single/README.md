# RemediGenius Community Edition on one AWS Spot instance

A persistent RemediGenius-CE deployment in your account: one Spot instance in an Auto Scaling group and a private S3
bucket for durable state. The instance is disposable. If AWS reclaims it, the group launches a new one and it restores
itself from S3.

```mermaid
flowchart LR
  subgraph Instance[Spot instance - disposable]
    D[remedigenius-desk.service<br/>uid 10000, read-only AWS via audit role]
    H[Hermes container<br/>profile remedigenius<br/>no AWS credentials, egress: HTTPS only]
    D -- /run/rgtriage/rgtriage.sock --> H
  end
  D -- checkpoints every 2 min, after scans/decisions,<br/>on stop and on Spot interruption notice --> S[(Private S3 bucket<br/>state/)]
  S -- restore at boot --> D
  You -- SSM port forward --> H
```

## Before you begin

- Terraform ≥ 1.10, AWS CLI v2 with the Session Manager plugin, Python 3.11+
- A provisioning identity that can create IAM roles, an S3 bucket, a security group, a launch template and an
  Auto Scaling group. It is used only for `terraform apply`; it never reaches the instance.
- An existing subnet with outbound HTTPS (public with an internet gateway, or private with NAT). No inbound port is opened.
- Your model API key stored in Secrets Manager as a plain string. A customer-managed KMS key on the secret is detected
  and granted automatically.

## Deploy

```sh
git clone https://github.com/IaCGenius/RemediGenius.git && cd RemediGenius
python tools/package_release.py --spot dist/remedigenius-ce-spot.zip
cd deploy/aws-single
cp example.tfvars local.tfvars          # set account_id, subnet_id, source_zip, model_* (see below)
terraform init
terraform plan -var-file=local.tfvars
terraform apply -var-file=local.tfvars
```

| Variable | Default | Notes |
| --- | --- | --- |
| `account_id`, `subnet_id`, `source_zip` | required | `source_zip` = the archive built above |
| `name` | `remedigenius-ce` | stack, role and Auto Scaling group name |
| `model_secret_arn` | `""` | secret holding only the model key; without it, configure the model in the dashboard |
| `model_name` / `model_base_url` | `deepseek-v4.1-flash` / `""` | OpenAI-compatible endpoint; required with a secret |
| `regions` | `[]` (= `region`) | regions the desk reads |
| `scan_interval_hours` | `6` | background scans and new-P1/P2 alerts |
| `watch_deliver` | `local` | Hermes delivery target for alerts (`local`, or a messaging channel configured in Hermes); `""` = none |
| `running` | `true` | `false` scales to zero; state stays in S3 |
| `spot_instance_types` / `container_memory_mb` | `t3.large, t3a.large` / `6144` | |
| `public_ip` | `true` | `false` for a private subnet with NAT |
| `delete_data_on_destroy` | `false` | `true` lets `terraform destroy` delete the bucket and all checkpoints |

First boot takes about 5 minutes: packages, the pinned Hermes image, the desk runtime and a pinned, checksum-verified
Terraform binary for fix validation.

## Open the dashboard

```sh
bash tools/open-remedigenius.sh --with-login          # PowerShell: tools\open-remedigenius.ps1 -WithLogin
```

This prints the private login (from `/data/hermes/remedigenius-login.json`) and opens an SSM port-forward to
`http://127.0.0.1:9125/chat?profile=remedigenius`. Keep the window open; say "hi".

## What the stack creates

- **S3 bucket** (private, versioned, TLS-only, SSE-S3). `state/` holds checkpoints (old versions expire after 30 days);
  `source/` holds the archive the instance verifies by SHA-256 at boot.
- **Instance role** with SSM core, its bucket, the model secret (+ KMS decrypt via Secrets Manager), and `sts:AssumeRole`
  on the audit role and any `member_role_arns`. It does **not** have AWS security read permissions itself.
- **Audit role** with `SecurityAudit` + `ViewOnlyAccess` and an explicit deny on credential and data reads (secrets,
  parameters, S3/DynamoDB object data, KMS decrypt). Every AWS read the desk makes uses this role.
- Security group with no inbound rules; IMDSv2 with hop limit 1, so containers cannot reach instance metadata.
- Launch template and Auto Scaling group (min 0, max 1, Spot only, price-capacity-optimized).

## On the instance

| Unit | Role |
| --- | --- |
| `remedigenius-desk.service` | `rgtriage serve` as uid 10000 with systemd sandboxing; Unix socket API; S3 checkpoints; Spot interruption watcher |
| `remedigenius-scan.timer` | scheduled scan (3 minutes after boot, then every `scan_interval_hours`) |
| `remedigenius-hermes.service` | the pinned Hermes container: profile `remedigenius`, dashboard on `127.0.0.1:9120`, egress limited to HTTPS (no metadata, no private ranges) |

Desk state is in `/data/rgtriage`, the Hermes home in `/data/hermes`, and proposals the agent saves in `/opt/data/proposals`
(inside the Hermes home). IaC repositories go in `/data/iac` (clone them through an SSM session), mounted
read-only into the agent. Logs: `journalctl -u remedigenius-desk -u remedigenius-scan -u remedigenius-hermes`.

## Member accounts

See [docs/MULTI-ACCOUNT.md](../../docs/MULTI-ACCOUNT.md). In short: run the stack in your security tooling (delegated
administrator) account with `delegated_admin = true`, deploy [`member-read-role.yaml`](member-read-role.yaml) to every
member account as a service-managed StackSet, and set `organization_id` and `member_account_ids`. The instance role can
assume `RemediGeniusReadOnly` only inside your organization.

| Variable | Default | Notes |
| --- | --- | --- |
| `delegated_admin` | `false` | this account's Security Hub/GuardDuty/Inspector view is org-wide |
| `organization_id` | `""` | enables the org-scoped `sts:AssumeRole` on `member_role_name` |
| `member_role_name` | `RemediGeniusReadOnly` | role name deployed in every member account |
| `member_account_ids` | `[]` | added to `triage.yaml` at boot (append only) |
| `member_role_arns` | `[]` | explicit role ARNs (no organization) |

## Stop, start, remove

- Stop: `running = false` and apply (scale to zero). Start: `running = true`. State comes back from S3.
- Interruptions: Spot gives a two-minute notice. The desk saves state immediately; at most the last few minutes of
  activity can be lost.
- Remove: `terraform destroy`. The bucket is kept unless `delete_data_on_destroy = true`.
