# Inputs, identities and first use

RemediGenius CE is a single-operator, self-hosted AWS investigation tool. You supply AWS access
and a model account. The tested scope is **us-east-1 with DeepSeek v4.1 Flash**.
RemediGenius CE does not include a shared key, model credits or preconfigured business policy.

## Choose where to run

| | Docker workstation | AWS Spot |
|---|---|---|
| Setup | [Workstation guide](LOCAL-COMPUTE-WORKSTATION.md) | [AWS walkthrough](../deploy/aws-single/README.md) |
| Terraform | `deploy/workstation-storage` | `deploy/aws-single` |
| AWS resources created | Private versioned S3 bucket | Private S3 bucket, Spot ASG, launch template, role/profile, security group, retained EBS |
| Existing inputs | AWS profile and model access | Provisioning identity, existing subnet, model access |
| AWS read identity | Operator's temporary credentials, mounted only in collector | Instance role, available only to host/collector |
| Model key | Environment variable or optional Secrets Manager secret | Optional Secrets Manager secret, or configure in Hermes |
| Dashboard login | Launcher `login` command | SSM shell reads retained `ce-login.json` |
| State | Named Docker volume and S3 checkpoint | Encrypted retained EBS and S3 checkpoint |

Collection runs on your chosen compute. Neither path creates a Lambda collector.
No collection or checkpoint runs while that compute is stopped. The model and AWS
APIs still require network access; workstation mode is not offline operation.

## Four different credentials

1. **Provisioning identity:** Terraform uses it to create the stack. Verify the
   account with `aws sts get-caller-identity` before applying a plan.
2. **Runtime AWS identity:** the collector uses it for admitted reads and writes
   to RemediGenius CE's own S3 storage. Hermes receives no AWS credentials. See [IAM](IAM.md).
3. **Model credential:** belongs to your provider account. Set it through the
   supported launcher/secret option or Hermes configuration, never through chat.
4. **Dashboard login:** generated for this workspace. Retrieve it privately;
   it is not your AWS login or model key.

For workstation access, prefer `aws configure sso`, then `aws sso login --profile
YOUR_PROFILE`. An existing AWS CLI profile also works. Temporary access keys need
all three values: access key ID, secret access key and session token. Do not put
these values in source files. RemediGenius CE cannot renew an expired upstream AWS login.

## Model and host requirements

Use a reasoning model with reliable tool calling and enough context for the skills,
evidence and review packet. A configured model name does not prove authentication
or successful inference. An unconfigured model must be onboarded before a live
investigation. Hermes owns model routing; RemediGenius CE supplies no separate provider SDK.

The Spot host is Amazon Linux 2023, x86_64. Its default pool is `t3.large` /
`t3a.large`, with a 6144 MiB Hermes limit. Hermes uses the pinned upstream Docker
image; the separate collector uses pinned Python 3.12 and AWS SDK dependencies.
Bash on Linux or WSL2 is the documented operator shell. Retained EBS binds the
instance to the chosen subnet's Availability Zone.

## First useful result

1. Follow the chosen setup guide and open **ce-desk**.
2. Configure your model if it is not ready. Send a small request first.
3. Ask what target and sources are configured. Then request an actual bounded
   inventory or findings read. Source availability is not collected evidence.
4. Inspect account/region scope, observation time, receipt and collection limits.
5. Add one real policy: ask RemediGenius CE to stage it with scope, review the draft, then send
   its exact publication phrase. Ask how that knowledge changes the conclusion.
6. Request a fix proposal and actual tool validation. Save a Kanban case if work
   must wait. Apply changes yourself, then ask for fresh-evidence reassessment.

## What persists

S3 receives collected records and receipts as they are produced. A two-minute
SQLite-aware checkpoint copies private runtime state, including sessions, cases,
knowledge and model configuration. An empty new runtime can restore a valid
checkpoint; existing retained storage takes precedence. This is not zero data
loss: activity after the last successful checkpoint can be lost.

Backups may include model credentials. Protect the whole bucket, Terraform state
and local configuration. None belongs in Git, screenshots or support issues.
A stopped collector cannot create a new checkpoint. Verify the last checkpoint
before stopping deliberately. [Recovery details](SINGLE-HOST-MIGRATION.md).
