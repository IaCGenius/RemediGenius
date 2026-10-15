# Native Hermes on your workstation

This runs the official pinned Hermes container and the CE profile locally. AWS
Lambda performs bounded collection; S3 retains evidence; EventBridge runs daily
deterministic checks even when your workstation is off. This is a hybrid deployment,
not an offline edition. AWS and model usage are charged to your accounts.

The older root `compose.yaml` starts the legacy console, not this experience.

The launcher checks the pinned upstream dashboard source and mounts a small CE
session-limit overlay: two live terminals and ten minutes for detached terminals.
Hermes's own cleanup preserves saved conversations in the Docker volume. Finish
an active run before starting another chat. The overlay must be reviewed when
updating the official image; a changed source hash stops preparation explicitly.

## Prepare the AWS backend

Prerequisites: Docker with Linux containers, Python 3.11 or later with boto3,
Terraform 1.10 or later, and an authenticated AWS operator profile. The operator
needs provisioning permissions for S3, IAM, Lambda, logs and EventBridge Scheduler.
These operator credentials stay on the workstation and are not mounted in Hermes.

1. Copy `deploy/aws-workstation/terraform.tfvars.example` to a private `.tfvars`
   file. Set your account, region and exact operator IAM user/role ARN. For an SSO
   or assumed-role session, use its IAM role ARN, not its STS session ARN.
2. Initialize and inspect the plan, then apply it:

```powershell
terraform -chdir=deploy/aws-workstation init
terraform -chdir=deploy/aws-workstation plan -var-file=YOUR_PRIVATE_INPUTS.tfvars
terraform -chdir=deploy/aws-workstation apply -var-file=YOUR_PRIVATE_INPUTS.tfvars
terraform -chdir=deploy/aws-workstation output -json workstation_backend
```

Use an absolute path for your inputs. The stack creates a private, encrypted,
versioned bucket, scoped roles, a collector and a daily schedule. It creates no
EC2 instance or VPC. Preserve Terraform state securely. Evidence has a destruction
guard; removing the installation must be a deliberate storage-retention decision.

Default checks collect bounded Security Hub ACTIVE findings and Config recorder
configuration for the first configured target (alphabetically) and its first region.
Set `schedule_checks` to choose one to four explicit collector requests; additional
interactive targets are not silently included in scheduled coverage. Unavailable services are reported
as unavailable, not healthy. This is not an exhaustive daily scan. Configure
`schedule_interval_hours` (1–168, default 24), or `schedule_enabled=false`.
Multi-account targets use the same explicit trust and region configuration as
[AWS execution](AWS-READ-EXECUTION.md); accounts are not enrolled automatically.

## Start Hermes

Copy `deploy/aws-workstation/workstation.example.json` into `.rgce/` and fill its
backend fields from Terraform output. Set your AWS profile and Hermes-compatible
model/base URL. Supply the model key through the named environment variable, or
set `model_secret_arn` to a Secrets Manager secret containing the raw API key.
Never commit keys or private deployment configuration.

```powershell
python -m pip install boto3
python tools/native_workstation.py run --config .rgce/workstation.json
```

Keep that terminal open: it refreshes the narrowly scoped reader credentials every
20 minutes. Ctrl+C stops the local container. A refresh failure stops it rather
than leaving a misleading connected session. AWS schedules remain active.
`start` is an alternative for short tests, but its reader credentials expire after
one hour unless you run `refresh` yourself.

Open `http://127.0.0.1:9125/chat?profile=ce-desk`. In another terminal, explicitly
retrieve your locally generated login:

```powershell
python tools/native_workstation.py login --config .rgce/workstation.json
python tools/native_workstation.py stop --config .rgce/workstation.json
```

Ask: “Collect current Config recorder configuration. Show the account, region,
observation time, source receipt and missing coverage.” Then ask about Security
Hub findings, prepare a fix and save a follow-up case. No customer-cloud remediation
is executed. Generated CLI/Terraform/CloudFormation remains a reviewable proposal.

## Storage and trust

- S3: source records, normalized records, receipts and scheduled comparisons.
- Named Docker volume `<name>-data`: Hermes configuration, conversations and Kanban.
  Container replacement retains it; deleting the volume loses that local history.
  S3 evidence does not automatically reconstruct conversations or cases.
- `.rgce/workstation/<name>`: private login, temporary scoped AWS credentials and
  launch material. The launcher removes its model environment file on normal stop.
- Optional `knowledge_dir`: an exported knowledge view containing `index.md`,
  mounted read-only. Supply the selected view rather than your entire document store.

Back up the named volume while the container is stopped using your Docker volume
backup procedure. Preserve it alongside S3 evidence and deployment configuration.
Do not run two writers against the same volume.

The verified recovery method is: stop Hermes, archive its named volume, create a
new empty volume, mount that destination at `/opt/data` with `volume-nocopy`, and
restore your own trusted archive preserving ownership and symlinks. Hermes uses
absolute links under `/opt/data`; generic safe-document extractors reject them.
Never extract an untrusted archive this way. Start the recovered volume under a
new `rgce-...` name/port using matching backend/model settings, then verify login,
prior conversations and runtime integrity before switching over. Keep the original
volume until that verification succeeds. Backups contain private conversations and
configuration and need the same protection as the live volume.

The local machine and Docker administrator are trusted. The container receives
the model key and temporary collector-invocation/evidence-read credentials; it
does not receive the operator AWS profile, host repository or Docker socket.
Its networking is ordinary Docker networking, not the cloud host's network rules.
Do not treat local Docker as a hostile multi-tenant sandbox.

Normal restarts preserve the active profile. If packaged CE source changes, the
launcher requires `--upgrade`; review it and back up the volume first. The existing
upgrader retains profile backups. Model changes for an existing installation use
Hermes configuration; launcher model fields seed a new profile. Model choice stays
configurable through Hermes.
