# Start locally; add only the AWS pieces you need

The easiest first experience is the local Python app plus the sample workspace. Terraform is optional until you connect an account. An agent needs only the skill and a selected exported folder; MCP is not required. Source code for all operations ships in the repository.

## 1. Local workspace

Install from a reviewed checkout or wheel. For AWS and document support:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install ".[aws,documents]"
.\.venv\Scripts\python -m rgce --home .rgce/my-workspace serve
```

Open the local console, try the sample, then use Connections to export a selected assessment. Download the investigation skill there, or read `integrations/skills/remedigenius-investigate/SKILL.md`. Ask your existing agent to read the skill and exported `START-HERE.md`. Credentials remain in the existing agent/provider setup. The skill is instructions, not an OS sandbox; run untrusted investigation code under a separate user/container where appropriate.

The live acceptance run used Hermes' native file tools and an existing named provider. The generic `custom` selection returned an authentication error; selecting the configured provider explicitly succeeded. CE does not implement another model API client or copy provider secrets.

## 2. Read access only

Use **one small Terraform root**, `deploy/aws-access`, which calls `modules/aws-read-access`. It creates one role and one inline policy. It does not create an EC2 host, deploy agents, enable security services, or create compute.

Supply a private `terraform.tfvars` file (ignored by Git):

```hcl
account_id            = "YOUR_ACCOUNT_ID"
region                = "us-east-1"
trusted_principal_arn = "YOUR_IAM_USER_OR_ROLE_ARN"
external_id           = "YOUR_UNIQUE_EXTERNAL_ID_AT_LEAST_16_CHARACTERS"
log_group_arns        = [] # Optional: exact selected group ARNs with :* suffix
object_arns           = [] # Optional: exact selected S3 object ARNs
```

From that directory, run `terraform init`, `terraform plan -out=access.tfplan`, review the plan and then `terraform apply access.tfplan`. Keep state private; sensitive Terraform variables still appear in state. The account guard prevents applying against a different configured account. If the named CE role already exists, manage it through its existing stack rather than attempting a second creation.

Use CE's Connections read-plan form or `rgce plan-source --help`. An explicit `--consent` is required by `collect-source`; `--check` limits it to one page/object. The older `collect-aws` command is itself an explicit operator invocation. Add `--group-ids` to restrict SG collection to selected resources. Collection assumes the read role with an additional session policy; it does not use deployment credentials for source reads.

Users who prefer CloudFormation can download a selected-source role template from Connections. Choose one owner for the role: Terraform or CloudFormation. Never let both manage the same role. Terraform is the path exercised by the live acceptance run; AWS ValidateTemplate accepted the generated CloudFormation templates; they were not deployed as CloudFormation stacks.

## 3. Optional approved reader compute

`modules/approved-reader` is a small optional module, illustrated by `deploy/aws-test`. It reuses the earlier kiosk's deterministic ZIP builder and hash-locked Python dependencies. Build artifacts with:

```powershell
python modules/approved-reader/build.py
```

The builder needs `uv` and network access to the package index. It targets Python 3.13 on Linux, regardless of the builder's OS. Runtime dependency hashes are in `modules/lambda-kiosk/layers/runtime.lock`; lock upgrades must be reviewed and rebuilt separately.

The module deploys reviewed fixed code. Its execution role may assume only the selected read role, write only the output prefix, and write its own logs. The read role must explicitly trust that execution role. The deployed source specification fixes source, location, region and limits. An invocation must contain exactly `consent: true` and the matching CE plan hash; arbitrary source overrides or code uploads are rejected. Use a narrowly scoped invocation identity for operators; the test deployer had account administration rights, but the function's source reads used the restricted role.

The returned S3 receipt includes evidence hash, code hash, request ID, Python and boto3 versions. Output writes are distinct from source reads. No schedule, public function URL, API Gateway or provisioned concurrency is created. AWS Lambda/S3/Logs charges still apply; limits bound work, not a dollar budget.

`enabled = false` is the default: reserved concurrency is zero and the handler is disabled. It rejects new invocations. Already-running invocations are not force-killed; the function has a 60-second timeout. Pausing does not delete Lambda versions, IAM roles, logs, S3 objects or evidence. Terraform manages compute retirement; the bucket intentionally does not force-delete evidence.

This is **not** an autonomous arbitrary-code deployment service. The older `modules/lambda-kiosk` gate/builder remains a separate advanced extension; its legacy freeze still permits live runs. Do not substitute it for the approved reader's pause control. A future custom-code reader should reuse that gate only after its permissions, code admission and full pause behavior receive separate acceptance tests.

## 4. Repeatable acceptance environment

`deploy/aws-test` creates a private synthetic source bucket, a short-retention log group, an unattached SG in a VPC without workloads or an internet gateway, the scoped role and optional reader. It is a test harness, not the default customer install. Private test inputs, Terraform plans, raw AWS evidence and model transcripts stay under `.rgce/aws-acceptance`; never publish them.

`tests/live_acceptance.py` exercises collection, denied access, before/after comparison, consent, receipt hashes and pause. `tests/live_hermes_files.py` exercises selected exported files with a configured provider and checks actual tool use and citations. Both require an explicit `--run`; neither is part of ordinary pytest. Sending an AWS-derived export to a model requires the operator's approval for that provider and selected data.

The live tests preserve evidence and leave reader compute paused. To remove the acceptance environment later, first decide which S3 evidence to retain; Terraform will refuse to destroy a nonempty bucket. Do not point its state at the hosted/SaaS stack.
