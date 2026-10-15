# Deploy the native Hermes CE candidate

This is the current cloud entry point. Docker Compose at the repository root
starts the preserved console, not this agent.

For local native Hermes instead, use [the workstation guide](WORKSTATION-HERMES.md).
Both modes use the same CE profile and scoped AWS collector. The workstation mode
needs Docker and an AWS backend; the cloud mode below needs an existing bucket and
subnet and adds Spot compute with retained EBS.

## Prerequisites and scope

For the existing deployment, show the dashboard username/password and open the
tunnel together from your private PowerShell terminal:

```powershell
C:\work\remedigenius-community\tools\open-native-hermes.ps1 -WithLogin
```

Open http://127.0.0.1:9121 and leave that terminal running. The script retrieves
the dashboard credentials from AWS Secrets Manager using your current AWS login.
Use `-ShowLogin` for credentials only. Neither option retrieves the model API key.
Do not capture this terminal in shared screenshots or test logs.

Use Python 3.11+, Terraform, AWS CLI and the AWS Session Manager plugin. Choose
one AWS region, an existing subnet with outbound Internet, an existing private S3
bucket, a new workspace prefix and a dedicated stack name. The stack creates IAM,
Lambda, a Spot ASG, retained encrypted EBS and a dashboard secret; it does not
create the bucket or VPC. Protect Terraform state: it contains the dashboard login.

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

## Package and launch

1. Read `deploy/aws-native-sketch/README.md` and the IAM/module source.
2. Package this checkout:

   ```powershell
   python tools/package_native_hermes.py --output .rgce/native-source.zip
   ```

3. Copy `deploy/aws-native-sketch/terraform.tfvars.example` to an ignored private
   file. Replace all placeholders. Set `source_archive_sha256` to the printed
   digest and use `native-source/DIGEST.zip` as its immutable upload key.
4. Upload the archive with your normal AWS operator credentials:

   ```powershell
   aws s3 cp .rgce/native-source.zip s3://YOUR_BUCKET/native-source/DIGEST.zip
   terraform -chdir=deploy/aws-native-sketch init
   terraform -chdir=deploy/aws-native-sketch plan -var-file=YOUR_ABSOLUTE_PRIVATE_TFVARS -out=YOUR_ABSOLUTE_PLAN
   terraform -chdir=deploy/aws-native-sketch apply YOUR_ABSOLUTE_PLAN
   ```

   Set `running=true` in the reviewed inputs to launch. Start with one account
   and region. Source download/hash verification and image startup take several
   minutes. No inbound security-group port is opened; dashboard access is through SSM.
5. In one terminal run `tools/open-native-hermes.ps1`. In another, run it with
   `-ShowLogin` to display your private dashboard credentials. Add `-Region` and
   `-Name` if you changed defaults. Sign in at http://127.0.0.1:9121 and select
   `ce-desk`. Keep the tunnel open; reconnect after Spot replacement.

## First useful checks

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

## Add context and accounts

Use a selected `knowledge_view` as described in [AWS read execution](AWS-READ-EXECUTION.md).
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

## Upgrade, stop and recover

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

Daily collection is separately opt-in: set `schedule_enabled=true` and
`schedule_interval_hours=24`, then review/apply. Lower the interval for more frequent
checks (minimum one hour). It keeps running when Spot is stopped. Set
`schedule_enabled=false` too if you want all scheduled collection paused. See
[daily checks and saved findings](OPERATING-LOOP.md) for scope and follow-up.
