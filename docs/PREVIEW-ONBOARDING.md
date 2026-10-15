# What a new CE user gets

RemediGenius CE is a **single-operator, self-hosted AWS investigation preview**.
You bring your AWS account and model access. There is no RemediGenius hosted
service, shared model key, trial AWS account or preconnected organization policy.

**Release baseline: one AWS account in `us-east-1`, using Qwen 3.8 Max.** Explicit additional-account onboarding remains available. Other regions and models are configurable extensions, not validation requirements or promises for this preview.

## Choose a deployment

| Question | Workstation | AWS Spot |
|---|---|---|
| Where does Hermes run? | Docker on your machine | Docker on an EC2 Spot host |
| What provisions AWS resources? | `deploy/aws-workstation` Terraform | `deploy/aws-native-sketch` Terraform |
| Existing infrastructure needed | AWS operator identity | AWS operator identity, private bucket and Internet-connected subnet |
| What is created? | S3 bucket, scoped IAM, Lambda collector, daily schedule | Scoped IAM, collectors, Spot ASG, encrypted retained EBS, dashboard secret; optional schedule |
| Model key | Local environment variable OR your Secrets Manager secret | Your Secrets Manager secret |
| Open the dashboard | `localhost:9125`, local generated login | SSM tunnel to `localhost:9121`, generated login from Secrets Manager |
| Durable conversations/cases | Named Docker volume | Retained EBS volume |
| Durable collected evidence | Your private S3 bucket | Your private S3 bucket |

Local means local **agent compute**, not offline: both paths use AWS Lambda/S3
and your configured model endpoint. Stopping the agent does not stop an enabled
AWS schedule. Neither path automatically enables paid AWS security services.

## First run in five steps

1. Clone this repository and choose one of the two paths above. Use Docker with
   Linux containers for workstation mode; install Python 3.11+, boto3, Terraform
   1.10+ and AWS CLI. Cloud dashboard access also needs the AWS Session Manager
   plugin. Authenticate as your provisioning operator and verify the account.
2. Copy the relevant example inputs into an ignored private file. Choose a stack
   name, deployment account/region and the inputs in the tables below. Inspect
   the Terraform plan before applying it.
3. Supply **your** model name, compatible HTTPS base URL and API key. For Spot,
   create the key secret first. For workstation mode, choose environment-variable
   or Secrets Manager delivery. No Qwen credential or provider is supplied by CE.
4. Follow the exact commands in [Workstation](WORKSTATION-HERMES.md) or
   [AWS Spot](NATIVE-CE-QUICKSTART.md). Open the dashboard and select `ce-desk`.
   These are file-and-command workflows today, not an interactive setup wizard.
5. Ask what account aliases, regions and sources are configured, then request a
   bounded read from a service you actually use. Check the receipt, time and scope
   before asking for interpretation or a remediation proposal.

The root Compose file is the preserved older console. It is **not** the native
Hermes quickstart. Both supported preview paths use the guides linked above.

## Inputs and what they control

| Input | Meaning |
|---|---|
| `account_id` | Account where Terraform provisions CE; provider rejects a different account |
| `region` | Region for CE infrastructure and secret retrieval, not automatic access to every region |
| `name` | Dedicated resource prefix; use a different name for independent installations |
| `operator_arn` (workstation) | Exact IAM user/role trusted to assume the limited invocation role; not an STS session ARN |
| `subnet_id` (Spot) | Existing subnet in the deployment region; its AZ also locates retained EBS |
| `bucket_name` / `workspace_prefix` (Spot) | Existing private bucket and dedicated CE object prefix |
| `source_archive_key` / `source_archive_sha256` (Spot) | Immutable uploaded CE ZIP and its printed digest |
| `model_name` / `model_base_url` | Your model identifier and compatible endpoint; seeds a new Hermes profile |
| `model_secret_arn` | Exact Secrets Manager secret holding the raw key; not a JSON object |
| `model_key_env` (workstation) | Name of the local environment variable holding the key; default `MODEL_API_KEY` |
| `aws_read_targets` (Spot) / `targets` (workstation Terraform) | Explicit account aliases, region lists and optional scoped cross-account role/external ID |
| `knowledge_view` (Spot) / `knowledge_dir` (workstation JSON) | Optional selected knowledge view, not your entire document store |
| `schedule_enabled` / `schedule_interval_hours` | Deterministic background collection; 24 hours by default when enabled, configurable 1-168 |

