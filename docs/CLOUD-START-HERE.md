# RemediGenius CE __VERSION__: cloud preview

**Historical integrated-console bundle template.** For the current native Hermes
preview, start at [START-HERE](../START-HERE.md) and the
[native AWS guide](NATIVE-CE-QUICKSTART.md). The older deployment below is retained
for historical artifacts, not the current release entry point.

This is the cloud-first Community Edition: the workspace **and its real Hermes investigation runtime** deploy together to your own AWS account. It is separate from the workstation preview and from RemediGenius v2. Start with a sample assessment, select evidence, review the model destination and consent, then ask Hermes to investigate directly in the workspace. No manual investigation ZIP handoff is required for this cloud path. Deterministic facts and checks remain distinguishable from unreviewed AI analysis.

The bundle's checksums identify its source and images. Packaging alone does not establish that this candidate passed live tests. Review the version-specific acceptance evidence in the source before treating a release as tested. The console and Hermes image IDs are separate pins in `RELEASE.json`.

## Before deploying

You need Terraform 1.10+, AWS CLI and permissions to create this dedicated EC2/ASG/IAM/SSM deployment; an IPv4 subnet with outbound HTTPS and DNS connectivity; an existing private SSE-S3 bucket; and a Secrets Manager secret containing your selected provider's **raw API key**. The supplied images run on Linux amd64. Use a dedicated S3 workspace prefix. Do not point two deployments at the same prefix. Operator-initiated model calls, EC2, S3 and Secrets Manager may incur charges.

This preview serves one trusted operator, one workspace and one investigation at a time. It is not a shared multi-user service. The default host role manages CE storage; it does not grant Hermes access to inspect your whole AWS account. Begin with sample or explicitly imported evidence. Additional collection uses the separately scoped onboarding paths in the source documentation.

Extract `source.zip` into a directory named `source`. Read [the full architecture and operations guide](source/docs/HERMES-CLOUD.md) and inspect [the Terraform source](source/deploy/aws-hermes/main.tf), [variables](source/deploy/aws-hermes/variables.tf) and [bootstrap](source/deploy/aws-hermes/boot.sh.tftpl). The snapshot includes the full CE source, skills and infrastructure, without Git history. It contains no account-specific tfvars, Terraform state, provider credentials or private test logs.

Validate the outer ZIP against its supplied `.sha256` file. After extraction, verify `SHA256SUMS` (`sha256sum -c SHA256SUMS` on Linux; PowerShell `Get-FileHash -Algorithm SHA256` can verify each named file). In particular, the `console.tar.gz` and `hermes.tar.gz` checksums must match `RELEASE.json`. Their image IDs are verified by the packager against the actual Docker-save image configurations.

## Upload and configure

Upload the two supplied archives to two dedicated keys in your bucket using your normal AWS profile. For example, replace `YOUR_BUCKET` and `YOUR_RELEASE_PREFIX` in these commands:

```powershell
aws s3 cp console.tar.gz s3://YOUR_BUCKET/YOUR_RELEASE_PREFIX/console.tar.gz
aws s3 cp hermes.tar.gz s3://YOUR_BUCKET/YOUR_RELEASE_PREFIX/hermes.tar.gz
```

Create a private tfvars file outside the extracted source. Populate these values from your own account and `RELEASE.json`:

| Input | Value |
|---|---|
| `account_id`, `region`, `subnet_id` | Your target AWS account, region and subnet |
| `name` | A new name dedicated to this CE deployment |
| `bucket_name`, `workspace_prefix` | Existing bucket and a new durable workspace prefix |
| `console_image_key`, `hermes_image_key` | The two uploaded object keys, without `s3://bucket/` |
| `console_archive_sha256`, `hermes_archive_sha256` | The corresponding `archive_sha256` values in `RELEASE.json` |
| `console_image_id`, `hermes_image_id` | The corresponding `image_id` values, including `sha256:` |
| `model_secret_arn` | Exact ARN of the raw-key secret; never paste its key into tfvars |
| `secret_kms_key_arn` | Optional exact customer-managed KMS key ARN if your model secret uses one |
| `model_provider`, `model_name`, `model_base_url` | Hermes provider identifier, selected model and HTTPS endpoint |
| `model_key_env` | Provider key environment variable, normally `OPENAI_API_KEY` for a compatible endpoint |
| `running` | `true` to start, `false` to scale the ASG to zero |

`model_provider` defaults to `custom`. Use a provider/model supported by the pinned Hermes runtime. DeepSeek is an **unverified optional configuration** requiring your own key and a real-provider test; it is not enabled or used as fallback. There are no scheduled model calls. The default `t3.medium` host is Spot, max one instance. If you disable its public IP, provide suitable outbound NAT or endpoint connectivity yourself. An SSE-KMS data bucket needs additional reviewed key permissions; do not silently broaden IAM.

## Review and apply

From the extracted bundle directory, replace the private file path below with yours:

```powershell
terraform -chdir=source/deploy/aws-hermes init
terraform -chdir=source/deploy/aws-hermes validate
terraform -chdir=source/deploy/aws-hermes plan -var-file=C:/private/ce-hermes.tfvars -out=ce-hermes.tfplan
terraform -chdir=source/deploy/aws-hermes apply ce-hermes.tfplan
```

Inspect the saved plan before applying it. The boot process verifies the archives, loads their pinned image IDs, retrieves the model key into tmpfs and starts the console and trusted job broker. Disposable Hermes workers receive selected files and model configuration, not AWS credentials or the console token. The trusted host/console IAM boundary and outbound DNS exception are described in the architecture guide. Keep generated state, plans and tfvars private.

## Open the workspace

Use the Terraform `autoscaling_group` output to find the active EC2 instance. The host has no inbound security-group ports. Install AWS's Session Manager plugin, then open an SSM `AWS-StartPortForwardingSession` with remote port `8765` and a free local port, for example `8879`. These PowerShell commands use your configured AWS profile and region; replace the instance placeholder with the active instance from that ASG:

```powershell
terraform -chdir=source/deploy/aws-hermes output -raw autoscaling_group
'{"portNumber":["8765"],"localPortNumber":["8879"]}' | Set-Content -Encoding ascii ssm-ports.json
aws ssm start-session --target YOUR_ACTIVE_INSTANCE_ID --document-name AWS-StartPortForwardingSession --parameters file://ssm-ports.json
```

Browse `http://127.0.0.1:8879` while that session remains open. Wait for bootstrap and SSM registration to finish if the newly launched instance is not yet available. This tunnel opens the cloud workspace; it does not change your local Docker preview.

Create/load a sample assessment, review its deterministic findings, add or review shared knowledge, and start an investigation only after checking the selected evidence and provider. Treat the answer as an AI draft with citations to inspect. This experience does not automatically remediate AWS resources. Invalid credentials, provider errors and interrupted jobs should be visible rather than presented as successful investigations.

## Stop and retain your work

Set `running=false` in the same private tfvars, review a new plan and apply it. **Do not just stop the EC2 instance:** its ASG may replace it. S3 preserves committed records: evidence, reviewed knowledge, investigation requests and results that the console has persisted. A model finishing alone is not a durability guarantee until its result is committed. The local database is rebuilt from S3; temporary job files, unfinished model output and worker scratch space disappear with compute. Interrupted work needs an explicitly requested new investigation rather than an automatic replay, and may incur another model call. Bucket data and the secret remain and may incur storage charges. Do not delete the workspace prefix merely to stop compute.

Send synthetic or redacted feedback using [FEEDBACK.md](FEEDBACK.md). Never share your private tfvars, state, credentials, raw cloud evidence or model key when reporting a problem.
