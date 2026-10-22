# RemediGenius Community Edition on a Docker workstation

Run RemediGenius-CE on your own machine to try it against a real AWS account. Nothing is deployed into AWS.

## Requirements

- Docker (Docker Desktop on Windows/macOS, or Docker Engine on Linux) and Python 3.11+ with `boto3`
  (`python -m pip install boto3`)
- An AWS CLI profile that can read your security services. **Recommended:** a read-only role with the AWS managed
  policies `SecurityAudit` and `ViewOnlyAccess`, passed as `--read-role-arn`.
- A model API key for an OpenAI-compatible endpoint (validated: `deepseek-v4.1-flash`)

## Start

```sh
git clone https://github.com/IaCGenius/RemediGenius.git
cd RemediGenius
export REMEDIGENIUS_MODEL_KEY=...            # PowerShell: $env:REMEDIGENIUS_MODEL_KEY = '...'
python tools/workstation.py run \
  --aws-profile default \
  --read-role-arn arn:aws:iam::111122223333:role/RemediGeniusReadOnly \
  --model-base-url https://YOUR_PROVIDER/v1 \
  --iac ~/src/infra                         # optional: folder with your Terraform/CloudFormation/CDK repos
```

The first start builds the desk image (about a minute), restores any earlier state, starts both containers and prints:

```
RemediGenius-CE is running: http://127.0.0.1:9125/chat?profile=remedigenius
```

Get the dashboard login with `python tools/workstation.py login`. It is stored in `~/RemediGenius-CE/login.json`;
keep it out of chat and screenshots. Say "hi".

The **Knowledge** tab (next to Chat) is where you tell the desk what matters: owners, critical applications and
accounts, accepted risks, policies and runbooks. Importing PDF or Office files installs the open-source converter
markitdown into the Hermes volume on first use (about 350 MB, needs internet once). See [KNOWLEDGE.md](KNOWLEDGE.md).

`run` keeps the desk's AWS credentials fresh (assumed-role credentials last an hour). Use `start` instead to start
and exit; `refresh` renews credentials once.

| Command | Does |
| --- | --- |
| `start` / `run` | build, restore, start; `run` also refreshes credentials every 30 minutes |
| `status` | container state and the current board |
| `login` | print the dashboard login |
| `refresh` | renew the desk's AWS credentials |
| `stop` | final checkpoint, then remove both containers (volumes and the durable folder stay) |

Options: `--region` (default us-east-1), `--regions us-east-1 eu-west-1` (first start), `--data` (durable folder,
default `~/RemediGenius-CE`), `--port` (9125), `--model-name` (default `deepseek-v4.1-flash`), `--scan-every-hours` (6),
`--watch-deliver` (`local`; `''` disables the alert job).

## What runs

| Container | Holds | Has AWS credentials |
| --- | --- | --- |
| `remedigenius-ce-desk` | the rgtriage service (scans, investigation reads, IaC locator, `terraform validate`), checkpoints | **yes**: temporary role credentials, or your profile's credentials if you give no role |
| `remedigenius-ce-hermes` | pinned Hermes image, profile `remedigenius`, dashboard | **no** |

The desk container is read-only, drops all Linux capabilities, and is never reachable by the model except through
the socket's fixed list of triage commands. Without `--read-role-arn`, the profile's own credentials are copied into
the desk container. They are short-lived for SSO/role profiles and long-lived for IAM user keys. Prefer a role.

## Durable storage

The desk checkpoints two homes, the Hermes home (conversations, settings, memory) and the desk state
(`triage.yaml`, decisions, scan history), into `~/RemediGenius-CE/durable/`. It does this every 2 minutes, right after
scans and decisions, and on `stop`. If Docker volumes are lost, the next `start` restores them from that folder. A new home
can never overwrite existing checkpoints by accident: it must descend from the latest checkpoint.

Back up `~/RemediGenius-CE/` like any private folder; it contains your conversations and the dashboard login.

## Business context and IaC

Edit `triage.yaml` through the agent ("help me onboard"), or directly:
`docker exec -it remedigenius-ce-desk sh -c 'vi /data/rgtriage/triage.yaml'` (or copy it out with `docker cp`).
With `--iac`, repositories are mounted read-only at `/data/iac`, and the agent saves proposed changes in
`/opt/data/proposals` (copy them out with `docker cp remedigenius-ce-hermes:/opt/data/proposals .`).

## Differences from the Spot deployment

The workstation path does not apply the Spot host's egress firewall to the Hermes container (Docker Desktop networking
differs). The Hermes container still has no AWS credentials and binds the dashboard to `127.0.0.1` only.
