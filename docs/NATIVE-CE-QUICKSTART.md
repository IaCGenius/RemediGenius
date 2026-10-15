# Deploy the native Hermes CE candidate

This is the current cloud entry point. Docker Compose at the repository root
starts the preserved console, not this agent.

For local native Hermes instead, use [the workstation guide](WORKSTATION-HERMES.md).
Both modes use the same CE profile and scoped AWS collector. The workstation mode
needs Docker and an AWS backend; the cloud mode below needs an existing bucket and
subnet and adds Spot compute with retained EBS.

## 1. Get the source, authenticate and choose inputs

Preview baseline: **AWS `us-east-1`, Qwen 3.8 Max, one `ce-desk` profile**.
Use Git, Python 3.11+, Terraform 1.10+, AWS CLI and the AWS Session Manager plugin.
The commands below use PowerShell. Work from the repository root:

```powershell
git clone https://github.com/IaCGenius/RemediGenius.git
cd RemediGenius
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[aws,documents]"
New-Item -ItemType Directory -Force .rgce | Out-Null
aws configure sso --profile ce-operator
aws sso login --profile ce-operator
$env:AWS_PROFILE = "ce-operator"
aws sts get-caller-identity
```

Use your actual SSO settings. Existing named AWS credential profiles also work;
see [AWS authentication](WORKSTATION-HERMES.md#2-authenticate-to-aws-first).
Confirm the returned account is the one you intend to provision. The operator
needs provisioning rights for IAM, Lambda, S3 uploads, EC2/Auto Scaling, EBS,
Secrets Manager and the optional schedule, plus SSM access for the tunnel.
The agent is not given those operator credentials.

Prepare an existing subnet with outbound Internet and an existing private S3 bucket
in `us-east-1`. Enable S3 Block Public Access, bucket versioning and default
encryption, and require HTTPS in its bucket policy. Preserve the bucket independently
of disposable compute; choose your retention policy deliberately. This stack does
not create or configure that existing bucket. Choose a dedicated workspace prefix
and stack name. Terraform
creates scoped IAM, Lambda, a Spot ASG, retained encrypted EBS and a dashboard
secret; it does not create the bucket or VPC. Protect Terraform state: it contains
the generated dashboard login. Review [all input meanings](PREVIEW-ONBOARDING.md#inputs-and-what-they-control).

The default Spot pool offers `t3.medium` and `t3a.medium` (2 vCPU, 4 GiB RAM),
using price-capacity-optimized selection and a 3 GiB container memory limit.
The CE compatibility overlay bounds native dashboard terminals to two, with a
ten-minute detached TTL. It checks the exact upstream source before applying;
an image update needs overlay review. Finish a run before starting another chat.
Saved conversations remain on EBS; live terminals are disposable.
Set `spot_instance_types` to compatible x86 Nitro types available in your subnet's
Availability Zone; these explicit overrides take precedence over `instance_type`.
Set the list to `[]` to use only `instance_type`. Keep host memory above
`container_memory_mb`. The retained session volume pins this deployment to one
Availability Zone; instance diversity does not provide cross-zone failover or
guarantee Spot capacity. ARM types require a separately validated image/bootstrap.

Create a Secrets Manager secret containing your provider API key as plain text.
Supply its ARN, compatible HTTPS endpoint and model name. Do not put the key in
Git, tfvars or chat. Check that your provider permits this use and data scope.
The model receives selected AWS records and knowledge needed for the question.

## 2. Package and launch

1. Read `deploy/aws-native-sketch/README.md` and the IAM/module source.
2. Package this checkout:

   ```powershell
   python tools/package_native_hermes.py --output .rgce/native-source.zip
   ```

3. Read `deploy/aws-native-sketch/terraform.tfvars.example` for all configurable
   settings. Create `.rgce/aws.tfvars.json` using the following JSON shape. Replace
   **every** uppercase placeholder; use your packaged digest for both digest fields.
   JSON is supported by Terraform and by the knowledge publisher later. Do not
   copy HCL syntax from `.tfvars.example` into a JSON file.

   ```json
   {
     "account_id": "YOUR_ACCOUNT_ID",
     "region": "us-east-1",
     "name": "rgce-native",
     "subnet_id": "YOUR_SUBNET_ID",
     "bucket_name": "YOUR_PRIVATE_BUCKET",
     "workspace_prefix": "ce-preview",
     "running": true,
     "source_archive_key": "native-source/YOUR_DIGEST.zip",
     "source_archive_sha256": "YOUR_DIGEST",
     "model_secret_arn": "YOUR_SECRET_ARN",
     "model_name": "qwen3.8-max",
     "model_base_url": "https://YOUR_PROVIDER/v1",
     "schedule_enabled": true,
     "schedule_interval_hours": 24
   }
   ```

   This walkthrough explicitly enables daily bounded AWS collection. Set
   `schedule_enabled` to false before applying if you do not want background reads.
   The underlying Spot Terraform default remains off. Confirm your provider's
   Qwen model identifier and endpoint; no key is bundled.
4. Upload the archive with your normal AWS operator credentials:

   ```powershell
   aws s3 cp .rgce/native-source.zip s3://YOUR_BUCKET/native-source/DIGEST.zip
   $inputs = (Resolve-Path .rgce/aws.tfvars.json).Path
   $plan = Join-Path (Resolve-Path .rgce).Path "aws.tfplan"
   terraform -chdir=deploy/aws-native-sketch init
   terraform -chdir=deploy/aws-native-sketch plan "-var-file=$inputs" "-out=$plan"
   # Review resources and permissions before applying the saved plan.
   terraform -chdir=deploy/aws-native-sketch apply $plan
   ```

   Set `running=true` in the reviewed inputs to launch. Start with one account
   in `us-east-1`. Source download/hash verification and image startup take several
   minutes. No inbound security-group port is opened; dashboard access is through SSM.
5. Wait for the instance to become available to SSM, then follow the login sequence below.

## 3. Retrieve your login, open the tunnel and select ce-desk

In a private PowerShell terminal at this checkout, using the same authenticated
AWS operator profile:

```powershell
$env:AWS_PROFILE = "ce-operator"
.\tools\open-native-hermes.ps1 -Region us-east-1 -Name rgce-native -WithLogin
```

Replace `rgce-native` if you chose another stack name. The helper displays the
**dashboard** username/password from `<name>/dashboard` in Secrets Manager and
opens a localhost SSM tunnel. It does not show the model API key. Leave the terminal
open; do not record it in screenshots. Your identity needs secret-read access to
that dashboard secret, Auto Scaling discovery and SSM session access.

1. Open `http://127.0.0.1:9121/chat?profile=ce-desk`.
2. Enter the displayed dashboard username and password.
3. Confirm **ce-desk** in Chat; start a new conversation.
4. Keep the tunnel running. After a laptop reboot or Spot replacement, rerun the
   helper; it discovers the current instance instead of keeping a stale instance ID.

![Native Hermes login form; use your own generated dashboard credentials](images/hermes-login.jpg)

![Select the single CE profile, ce-desk, in native Hermes Chat](images/hermes-profile-selector.jpg)

Continue with [the illustrated first investigation and knowledge walkthrough](MVP-WALKTHROUGH.md).

Use `-ShowLogin` to retrieve only the login, or omit both login switches to open
only a tunnel. If connection fails, first confirm `running=true`, a healthy SSM
instance, a free local port and your unexpired AWS login. A changed source image
can take several minutes to download; refresh after startup completes.

## 4. Get your first useful result

Ask: “What configured targets and operations can you use? Distinguish configured
scope from successfully collected data. Is selected organization knowledge supplied?”

Then: “Read current ACTIVE Security Hub findings for default in my region, at
most two pages. Preserve AWS severity, cite receipts, state missing coverage,
and propose three concrete next steps. Do not change resources.”

Then: “Repeat the identical query and compare it with that receipt. Do not assume
any fix happened.”

For activity: “Read EC2 CloudTrail management events over the last five days,
at most two pages. Give exact returned counts, API errors and actual time coverage.”
Two pages may cover only minutes. CloudTrail Event History is not S3 data-event
history. A denied/disabled source should produce an honest limitation, not findings.

## 5. Add your knowledge, then additional accounts

Start with [one real policy in the knowledge walkthrough](NATIVE-KNOWLEDGE-QUICKSTART.md). Import, preview and publish a selected view, then set `knowledge_view` in your private Terraform inputs and review/apply the plan. Use `.rgce/aws.tfvars.json` as the publisher's `--config` file; it reads only destination fields. Keep the same `AWS_PROFILE` environment selection. Copy the returned `knowledge_view` into that JSON and review/apply a new Terraform plan. If you instead used HCL `.tfvars`, create a separate ignored JSON file with `region`, `bucket_name` and `workspace_prefix` for the publisher; do not pass HCL to a JSON reader.
Supply readable Markdown with source, applicability and dates; keep scoped
exceptions explicit. Operating instructions are not your company's security policy.

For another account, deploy `member-read-role.json` there with the exact CE
executor role ARN, external ID and regions. Add the role under `aws_read_targets`,
then review/apply the Terraform plan. The agent never receives an administrator role.

Find the execution role with your operator CLI (replace the name/region if changed):

```sh
aws lambda get-function-configuration --function-name rgce-native-aws-read --region us-east-1 --query Role --output text
```

This reads Lambda configuration; it does not change permissions. Use that role,
not the host role or reader-invoker role, as the member template's `ExecutorRoleArn`.

## 6. Upgrade, stop and recover

Use [runtime controls](CE-RUNTIME.md) for explicit retained-profile upgrades.
Restarting with a new archive preserves operator configuration; it intentionally
does not silently overwrite skills. Preflight blocks mismatched reviewed files.

After deploying a new pinned archive, use a root SSM shell on the CE host during
a maintenance window (this is an operator command, not an agent tool):

```sh
docker exec -i --user 10000:10000 rgce-native /opt/hermes/.venv/bin/python - --home /opt/data/profiles/ce-desk --guard-default < /opt/rgce-native/source/tools/upgrade_native_profile.py
systemctl restart rgce-native.service
```

Wait until the container is running before the upgrade. The utility prints the
backup directory; keep it for rollback. Open a new chat after restart.

To stop compute, set `running=false` and apply the plan. Stopping EC2 alone causes
ASG replacement. S3 evidence, the session EBS volume and secrets remain and can
incur charges. Keep backups according to your needs; no session snapshot schedule
or cross-region recovery is configured. Do not delete the retained EBS volume to
repair startup. Read [acceptance results](CE-RUNTIME-ACCEPTANCE.md) before sharing.

During onboarding, choose whether to enable daily collection. It is separately opt-in: set `schedule_enabled=true` and
`schedule_interval_hours=24`, then review/apply. Lower the interval for more frequent
checks (minimum one hour). It keeps running when Spot is stopped. Set
`schedule_enabled=false` too if you want all scheduled collection paused. See
[daily checks and saved findings](OPERATING-LOOP.md) for scope and follow-up.
