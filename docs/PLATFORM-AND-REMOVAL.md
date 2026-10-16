# Platform, state, costs and removal

## Platform contract

Release operator baseline: **Bash on Ubuntu 24.04 LTS**, native or WSL2. PowerShell
helpers remain secondary. macOS Bash-compatible commands are not a tested macOS
release claim; community reports can qualify them separately.

| CE controls | Operator controls |
|---|---|
| Official pinned Hermes container and its Debian userspace | Ubuntu/WSL installation, Bash, Docker, Python, Terraform and AWS CLI |
| Linux validator and pinned toolchain | Model account/key, AWS profile, IAM, network and storage inputs |
| Amazon Linux 2023 Spot host | Existing subnet, routing and private evidence bucket |
| Python 3.12 Lambda collectors | Permissions, retention and schedules |

Use Python 3.12, Terraform >=1.10, AWS CLI v2, Docker with Linux containers and the
Linux Session Manager plugin. The exact validator pins are separate from host
prerequisites: see [toolchain](REMEDIATION-VALIDATION.md). Proposed commands are
Bash/Linux; run them in Bash, not by pasting them into PowerShell. An equivalent
Bash environment such as CloudShell still needs your intended credentials/tools.

## State is private and durable

Without an optional backend, Terraform stores `terraform.tfstate` inside the
stack directory. Spot state includes the dashboard login. Back up state privately;
losing it loses the straightforward resource inventory and destroy path.
Each stack supplies `backend.tf.example`: copy to `backend.tf`, use a separate
pre-existing S3 state bucket, then `terraform init -migrate-state` for existing
state. Review migration and keep a backup. `use_lockfile=true` needs Terraform
1.10+ and the appropriate S3 state/lock object permissions. Never put state in Git.

## Tags and billable resources

Stack providers apply `Project=remedigenius-ce`, `Stack=<name>`,
`ManagedBy=terraform`, `CEVersion=0.1.3` to taggable resources. Launch-template root
volumes receive tags too. Not every AWS resource supports the Tagging API.

```bash
aws resourcegroupstaggingapi get-resources --region us-east-1 \
  --tag-filters Key=Project,Values=remedigenius-ce
```

CE can answer the same bounded inventory question through its read executor.
This is tagged-resource inventory, not a bill or an exhaustive inventory. For
costs, activate Project as a cost-allocation tag in the payer account and filter
Cost Explorer; activation applies going forward. No billing API is exposed to CE.

Budget for Spot EC2, 20 GiB session EBS and 24 GiB root gp3 EBS, snapshots, S3
storage/requests/old versions, Lambda, CloudWatch Logs, EventBridge Scheduler,
Secrets Manager, optional public IPv4, subnet NAT costs, and model tokens including
critique and the one-call startup probe. Stopping compute does not stop these
other charges. A NAT gateway is existing infrastructure, not created by CE.

## Remove workstation deployment

Stop the launcher first, then run from the repository root with the same inputs:

```bash
python tools/native_workstation.py stop --config .rgce/workstation.json
terraform -chdir=deploy/aws-workstation destroy -var-file="$(realpath .rgce/workstation.tfvars)"
```

Default `delete_evidence_on_destroy=false` refuses deletion of a non-empty bucket.
Destroy is not atomic: other resources may already have been deleted when it
stops at the bucket. Back up wanted evidence first. To delete all objects and
versions, deliberately set the variable true, apply it, then destroy. This is
irreversible; do not use it just to stop compute.

## Remove Spot deployment

First set running=false and apply with the same private var-file; wait for the
instance to terminate and the session volume to detach, so the final snapshot is
consistent. Then:

```bash
terraform -chdir=deploy/aws-native destroy -var-file="$(realpath .rgce/aws.tfvars.json)"
```

The session volume is deleted after a final snapshot. That snapshot persists and
costs money; retain its ID and test restoration before relying on it. Your existing
S3 bucket, CE objects/source ZIP and model secret remain. Dashboard-secret recovery
defaults to 7 days, preventing immediate reuse of the same name. Set
`dashboard_recovery_days=0` only when you deliberately want immediate, unrecoverable
deletion. The default is recoverable deletion.

For both paths, remove separately deployed member read-role CloudFormation stacks
in their accounts. Existing networks/NAT and any remote-state bucket remain.

## Docker leftovers

After stopping CE, inspect and remove only your selected resources if no longer
wanted: container `<name>`, validator `<name>-validator`, named volume `<name>-data`,
internal network `<name>-validation`, and `remedigenius-validator:*` images. Deleting
the volume loses sessions/cases; keep it for a later restart. Avoid blanket Docker
prune commands on a shared workstation.