Workstation backend outputs supply `region`, `bucket`, `prefix`, `reader_function`
and `reader_role_arn` for the launcher JSON. Add your local `aws_profile`, model
settings and chosen key-delivery method. AWS operator credentials are used by the
launcher; the operator's full credentials are not mounted into the agent.

Workstation scheduling defaults **on**. Spot scheduling defaults **off** until
selected. Default checks are bounded Security Hub ACTIVE findings and Config
recorder configuration, not an exhaustive security scan. With custom Spot targets,
set `scheduled_checks` to matching aliases/regions; its built-in checks use `default`.
For workstation, customize `schedule_checks`; defaults use the first sorted target
and its first region. Interactive scope does not silently expand scheduled coverage.

## Regions and operating systems

There is no `us-east-1` lock in the Terraform deployment region input. The examples
and tunnel convenience script default there; pass your own `region` and tunnel
`-Region`. Deployment region and investigated regions are separate choices.
The executor checks each requested target/region against the configured list.
Adding regions or accounts requires an operator configuration/trust update.

Use `us-east-1` for this preview. The selected x86 Spot types and required services must be available in your chosen subnet/Availability Zone. We are not attempting all-region qualification. China/GovCloud partitions, ARM
hosts and universal cross-region failover are **not validated preview promises**.
The bootstrap has commercial endpoint assumptions; a partition-aware ARN alone
does not establish support. Keep the bucket and model secret in the deployment
region for this preview. Security service availability and enabled coverage vary.

- EC2 host: **Amazon Linux 2023, x86_64**, resolved through the regional public
  SSM AMI parameter. The AMI is resolved at planning time, not pinned to our test AMI.
- Official pinned Hermes container: **Debian GNU/Linux 13 (trixie)**, verified
  from `/etc/os-release` in the checked-in image digest.
- Workstation: Docker Linux containers; Windows was acceptance-tested. Linux/macOS
  host variants are not independently proven by the Windows test result.
- Default Spot pool: `t3.medium` / `t3a.medium`, configurable compatible x86 Nitro
  types. Retained EBS ties the runtime to one Availability Zone.

## Choose a capable model

Use a model with strong security reasoning, reliable multi-step tool calling and
instruction following. A compatible endpoint alone is insufficient. It must handle
the supplied skills, AWS evidence and bounded critic packet within its context
window; an undersized context can fail even when a simple chat succeeds.

The model must preserve account/region/time scope, distinguish missing evidence
from healthy posture, apply scoped exceptions without inventing policy, and prepare
technically accurate proposals. Skills and deterministic controls help, but cannot
make every small/fast model equally reliable. A "reasoning" product label or high
reasoning-effort setting alone does not establish suitability.

For the MVP, use Qwen 3.8 Max. If you deliberately experiment with another model, first run a real bounded AWS read, a knowledge/exception question and a remediation proposal with review; inspect receipts and actual critic model/context. Qwen 3.8 Max is the tested baseline. [DeepSeek smoke results](DEEPSEEK-SMOKE-ACCEPTANCE.md)
record two targeted checks on the operator's compatible endpoint. Alternative model smoke tests
are not full release qualification. Keep provider/model selection in Hermes rather
than adding model-specific CE code. Use the same operator-owned credentials model.

