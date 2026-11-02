# AWS connections for CE

Unreleased, evaluated on the disposable Spot lab on 2026-11-02 (UTC).

The standard EC2 deployment uses **managed AWS MCP investigation transport by default** behind the existing `rg_triage aws` command.
The operator reuses an explicit audit role; the agent does not receive AWS credentials, a script interpreter,
or another collection of AWS tools. Scheduled collection, scoring and storage remain on the direct SDK path.

## Deployment defaults

| Deployment | Recommended starting point | Optional next step |
| --- | --- | --- |
| CE on AWS | Managed MCP using the existing audit role; no extra sign-in | Installed automatically at boot; installer below is for repair/rollback |
| Individual workstation | Existing AWS SSO profile plus explicit scoped audit role | Install the `aws-mcp` package extra in the desk environment and opt in via triage.yaml |
| Standalone native MCP client | Restricted identity, official vendor connection | OAuth can simplify sign-in, but CE/Hermes OAuth onboarding is not yet certified |
| Multiple accounts | Existing member-role onboarding and explicit target account | Managed reads use that selected role; no implicit default when several accounts are available |

On the standard AWS host, from the unpacked release source:

```sh
sudo bash deploy/aws-single/install-aws-investigation.sh enable
```

The installer preserves installed dependency versions, installs `mcp-proxy-for-aws==1.7.0`, backs up the profile,
and selects the transport. It does not modify IAM. An existing native MCP connection is not needed for this path.
Use `disable` to return interactive reads to direct SDK. Existing AWS credential sources stay unchanged.
For other deployments, install `remedigenius-community[aws-mcp]` and configure:

```yaml
aws_investigation:
  transport: managed_mcp  # standard EC2 deployment default
  endpoint_region: us-east-1
```

Every selected account needs an explicit `role_arn`. The endpoint region selects the managed service; the
read's region selects the actual resources. Credentials are assumed afresh per invocation in the desk.
Run `doctor` to see configuration and account coverage, then verify one real read such as
`aws ec2 describe_regions --region us-east-1`. The evidence line must identify `transport managed AWS MCP`.
Configuration, handshake and successful evidence are deliberately separate checks.

## Why a bounded transport

The live managed server exposes `aws___run_script` with `readOnlyHint=false` and `destructiveHint=true`.
AWS's proxy `--read-only` would remove this tool, so that flag alone cannot provide account investigation.
CE resolves the requested operation against the installed SDK model, applies its existing read/sensitive-data
guards and parameter validation, and constructs one fixed `call_boto3` expression with JSON-encoded data.
No model-authored code or endpoint is accepted. AWS's official library supplies SigV4/MCP transport; CE does
not implement service-specific connectors or its own signing protocol. Existing audit-role IAM still applies.

The response must have a successful body status, a structured result, and matching successful API execution
records. `isError=false` alone is insufficient (observed live with invalid sandbox code). Warnings, pending
tasks, mismatched records and malformed output are rejected. Vendor exception bodies are not echoed.
Requests have a 55-second transport deadline. There is no automatic direct replay, no credential fallback and
no automatic permission expansion. The managed service auto-paginates with a cap; CE labels completeness
unverified even if it returns no continuation token. This does not replace collection's coverage accounting.

## Prompt size and useful integrations

The account transport adds **zero model-facing tool schemas**. The existing small routing skill loads
`references/aws-connection.md` only for connection/access questions. AWS documentation and specialist skills
remain on-demand through the public AWS Knowledge connection. No full vendor skill/catalog copy is injected.
Keep public Knowledge available independently: account credential expiry must not break public guidance.
Do not enable a duplicate authenticated documentation catalog alongside it.

| Candidate | Use only when this gap exists | Default |
| --- | --- | --- |
| Managed AWS MCP | Structured live configuration reads through the desk | Standard EC2 path, qualified on lab |
| Managed EKS/ECS | Cluster/container investigation beyond the desk's metadata reads | Not installed; scope Kubernetes access and log/data permissions separately |
| Managed SageMaker | ML-specific operations beyond security triage | Not installed |
| AWS Labs CloudWatch/CloudTrail | A required supported diagnostic workflow unavailable through existing reads | Not installed; log content is outside the current metadata boundary |
| AWS Pricing / Billing | Cost of a proposed change / actual spend | Separate opt-in workflows; price is not observed spend |
| Bedrock Knowledge Base retrieval | Existing user-selected knowledge base | Separate knowledge access; no blanket S3 object permission |
| AWS Knowledge skills | Task-specific AWS procedure | Retrieve only the relevant skill/reference |

AWS-managed remote services and AWS Labs installable MCP servers have different hosting/authentication models.
Do not enable the entire catalog. A new integration must answer a concrete question, have a bounded identity,
and pass a representative read. Cloud evidence remains time-bound; OKF policies/runbooks require review.

## Failure and release gates

Expired sessions, access denials, SCP restrictions, endpoint outages, unknown SDK operations and pending MCP
tasks mean **missing evidence**, never a healthy resource. The current board remains readable and direct
collection continues. After Spot replacement, bootstrap reinstalls the default pinned dependencies; failure
is reported and collection still starts. The operator can repair dependencies or explicitly disable MCP.

The packaged candidate passed fresh-host bootstrap and Spot replacement on the existing lab, including
dependency installation, a real managed read and refusal of writes/secret reads. Details and limits are in
[release validation](RELEASE-VALIDATION.md). The host installer constrains resolution against both existing
pins and the tested Linux dependency snapshot (`aws-mcp-constraints.txt`); conflicts fail rather than upgrade
core packages. New-stack creation from zero, long-running credential expiry, multi-account managed transport,
endpoint outage and large-result pagination remain separate validation limits. OAuth is not claimed as tested.

Sources reviewed:
- [AWS setup and authentication](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/getting-started-aws-mcp-server.html)
- [Managed tool contract](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/understanding-mcp-server-tools.html)
- [AWS authorization model](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/security_iam_service-with-iam.html)
- [Official proxy library](https://github.com/aws/mcp-proxy-for-aws)
- [AWS Labs catalog](https://awslabs.github.io/mcp/)
