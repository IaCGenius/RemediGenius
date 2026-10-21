# Start here — RemediGenius Community Edition (RemediGenius-CE)

## What you get

One Hermes profile, `remedigenius`, that opens every conversation with your AWS security attention board.
Ask it things like:

- "hi" or "what needs attention?" → P1 first, what changed since the last scan, blind spots, one next step
- "investigate 3f9c2a7b1d04" → bounded read-only CloudTrail/IAM/GuardDuty reads and a verdict
- "fix 8e41d0c9a6b2 — our Terraform is in /data/iac/infra" → code location, diff, `terraform validate`, rollback
- "that bucket is a public website, accept the risk" → recorded after you approve the prompt
- `/triage` → the board without a model call (interactive chat)

## Choose a path

| | Docker workstation | AWS Spot |
| --- | --- | --- |
| Runs on | your machine (Docker Desktop or Linux Docker) | one Spot instance in your account |
| AWS access | your AWS profile, or (recommended) a read-only role you name | a read-only audit role created by the stack |
| Durable storage | a folder on your machine (`~/RemediGenius-CE`) | a private S3 bucket created by the stack |
| Dashboard | `http://127.0.0.1:9125` | SSM port-forward to `http://127.0.0.1:9125` |
| Guide | [docs/WORKSTATION.md](docs/WORKSTATION.md) | [deploy/aws-single/README.md](deploy/aws-single/README.md) |

Already running Hermes? [docs/LOCAL-HERMES.md](docs/LOCAL-HERMES.md) adds the profile to your installation.

## What "ready" means

- The dashboard opens on the `remedigenius` profile and a model is configured (validated: `deepseek-v4.1-flash`).
  **Without a working model key the desk can still scan, but cannot chat.** Never paste a key into chat.
- The desk's first scan has run (about 3 minutes after start, then every 6 hours). `/triage` shows it.
- Coverage lines say which sources were read. "Not enabled" or "access denied" is a blind spot, not a clean result.

## Before you rely on it

- Read [docs/LIMITS.md](docs/LIMITS.md): what is and is not covered, and what data reaches your model provider.
- Put your business context in `triage.yaml` (critical accounts, application tags, goals, IaC repositories). It changes
  priorities; ask the agent "help me onboard" to fill it in conversationally.
