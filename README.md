# RemediGenius Community Edition

**Investigate your AWS environment through native Hermes, with scoped execution
and evidence you can inspect.** Self-hosted, AWS-first, Apache-2.0.

Connect existing AWS security tools → collect evidence → apply shared knowledge
→ investigate → prepare a remediation proposal → reassess.

This candidate uses one `ce-desk` profile in the official pinned Hermes container
on AWS Spot. Hermes handles conversation, skills and model selection. A native CE
plugin checks runtime integrity and admits bounded operations; a separate read-only
Lambda collects AWS records and writes receipts to S3.

You can also run that native Hermes profile in local Docker with the same AWS
collector/S3 design. [Workstation acceptance](docs/WORKSTATION-ACCEPTANCE.md)
records the real AWS/Qwen and recovery tests. Neither deployment is fully offline.

## Start here

- [Current offering and architecture](docs/CURRENT-CE-OFFERING.md): a diagram,
  layered assessment, practical knowledge onboarding and the remaining release gates.
- [Latest layered-assessment acceptance](docs/LAYERED-ASSESSMENT-ACCEPTANCE.md):
  real Qwen behavior, independent AWS verification and session reliability tests.

- [Choose workstation or AWS deployment](START-HERE.md): the current native
  Hermes entry points and your first useful investigation.
- [Native Hermes on a workstation](docs/WORKSTATION-HERMES.md): Docker locally,
  scoped collection and durable evidence in your AWS account.
- [Current release gates](docs/V0.1-RELEASE-PLAN.md): implemented scope and remaining
  acceptance/publication work.
- [Daily checks, saved findings and remediation follow-up](docs/OPERATING-LOOP.md):
  configurable scheduling, native Kanban cases and returning to an unapplied fix.
- [Vision checkpoint](docs/VISION-CHECKPOINT.md): what is implemented, what remains
  unfinished, and where to resume after experimenting with the current system.
- [Resume handoff](docs/RESUME-HANDOFF.md): saved state, reconnect after reboot,
  verification results and the agreed next work.
- [Knowledge staging, visible use and control mapping](docs/KNOWLEDGE-USE-AND-CONTROL-MAPPING.md):
  what to supply, what the agent used, and current versus proposed framework mapping.
- [What CE adds, integrations and decision lifecycle](docs/CE-PRODUCT-AND-INTEGRATION-CONTRACT.md):
  Hermes versus CE, extension points, proposed MCP/API/A2A contracts, new-account
  value, false positives and posture-change revalidation; implemented versus planned.
- [Deploy and connect](docs/NATIVE-CE-QUICKSTART.md): prerequisites, Terraform,
  login and your first investigation.
- [Runtime controls](docs/CE-RUNTIME.md): enforcement outside the model,
  limits, evidence review, logs and upgrades.
- [AWS capabilities](docs/AWS-READ-EXECUTION.md): sources, account onboarding,
  selected knowledge and collection limits.
- [Acceptance results](docs/CE-RUNTIME-ACCEPTANCE.md): real AWS/Qwen tests and gaps.
  A listed SDK operation is not proof of live validation.
- [Remediation skill acceptance](docs/REMEDIATION-SKILL-ACCEPTANCE.md): CLI-first
  fix preparation, Terraform/CloudFormation follow-ups and live-Qwen corrections.

## What you can do

Investigate current Security Hub findings, recent EC2 CloudTrail management events,
EC2 inventory across configured accounts, and supported AWS security service
metadata. Reassess a prior Security Hub snapshot with a deterministic comparison.
Answers separate AWS facts, deterministic summaries, organization context and AI
interpretation. A bounded model critique checks the draft; it does not certify it.

Publish only the knowledge view relevant to this agent. Readable Markdown and
metadata stay separate from source findings. No policy is invented when none was
supplied. Evidence and published knowledge live in S3; sessions and configuration
live on retained encrypted EBS. EBS retention is not a cross-region backup.

## Candidate scope

Cloud reads and proposals only. No automatic remediation, arbitrary generated
collectors, Security Lake record queries, universal repository OAuth or automatic
organization-wide account onboarding. Additional plugins are operator extensions;
their execution paths must be admitted and tested explicitly.

Use your chosen Hermes-compatible provider and credentials. Qwen is the validation
backend, not a hardcoded dependency. Model and AWS charges remain yours.
Publication awaits the owner's review of acceptance evidence.

| Component | Location |
|---|---|
| Profile and skills | `profiles/native-sketch/desk` |
| Runtime gates and bounded review | `profiles/native-sketch/desk/plugins/ce-runtime` |
| Deterministic AWS collection | `modules/aws-read-executor` |
| Spot, IAM and deployment | `deploy/aws-native-sketch` |
| Package and profile upgrades | `tools` |
| Verification | `tests`, `docs` |

The earlier custom console remains preserved. Its Docker Compose workflow is in
[legacy console material](docs/LEGACY-CONSOLE-README.md); it does not launch this
native Hermes candidate.
