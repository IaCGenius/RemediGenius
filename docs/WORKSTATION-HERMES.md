# Native Hermes on your workstation

This runs the official pinned Hermes container and the CE profile locally. AWS
Lambda performs bounded collection; S3 retains evidence; EventBridge runs daily
deterministic checks even when your workstation is off. This is a hybrid deployment,
not an offline edition. AWS and model usage are charged to your accounts.

The legacy console is archived outside this release. Use the launcher below.

The launcher checks the pinned upstream dashboard source and mounts a small CE
session-limit overlay: two live terminals and ten minutes for detached terminals.
Hermes's own cleanup preserves saved conversations in the Docker volume. Finish
an active run before starting another chat. The overlay must be reviewed when
updating the official image; a changed source hash stops preparation explicitly.

## 1. Get the public source and prerequisites

Use AWS `us-east-1` and DeepSeek v4.1 Flash for the release baseline. Install Git, Python 3.11+, Docker with Linux containers, Terraform 1.10+ and AWS CLI v2. The examples use Bash on Ubuntu 24.04 LTS (native or WSL2); run them from the repository root. PowerShell helpers remain secondary.

```bash
git clone https://github.com/IaCGenius/RemediGenius.git
cd RemediGenius
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[aws,documents]"
mkdir -p .rgce
```

The documents extra installs conversion dependencies for selected knowledge files; it does not start the legacy console. Use the activated Python environment in each Bash terminal.

## 2. Authenticate to AWS first

You need an authenticated AWS operator identity, **not necessarily long-lived
access keys**. Prefer your organization's IAM Identity Center (SSO) profile:

```sh
aws configure sso --profile ce-operator
aws sso login --profile ce-operator
aws sts get-caller-identity --profile ce-operator
```

Use your actual SSO details. Confirm the returned account matches Terraform's
`account_id`. Set `"aws_profile": "ce-operator"` in workstation JSON. Before running
Terraform, select that same profile in its terminal:

```bash
export AWS_PROFILE=ce-operator
```

For bash/zsh, use `export AWS_PROFILE=ce-operator`. Reauthenticate with `aws sso
login --profile ce-operator` when your organization session expires; the launcher
cannot renew a revoked/expired operator login on your behalf.

If your organization supplies an IAM user's access keys instead, configure a
named profile privately with `aws configure --profile ce-operator`. This asks for
an **access key ID and secret access key**, plus region/output settings. They stay
in the workstation's AWS credential store, not the CE JSON or Terraform inputs.
Temporary STS credentials additionally require **aws_session_token**; a temporary
access/secret pair without its token will fail. Use your organization's temporary
credential tooling/profile configuration. Never use root access keys or paste
AWS credentials into Hermes chat. The model API key is a different credential.

The provisioning identity needs permission to create the documented AWS backend.
After provisioning, the runtime operator needs `sts:AssumeRole` for the generated
`reader_role_arn` and must match its trust policy. `operator_arn` is the stable IAM
role/user ARN, not the `arn:...:sts::...:assumed-role/.../session` returned for an
assumed session. Your AWS administrator can supply the correct IAM role ARN.
If model credentials come from Secrets Manager, add the separate secret-read/KMS
permissions described in [v0.1.3 release onboarding](ONBOARDING.md).

Connection flow:

`your AWS profile -> local launcher -> STS limited invoker role -> Hermes -> Lambda collector -> scoped AWS reads -> S3 receipts`

The launcher gives Docker temporary access-key/secret/session-token credentials
for collector invocation and evidence reads. It refreshes them every 20 minutes;
the session lasts one hour. Full operator credentials and the `.aws` directory
are not mounted in Hermes. The Lambda execution role performs collection using
its configured operations, target accounts and region restrictions.

See AWS's [SSO setup](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
and [temporary credential requirements](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_use-resources.html).
SSO is supported through the normal SDK profile chain; our existing acceptance
run does not constitute a separate end-to-end test of your organization's SSO setup.

## 3. Prepare the AWS backend

Prerequisites: Docker with Linux containers, Python 3.11 or later with boto3,
Terraform 1.10 or later, and an authenticated AWS operator profile. The operator
needs provisioning permissions for S3, IAM, Lambda, logs and EventBridge Scheduler.
These operator credentials stay on the workstation and are not mounted in Hermes.

1. Copy `deploy/aws-workstation/terraform.tfvars.example` to `.rgce/workstation.tfvars`, a private `.tfvars`
   file. Set your account, region and exact operator IAM user/role ARN. For an SSO
   or assumed-role session, use its IAM role ARN, not its STS session ARN.
2. Initialize and inspect the plan, then apply it:

