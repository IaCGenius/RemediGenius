# Native Hermes CE sketch

An independent Spot host running the pinned official Hermes gateway, with one native `ce-desk` profile. No custom CE console, builder, or scheduled model work. Hermes receives temporary credentials restricted to invoking the CE read executor and reading its evidence prefix. This stack does not modify the earlier CE cloud workspace or the v2 engine.

Required inputs: `account_id`, `region`, `subnet_id`, `bucket_name`, a new `workspace_prefix`, `source_archive_key`, `source_archive_sha256`, `model_secret_arn`, `model_name`, and `model_base_url`. The source ZIP must contain this bootstrap, `profiles/native-sketch/desk` and `tools/native_sketch_data.py` at their repository-relative paths. Terraform separately packages `modules/native-source-discovery` and `modules/aws-read-executor` for Lambda. Upload only reviewed source, with no state, secrets or private fixtures. Bootstrap verifies the exact ZIP digest before extraction. The official `hermes_image` defaults to the existing CE upstream digest pin.

`running=false` is the default. Set it true in private tfvars, review a Terraform plan, then apply to start the new ASG. The subnet must have outbound Internet connectivity; this sketch assigns a public IPv4 address but opens no inbound ports. It uses one x86 Spot instance (`t3.large` by default), with maximum ASG capacity one. Spot availability in the chosen subnet is not guaranteed.

The discovery module collects a bounded source-availability catalogue in the selected account and region. Bootstrap invokes it once through host IAM. A host-only timer hydrates verified S3 records every 30 seconds into `/data/shared`, mounted **read-only** at `/opt/data/shared` for Hermes. This timer performs no model calls and does not recollect the account. The `ce-aws-read` skill invokes a separate read-only Lambda executor using the AWS SDK. Its operation manifest controls supported calls; configured targets and IAM constrain accounts and regions. Returned source responses and deterministic summaries go to S3 with timestamps, hashes and receipts. The skill can read its exact result directly from S3 without waiting for the cache. Native terminal access does not confer the host's AWS role.

S3 is authoritative for collected evidence, normalized records, receipts and catalogue. A separate encrypted EBS volume preserves the native Hermes home, sessions and working files; it is not a substitute for S3 evidence storage or a claim that sessions are backed up to S3. The volume has `prevent_destroy` and is retained when compute stops. No snapshot schedule is configured in this sketch. Replacement waits for the old host to release the volume and never force-detaches it; unavailable or unrecognized state fails closed.

Model credentials are read from the exact existing Secrets Manager ARN into root-only tmpfs and passed to Hermes as `MODEL_API_KEY`. A new dedicated dashboard secret is generated for this stack. Its generated values exist in private Terraform state, so protect state as well as tfvars. No credentials are printed as outputs; `dashboard_secret_arn` identifies where the operator retrieves the login privately.

Connect through SSM port forwarding to host loopback port 9120, then use Hermes Desktop's Remote Gateway or the native dashboard with the new login. Select `ce-desk`; the unconfigured upstream default profile is not the CE entry point. Profile source files remain readable under `profiles/native-sketch`; they are installed through native `hermes profile install/update`, not rewritten into another agent framework.

The dedicated Docker bridge denies metadata/private destinations and new agent-to-host connections. Replies to host-initiated gateway connections are allowed. DNS is permitted only to the host-configured resolver, with public HTTPS for model access. These are access boundaries, not an exfiltration-proof sandbox. CE uses one profile for summaries and investigations; it is not a security tenant boundary. Builder and its permissions are absent.

Stop by setting `running=false` and applying a reviewed plan. Stopping an individual EC2 instance is insufficient because the ASG can replace it. The evidence bucket, retained session volume and dashboard secret remain and may incur storage charges. Bootstrap/systemd definitions and provider lockfiles are included for review. Terraform validation does not prove live gateway, profile, model or recovery behavior; record those acceptance results separately.


## Live AWS investigations

See [AWS read execution](../../docs/AWS-READ-EXECUTION.md) for onboarding, supported operations, limits, multi-account roles, selected knowledge and actual acceptance results. The checked-in skill uses the boto3 already installed in the pinned Hermes image. It does not install an external SaaS integration or expose host administrator credentials.

Set `aws_read_targets` to an explicit map of account aliases, account IDs, regions and optional role ARNs/external IDs. An empty map uses this deployment's account and region. For another account, deploy `member-read-role.json` there with the exact executor role ARN, an external ID and allowed regions; configure its output role ARN as a target. Existing Security Hub administrator and Config aggregator endpoints can also return member records: preserve record account IDs and distinguish their coverage from the configured target.

An optional `knowledge_view` selects `s3://BUCKET/PREFIX/knowledge/VIEW/`. Publish only the intended view using the existing knowledge-library export, then upload that directory. The host syncs this selected prefix to the read-only `/opt/data/shared/knowledge` cache. It never uploads or treats all organizational documents as global policy automatically.

Existing retained profiles are deliberately preserved on restart. Source updates must be applied explicitly with a backup; a new launch template alone does not overwrite operator customization.
