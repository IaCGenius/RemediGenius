# Start with RemediGenius CE

CE runs Hermes with one `ce-desk` profile, bounded AWS read tools, organization
knowledge and fix validation. The operator applies fixes. Collection runs on the
same Docker workstation or Spot host; evidence and private recovery checkpoints
are stored in S3.

Use the [validation record](docs/RELEASE-VALIDATION.md) for the tested source,
model, deployment paths and remaining boundaries.

| Choose | What you need | Guide |
| --- | --- | --- |
| AWS Spot | Bash/WSL2, Terraform >= 1.10, AWS CLI v2, Python, SSM plugin, an existing us-east-1 subnet, a provisioning identity, your model key | [Spot walkthrough](deploy/aws-single/README.md) |
| Docker workstation | Docker, an AWS profile, a private S3 bucket, your model key | [Local setup](docs/LOCAL-COMPUTE-WORKSTATION.md) |

The Spot walkthrough is the single current AWS deployment path. It covers clone,
package, `terraform plan/apply`, start, SSM login, model setup, first question,
knowledge publication, receipts, cases and stop/remove.

## What "ready" means

- The stack is running and you have logged in to the native dashboard with
  `ce-desk` selected.
- A model key is configured, either as an existing Secrets Manager secret or
  inside Hermes. **Without a working model key, CE is not ready to investigate.**
  Never put a key in a chat message or in tfvars.
- The collector, not Hermes, holds the AWS reads. Hermes runs without AWS
  credentials and cannot read instance metadata.

Both paths offer the native Hermes dashboard and the optional hermes-ui. The
optional UI provides chat and session access; use the native dashboard for Kanban
and other controls described in the [UI guide](docs/HERMES-UI.md).

## First run

1. Ask what target is configured, then request one bounded inventory or findings
   investigation. Example: `What AWS target can you access? Separate configured
   access from tested reads.`
2. Inspect the returned source receipts and coverage gaps. Receipts and raw
   records are written to the private S3 bucket under `<prefix>/receipts`,
   `<prefix>/raw`, `<prefix>/normalized` and `<prefix>/catalog.json`.
3. To add organization context, ask CE to stage a short policy with its scope.
   Review the exact Markdown and scope, then send the returned
   `publish knowledge <id>` phrase in a separate message. This is an operator
   assertion, not a verified AWS fact.
4. Ask for a remediation proposal and save it as a case on the native Kanban.
   After your change window, return to the case and collect fresh evidence.

Read [architecture and recovery](docs/SINGLE-HOST-MIGRATION.md), [permissions](docs/IAM.md)
and [reused tools](docs/AWS-TOOLING.md). Scheduled checks stop when compute stops.
The S3 checkpoint interval is two minutes, not zero-data-loss replication.