```bash
cp deploy/aws-workstation/terraform.tfvars.example .rgce/workstation.tfvars
# Edit .rgce/workstation.tfvars before continuing; set region = "us-east-1".
inputs=$(realpath .rgce/workstation.tfvars)
plan="$(pwd)/.rgce/workstation.tfplan"
terraform -chdir=deploy/aws-workstation init
terraform -chdir=deploy/aws-workstation plan "-var-file=$inputs" "-out=$plan"
# Review the displayed resource/permission changes before applying the saved plan.
terraform -chdir=deploy/aws-workstation apply "$plan"
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

## 4. Configure your model and start Hermes

Copy `deploy/aws-workstation/workstation.example.json` into `.rgce/` and fill its
backend fields from Terraform output. Set your AWS profile and Hermes-compatible
model/base URL. Supply the model key through the named environment variable, or
set `model_secret_arn` to a Secrets Manager secret containing the raw API key.
Never commit keys or private deployment configuration.

```bash
cp deploy/aws-workstation/workstation.example.json .rgce/workstation.json
# Edit backend fields, aws_profile, model_name and model_base_url first.
# Baseline model_name: deepseek-v4.1-flash (confirm the identifier with your provider).
# Prompt privately; do not paste the key into this JSON or chat.
read -rsp "Your model API key: " MODEL_API_KEY; echo
export MODEL_API_KEY
python tools/native_workstation.py run --config .rgce/workstation.json
```

Keep that terminal open: it refreshes the narrowly scoped reader credentials every
20 minutes. Ctrl+C stops the local container. A refresh failure stops it rather
than leaving a misleading connected session. AWS schedules remain active.
`start` is an alternative for short tests, but its reader credentials expire after
one hour unless you run `refresh` yourself.

## 5. Retrieve your login and open ce-desk

Leave the run terminal open. In a second terminal at this checkout, activate the same Python environment and explicitly retrieve your locally generated dashboard login:

```bash
python tools/native_workstation.py login --config .rgce/workstation.json
```

Open `http://127.0.0.1:9125/chat?profile=ce-desk`, sign in with that username/password, and confirm **ce-desk** in Chat. The dashboard password is neither the AWS secret access key nor the model API key. Never include the credential terminal in screenshots.

![Native Hermes login form; use your own generated dashboard credentials](images/hermes-login.jpg)

![Select the single CE profile, ce-desk, in native Hermes Chat](images/hermes-profile-selector.jpg)

Continue with [the illustrated first investigation and knowledge walkthrough](WALKTHROUGH.md).

## 6. Investigate and add knowledge

Ask first: “What account aliases, regions and sources can you use? Distinguish configured access from collected evidence.”

Ask: “Collect current Config recorder configuration. Show the account, region,
observation time, source receipt and missing coverage.” Then ask about Security
Hub findings, prepare a fix and save a follow-up case. No customer-cloud remediation
is executed. Generated CLI/Terraform/CloudFormation remains a reviewable proposal.

Use [the knowledge walkthrough](NATIVE-KNOWLEDGE-QUICKSTART.md) to import one policy, mount a selected view using `knowledge_dir`, and ask how it changed the recommendation. Chat text alone is not durable shared knowledge.

## 7. Stop, restart and protect storage

Ctrl+C in the launcher terminal stops local Hermes. Or, from another terminal:

```bash
python tools/native_workstation.py stop --config .rgce/workstation.json
```

Restart with the same `run --config .rgce/workstation.json` command and credentials. Keep the same name/volume to recover your conversations and cases. Set `schedule_enabled=false` in Terraform and review/apply a plan if you also want daily AWS checks stopped. Stopping Docker alone does not stop those checks.

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

## Recover from an expired operator login

If credential renewal fails, `run` stops the container and reports the underlying
error after the stop notice. It does not delete the named volume or stop AWS schedules.
For an expired SSO session, run `aws sso login --profile ce-operator`, check
`aws sts get-caller-identity --profile ce-operator`, then repeat the same launcher
`run --config .rgce/workstation.json` command. Use your actual profile name.
Open Sessions to resume saved work. If the error is AccessDenied rather than an
expired login, correct the operator trust/permissions; do not grant the agent admin.

When using `model_secret_arn`, the local launcher retrieves the secret with your
operator profile before Docker starts. The limited reader role is not granted
Secrets Manager access. This is separate from the model key passed into Hermes.

## bash/zsh equivalents (not a macOS acceptance claim)

The tested workstation path is Ubuntu under WSL2 with Docker Desktop and a Windows
browser. That is not a separate native-Linux or macOS end-to-end qualification.
Use the same configuration fields and review steps above; the commands below
summarize the Bash setup and can be adapted by operators using zsh.

```sh
git clone https://github.com/IaCGenius/RemediGenius.git
cd RemediGenius
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[aws,documents]'
mkdir -p .rgce
export AWS_PROFILE=ce-operator
cp deploy/aws-workstation/terraform.tfvars.example .rgce/workstation.tfvars
# Edit the inputs before planning.
inputs="$PWD/.rgce/workstation.tfvars"
plan="$PWD/.rgce/workstation.tfplan"
terraform -chdir=deploy/aws-workstation init
terraform -chdir=deploy/aws-workstation plan "-var-file=$inputs" "-out=$plan"
# Review changes before applying.
terraform -chdir=deploy/aws-workstation apply "$plan"
terraform -chdir=deploy/aws-workstation output -json workstation_backend
cp deploy/aws-workstation/workstation.example.json .rgce/workstation.json
# Edit JSON with your backend and provider fields; do not put the model key in it.
# Prompt privately without shell-history disclosure (works from bash or zsh).
export MODEL_API_KEY="$(python -c 'import getpass; print(getpass.getpass("Model API key: "))')"
python tools/native_workstation.py run --config .rgce/workstation.json
```

In a second activated terminal, use the same platform-independent login command:

```sh
python tools/native_workstation.py login --config .rgce/workstation.json
# When finished:
python tools/native_workstation.py stop --config .rgce/workstation.json
unset MODEL_API_KEY
```

## Operator reference

[Platform, state, costs and removal](PLATFORM-AND-REMOVAL.md) · [IAM roles and operator policies](IAM.md) · [Troubleshooting](TROUBLESHOOTING.md).

Startup makes one small model tool-call probe before opening the dashboard. No AWS data or knowledge is sent. First validator build downloads its pinned dependencies.
