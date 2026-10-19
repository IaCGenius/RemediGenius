# Docker workstation: local collection and S3 recovery

This is the local-collection path. The same deterministic collector used on Spot
runs in Docker on your machine; Hermes never receives AWS credentials. It is
being acceptance-tested with the [single-compute Spot path](../deploy/aws-single/README.md),
and a clean-deployment validation is still pending. Use a separate configuration,
bucket prefix and Docker name from an old Lambda deployment. Do not reuse its
Terraform state for this stack.

## Prepare AWS

Sign in with an AWS profile for the intended account, preferably IAM Identity
Center. Do not paste access keys into chat. The profile needs security/metadata
reads and scoped read/write access to CE's own S3 prefix. S3 writes store evidence
and private recovery state; they do not remediate customer resources. Unlike the
Spot host, there is no instance role: the launcher reads this profile and delivers
temporary credentials only to the collector container.

An administrator can create the bucket with:

```bash
cd deploy/workstation-storage
terraform init
terraform apply -var='account_id=123456789012'
terraform output -raw operator_storage_policy
```

The last command prints the storage permission document, not a credential.
The administrator attaches it to the existing operator role. For metadata reads,
review SecurityAudit and ViewOnlyAccess against your organization policy. SCPs,
resource policies and encryption-key permissions can still deny individual reads.
This stack creates no Lambda, schedule, EC2 instance or new operator identity.

## Start and log in

From the repository root, install the project's workstation requirements in one
virtual environment and use that environment for the launcher. Docker must be
running. Copy `deploy/workstation-storage/workstation.example.json` to a private
configuration under `.rgce/`; fill in account, profile, bucket and your model.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[aws]'
python tools/native_workstation.py run --config .rgce/workstation.json
```

The launcher exports credentials only to the collector's private Docker volume.
Hermes and the UI do not mount it. `run` refreshes them while running. A stale AWS
login must be renewed; `start` alone does not run a credential-refresh loop.
Use `model_key_env` to name an environment variable supplied by your local secret
manager, or `model_secret_arn` for an existing AWS Secrets Manager secret.

In another terminal:

```bash
python tools/native_workstation.py login --config .rgce/workstation.json
```

Read the login privately and open `http://127.0.0.1:9125/chat?profile=ce-desk`.
The optional UI is at port 9126 and uses the same login. Select **ce-desk**.
Keep the password out of chat. Both interfaces use the same backend and profile.

## Model configuration

Keep the custom OpenAI-compatible route: `provider: custom`, an OpenAI-compatible
base URL and `key_env: MODEL_API_KEY`, using a reasoning model with reliable tool
calling and 64k+ context. Configure the model in Hermes (Models page/config) if
you do not supply a key through the launcher. Keep the key, endpoint and model
consistent. **Without a working model key, the workstation is not ready to
investigate.** Never put a key in a chat message or in the workstation JSON.

## First use

Ask what target is configured, then request one bounded inventory or findings
investigation. Example: `What AWS target can you access? Separate configured
access from tested reads.` Inspect the returned source receipts and coverage gaps.
Evidence and receipts are written to the bucket under `<prefix>/raw`,
`<prefix>/normalized`, `<prefix>/receipts` and `<prefix>/catalog.json`.

To add organization context, ask CE to stage a short policy with its scope.
Review the Markdown draft and confirm its exact `publish knowledge <id>` phrase in
a separate message. Published notes are checkpointed with the profile. Existing
file views can be selected with `knowledge_dir`; the launcher copies the selected
view into retained storage before launch. Source files remain unchanged.
Review/import an updated view explicitly when its source changes.

Save remediation proposals as cases on the native Hermes Kanban; case actions
save local activity only and make no cloud changes.

## Knowledge and scheduling

To enable daily deterministic checks, add one to four bounded `checks` requests
and `interval_hours: 24` to the configuration. Each request uses a configured
service/operation, target `default`, region `us-east-1`, parameters and max_pages.
The checks run while the collector is running and retain reports in S3. They do
not perform an LLM investigation or apply fixes. No cron inside Hermes is needed.

## Stop, recover, upgrade

Ctrl-C in `run` stops local compute. Alternatively use the launcher `stop` action.
The named data volume and S3 objects remain. The collector checkpoints state every
two minutes; inspect its logs for failures. A fresh empty data volume restores
from the configured S3 prefix before Hermes initializes. Existing state wins.
Use a unique prefix for each independent workspace to avoid overwriting another
workspace's recovery pointer.

Back up before an upgrade. Pass `--upgrade` only after reviewing source changes.
It updates CE skills and keeps profile backups, sessions, knowledge and settings.
A checkpoint may contain model keys and chat contents; restrict its S3 access.
A stopped collector cannot refresh evidence or take backups.
Without a supplied key, a fresh profile shows **MAIN MODEL (unset)** and native Hermes configuration guidance. Use the MODELS page or the profile's Hermes model configuration command. A supplied model name alone is not seeded as a working model.
