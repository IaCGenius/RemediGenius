# Connect one existing source

CE uses information you already have. The console does not enable paid AWS services, schedule collection, request a GitHub token or run a model. An operator reviews each read plan and runs collection explicitly.

## Where the command runs

| Console | Collection path |
|---|---|
| Native Python, local data | The generated command uses the same Python executable and workspace path. Run it on that workstation, then refresh. |
| Docker or S3-backed console | Install/activate the CE wheel on your workstation. The generated command writes `ce-evidence.json`; inspect it and choose **Import evidence** in the console. No credentials are injected into the console. |

PowerShell and macOS/Linux command forms are shown. Add `--profile NAME` for your existing AWS profile and `--external-id VALUE` when the role trust requires it. `--check` makes one page/object read; it does not certify comprehensive coverage. Files refuse overwrite. Collection to a file does not open a workspace or use its storage configuration.

The source principal needs permission to assume the selected `RemediGeniusCommunityReadOnly` role. Reads occur through that role with an additional session policy. Follow [AWS access setup](AWS-ONBOARDING.md); no account admin credential belongs in the investigation agent.

## Available adapters

| Source | Working interface | What it means |
|---|---|---|
| Security groups | `collect-aws sg` | Regional SG configuration and deterministic rules; `--group-ids` can narrow resources. |
| Security Hub | `collect-aws securityhub-asff` | Existing ASFF findings; provider severity/lifecycle retained. Inspector/GuardDuty require their existing integration into Security Hub. |
| CloudTrail | `collect-source cloudtrail-events` | Regional management event history, bounded time window/pages; no data events or Lake. |
| CloudWatch Logs | `collect-source cloudwatch-logs` | One exact log group; FilterLogEvents, no Insights query. |
| S3 | `collect-source s3-object` | One same-account JSON/JSON.gz object, up to 2MB decoded; no bucket scan or generic archive import. |
| Terraform context | `repo LOCAL_PATH` | Committed .tf/.tf.json blobs; no hooks, execution, state, tfvars or automatic resource mapping. |
| Documents | UI upload/paste or `documents PATH` | Source receipts and text conversion; review guidance before using it. |

Logs/objects are context, not automatically correlated findings. An empty result is not evidence of safety. Imported files have unknown coverage even when their JSON claims completeness. This intentionally limits reassessment claims after file transfer. Use a native collector-backed local workspace when testing trusted before/after SG comparison; the bundled sample also demonstrates it.

## Native CLI examples

Install the wheel with `[aws,documents]` or the source package, activate the virtual environment, then adapt these synthetic placeholders:

```sh
python -m rgce collect-aws sg --role-arn arn:aws:iam::111122223333:role/RemediGeniusCommunityReadOnly --external-id YOUR_EXTERNAL_ID --profile YOUR_PROFILE --regions us-east-1 --group-ids sg-0123456789abcdef0 --output selected-sg.json
python -m rgce collect-aws securityhub-asff --role-arn arn:aws:iam::111122223333:role/RemediGeniusCommunityReadOnly --external-id YOUR_EXTERNAL_ID --profile YOUR_PROFILE --regions us-east-1 --max-calls 5 --output selected-findings.json
python -m rgce collect-source s3-object --role-arn arn:aws:iam::111122223333:role/RemediGeniusCommunityReadOnly --external-id YOUR_EXTERNAL_ID --profile YOUR_PROFILE --region us-east-1 --location s3://YOUR_BUCKET/YOUR_KEY.json --consent --output ce-evidence.json
```

The output file is selected cloud data: keep it private and review it before sharing with any model. Failed reads retain their error/partial-coverage status rather than becoming a clean assessment. Output is limited to the console's 10MB import size; narrow resources or read budget if needed.

For native local storage, omit `--output` and optionally supply `--home PATH` before the subcommand. Collection saves a receipt and, for SG/ASFF, an assessment. Do not run a second S3 writer alongside the console; use the file/import path instead.

## Repositories and existing agents

Use your existing GitHub CLI/browser authentication to clone an explicitly selected repository, then read committed Terraform locally. CE does not implement OAuth or manage that token. Export the selected context for the agent only after checking for inline secrets. Readable skills and investigation ZIPs are the default integration. Optional MCP is for native local-data installations with the extra installed; container paths cannot be pasted into a workstation MCP client.

## Optional compute

The [approved reader](AWS-ONBOARDING.md) deploys fixed reviewed Python code with an exact source plan, separate roles, explicit invocation consent and S3 outputs. It is off by default; Terraform manages it separately. Lambda execution comes and goes, but functions, versions, logs, IAM and S3 remain until retired. Pausing blocks new invocations, not an invocation already running.

The advanced arbitrary-code kiosk is experimental and not part of the preview's supported installer. Local collectors and file imports work without it. The existing Cloud Custodian/Prowler/IaC tools can remain in the customer's workflow; CE does not advertise unimplemented adapters for them.

## Verification and scope

Selected AWS source reads, denied IAM operations, S3 persistence, optional approved-reader pause and compute replacement have separate acceptance reports: [rc6](RC6-ACCEPTANCE.md), [rc7](RC7-ACCEPTANCE.md), [rc8](RC8-REVIEW.md), and [the private preview](PRIVATE-PREVIEW.md). CloudFormation templates were validated, not deployed as stacks. Terraform was the exercised AWS provisioning path. Nothing here means every customer's permissions, regions, data formats or provider integrations have been tested.
