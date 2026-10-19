# Docker workstation: local collection and S3 recovery

The replacement launcher is being acceptance-tested with the single-compute Spot
path. Use a separate configuration, bucket prefix and Docker name from an old
Lambda deployment. Do not reuse its Terraform state for this stack.

## Prepare AWS

Sign in with an AWS profile for the intended account, preferably IAM Identity
Center. Do not paste access keys into chat. The profile needs security/metadata
reads and scoped read/write access to CE's own S3 prefix. S3 writes store evidence
and private recovery state; they do not remediate customer resources.

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

## Start

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
Without a key, use Hermes model onboarding before investigating.

In another terminal:

```bash
python tools/native_workstation.py login --config .rgce/workstation.json
```

Read the login privately and open `http://127.0.0.1:9125/chat?profile=ce-desk`.
The optional UI is at port 9126 and uses the same login. Select **ce-desk**.
Keep the password out of chat. Both interfaces use the same backend and profile.

## Knowledge and scheduling

Ask CE to stage a short policy with its scope. Review the Markdown draft and
confirm its exact publication phrase. Published notes are checkpointed with the
profile. Existing file views can be selected with `knowledge_dir`; the launcher
copies the selected view into retained storage before launch. Source files remain
unchanged. Review/import an updated view explicitly when its source changes.

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