For local AWS credentials, follow [the authentication steps](WORKSTATION-HERMES.md#2-authenticate-to-aws-first):
SSO is preferred; long-lived access keys are optional, and temporary credentials
need a session token. AWS credentials and the model API key are separate.

## Your model and credentials

The preview's first-run contract is deliberately narrow: a **custom compatible
API endpoint plus a raw API key**, configured through Hermes. CE does not implement
its own provider SDK or hardcode Qwen. Qwen 3.8 Max is the tested model, not a
bundled service or proof that all models will follow the skills equally well.
The critic uses Hermes's model routing; the default needs no second provider key.

**Workstation environment option:** place your key in the environment variable
named by `model_key_env` before starting the launcher. Use your normal local secret
manager or a private prompt; never put the value in JSON, Git or a shared terminal
capture. In PowerShell 7, a private prompt is:

```powershell
$env:MODEL_API_KEY = Read-Host "Your model API key" -MaskInput
python tools/native_workstation.py run --config .rgce/workstation.json
```

**Workstation Secrets Manager option:** replace `model_key_env` with
`model_secret_arn` in your private launcher JSON. The launcher uses `aws_profile`
and `region` to retrieve SecretString. Your operator needs GetSecretValue on that
secret and, if applicable, permission to decrypt its customer-managed KMS key.
The backend Terraform does not grant this operator permission automatically.
If both options are present, the secret ARN takes precedence.

**Spot:** create a Secrets Manager secret in your deployment region using the
plain-text secret editor, with only the API key as its value (no JSON or newline).
Put only its ARN in private tfvars. The host receives GetSecretValue for that exact
secret. For customer-managed secret encryption, configure `secret_kms_key_arns`
and ensure the KMS key policy permits the host role. A separate generated secret
contains the dashboard login; it is not your provider key. Terraform state contains
the generated dashboard credentials and must remain private.

Keys are delivered into the Hermes process environment. On Spot, the host stages
them in a root-only file under `/run`; locally the launcher creates a private
runtime environment file and removes it on normal stop. Docker/host administrators
are trusted and can inspect process/container configuration. No secret value is
intended to be written to the repository or displayed by normal startup.

Changing a secret value is not a promise of hot rotation: restart through the
relevant launcher/bootstrap workflow and verify a new request. Model fields seed
new profiles; existing profiles retain operator configuration. Change an existing
model through Hermes configuration and keep the key, endpoint and model consistent.

**Subscriptions/OAuth:** CE does not currently guide or test provider browser-login,
subscription-token import or OAuth refresh. A paid chat subscription alone is not
a supported CE credential format. If you want a provider's native Hermes login,
check that specific Hermes integration and provider entitlement first. Do not paste
browser cookies into the key field. That is an advanced, separately validated
configuration, not a promised first-run path. You need not change CE code for the
supported endpoint/key path.

## What you get, and what you do not

**Available:** native Hermes conversation; scoped AWS reads; deterministic records,
counts and receipts; selected organizational knowledge with provenance; bounded AI
critique; CLI/Terraform/CloudFormation proposal guidance; manual Kanban follow-up;
fresh-evidence reassessment and configurable deterministic scheduled checks.

**Not supplied:** model credits; pre-enabled AWS services; automatic organization
account enrollment; automatic cloud fixes; a guarantee of complete coverage from a
bounded read; certified compliance; automated case closure; hosted multi-tenancy;
turnkey OAuth/Confluence synchronization; automatic chat-attachment intake; or a
public production MCP/API/A2A service. Planned interfaces are labeled as proposals.
Enabling extra upstream skills/plugins does not automatically grant CE execution
permission. Read the current capability and release documents before extending it.

## What survives stopping compute

| Data | Workstation | AWS Spot |
|---|---|---|
| Collected AWS records and receipts | S3 | S3 |
| Selected published knowledge | S3 if published; local view if mounted | S3 selected view |
| Conversations, profile and Kanban | Named Docker volume | Retained encrypted EBS |
| Live execution/terminal | Lost when compute stops | Lost on stop or interruption |
| Daily checks | Continue in AWS until disabled | Continue in AWS until disabled |

S3 evidence alone does not restore a conversation. Back up your volume/EBS and private deployment configuration separately. To pause cloud compute use Terraform `running=false`; stopping an individual ASG instance can cause replacement. To pause collection set `schedule_enabled=false` and apply the reviewed plan.

## Privacy of this public preview

The initial public tree was checked using the existing credential shape and private-identifier checks. The count and results belong to each release artifact, not a permanent guarantee for subsequent edits. Private `.rgce` files, AWS credentials,
Terraform state/private inputs and raw acceptance exports were excluded. The
public repository began with the scanned source tree, not the earlier development
history. Public acceptance reports intentionally describe tests and may name Qwen,
show non-secret example paths or test-session references; none supplies usable
model/AWS credentials. A pattern scan is useful evidence, not a guarantee against
every possible secret shape. Keep your own keys, policies, receipts and transcripts
private when reporting issues. Do not share Terraform state or Docker-volume backups.
