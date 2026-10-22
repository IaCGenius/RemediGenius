# Start here — RemediGenius Community Edition (RemediGenius-CE)

## What you get

One Hermes profile, `remedigenius`, that opens every conversation with your AWS security attention board.
Ask it things like:

- "hi" or "what needs attention?" → P1 first, what changed since the last scan, blind spots, one next step
- "investigate 3f9c2a7b1d04" → bounded read-only CloudTrail/IAM/GuardDuty reads and a verdict
- "fix 8e41d0c9a6b2 — our Terraform is in /data/iac/infra" → code location, diff, `terraform validate`, rollback
- "that bucket is a public website, accept the risk" → recorded after you approve the prompt
- "who owns payments-db?" → answered from the knowledge base, with the concept it used; if nobody knows yet, it asks
  you once and drafts the answer for review
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
- In an AWS Organization, the `Accounts:` line says how many accounts are read fully, findings-only or not covered.
  Other accounts need one read-only role, deployed once as a StackSet. Ask the agent "help me onboard the other
  accounts" (or run `rgtriage onboarding`) for the filled-in command. They are picked up at the next scan with no
  restart. See [docs/MULTI-ACCOUNT.md](docs/MULTI-ACCOUNT.md).

## Before you rely on it

- Read [docs/LIMITS.md](docs/LIMITS.md): what is and is not covered, and what data reaches your model provider.
- Tell the desk what matters: open the dashboard **Knowledge** tab. *Overview → What the desk is missing* lists the
  gaps that change priorities (unowned P1/P2 resources, accounts without a description). Add applications, accounts,
  teams and accepted risks there, import your runbooks and policies, and approve what the agent drafts. See
  [docs/KNOWLEDGE.md](docs/KNOWLEDGE.md). IaC repository paths and regions stay in `triage.yaml`.
