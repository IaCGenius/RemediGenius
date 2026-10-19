# Single-compute Spot setup

This replacement deployment is undergoing live acceptance testing. The existing
Lambda deployment is preserved separately; do not destroy it during migration.

## Prerequisites

Use Bash on Linux or WSL2, Terraform >= 1.10, AWS CLI v2 and Python. Sign in to
AWS with an operator identity allowed to provision this stack. Provisioning needs
write permissions; the runtime's customer-resource operations remain reads.
Install the AWS Session Manager plugin for the local tunnel.

Use an existing subnet in **us-east-1** with outbound HTTPS access. The stack
creates no VPC or NAT gateway. A public subnet requires an Internet Gateway route;
a private subnet needs suitable outbound connectivity. No inbound port is opened.

## Create

From the repository root:

```bash
python tools/package_native_hermes.py --output .rgce/spot-source.zip
cd deploy/aws-single
cp example.tfvars local.tfvars
# Edit account_id, subnet_id and the optional model settings.
terraform init
terraform plan -var-file=local.tfvars
terraform apply -var-file=local.tfvars
```

The default `running = false` provisions durable resources without launching
compute. Set `running = true` and apply to start the Spot instance. The pool is
`t3.large` / `t3a.large`; Hermes has a 6144 MiB limit. Leave memory for the collector,
validator and host when changing these values.

The instance builds pinned containers. Bootstrap can take several minutes.
Read `/var/log/cloud-init-output.log` and the `rgce-native-boot` service through SSM
if it does not become ready. Do not paste model configuration or secrets in issues.

## Connect

Find the instance with the stack's ASG name, then start a local tunnel:

From the repository root, the helper can show the login privately and open the
tunnel: `bash tools/open-native-hermes.sh --name rgce-simple --with-login`.
Use your chosen stack name. The helper reads the retained login through SSM;
it does not require a dashboard secret in Secrets Manager. Your organization's
SSM session logging settings apply. The PowerShell helper remains a secondary option.

For a tunnel without displaying credentials:

```bash
aws ssm start-session --region us-east-1 --target i-YOUR_INSTANCE \
  --document-name AWS-StartPortForwardingSession \
  --parameters 'portNumber=9120,localPortNumber=9125'
```

In a separate SSM shell, read `/data/hermes/ce-login.json` privately to obtain the
username and password. Open `http://127.0.0.1:9125/chat?profile=ce-desk` and sign in.
Do not paste the login in chat. The optional UI uses remote port 9122; forward it
to another local port and use the same login, then select **ce-desk**.

## Model and first use

Use your own model account. CE has been exercised with DeepSeek v4.1 Flash and
Qwen through the configured custom endpoint; this does not validate every provider.
Use a reasoning model with reliable tool calling and sufficient context capacity.

An optional existing Secrets Manager secret can seed `MODEL_API_KEY`. This stack
does not create a model key. If omitted, configure the provider, model and key with
Hermes before an investigation. Never put a key into a chat message or tfvars.
A model ID alone does not prove access. Retained Hermes configuration takes
precedence over initial seeds; do not expect changing tfvars to replace it.

Try: `What AWS target can you access? Separate configured access from tested reads.`
Then ask for a bounded inventory or findings investigation. To supply context,
ask CE to stage a short organization policy with its scope. Review the draft and
send the exact publication phrase returned by the knowledge tool. This records
an operator assertion, not an independently verified AWS fact.

## Persistence, stop and remove

Raw evidence and receipts go to the private versioned S3 bucket during collection.
Sessions, cases, knowledge and model configuration live on retained EBS and are
checkpointed to S3 every two minutes. This is a recovery interval, not zero data
loss. Check `systemctl status rgce-state.timer` and `rgce-state.service`.
Model credentials can be included in state backups. Protect bucket access.

Set `running = false` and apply to stop compute while retaining data. Scheduled
checks also stop. On restart, at most one overdue check runs; missed intervals
are not replayed. Read-only scheduled checks do not call an LLM.

Back up Terraform state and the S3 bucket before removal. Use `terraform destroy`
with the same var-file. By default a non-empty bucket prevents complete removal.
The retained session volume creates a final snapshot when destroyed. Existing
model secrets are not owned or deleted by CE. Deliberately setting
`delete_data_on_destroy = true` permits deletion of the bucket and its contents;
this is irreversible and should only be used after choosing what to retain.
