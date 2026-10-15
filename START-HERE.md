# Try native RemediGenius CE

Use your existing AWS security services through one Hermes agent. Collect scoped
evidence, understand a finding, prepare a fix, save it for your change process,
and return later to reassess. This is a single-operator community release.

**Validated release baseline: AWS `us-east-1`, Qwen 3.8 Max, one `ce-desk` profile.** Other configured regions/models are operator experiments, not release acceptance scope.

See [current offering and release gates](docs/CURRENT-CE-OFFERING.md) and the
[current architecture diagram](docs/diagrams/ce-mvp-architecture.html).

Read [the preview setup and credential contract](docs/PREVIEW-ONBOARDING.md) for required inputs,
regions, model access, storage, and what this preview does not provide.

## Choose where Hermes runs

| | Your workstation | Your AWS account |
|---|---|---|
| Agent | Official pinned Hermes Docker image | Same image on Spot EC2 |
| Collection | Scoped Lambda in your AWS account | Scoped Lambda in your AWS account |
| Evidence | Private versioned S3 | Private S3 |
| Conversations/cases | Named Docker volume | Retained encrypted EBS |
| Access | Loopback dashboard | Private SSM tunnel |
| Daily checks | EventBridge, independent of workstation | EventBridge, independent of Spot |
| Start | [Workstation guide](docs/WORKSTATION-HERMES.md) | [AWS guide](docs/NATIVE-CE-QUICKSTART.md) |

Both need your AWS access and a permitted Hermes-compatible model/provider key.
Neither is offline. Model/AWS charges are yours. The workstation backend creates
its bucket; the Spot deployment needs an existing bucket and subnet with outbound
access. Account/region onboarding is explicit. Start with one account in `us-east-1`.

## Sign in, then start with ce-desk

The deployment guide creates your own dashboard login. It is separate from AWS credentials and your model API key. Retrieve it privately using the local `login` command or cloud tunnel `-WithLogin`, sign in, and open Chat with `profile=ce-desk`. Do not paste credentials into chat. Keep the launcher/tunnel running while using the dashboard.

See [the illustrated first investigation and knowledge walkthrough](docs/MVP-WALKTHROUGH.md) for the actual UI.

## First useful investigation

1. Ask what sources, account aliases and regions are configured versus actually
   tested. Configured access is not a collected finding.
2. Ask for a bounded Security Hub or Config read with scope, observation time and
   receipt. Missing/disabled services should be reported honestly.
3. Ask for a CLI-first fix proposal, or Terraform/CloudFormation if supported.
   Some settings cannot be represented in every format. Review prerequisites,
   ownership, provider validation and rollback before acting outside CE.
4. Ask to save an actionable case on Kanban. A waiting case is not a fixed finding.
5. Return to its case ID, collect fresh evidence and decide whether to close it.

The agent does not apply customer-cloud fixes. Daily checks do not call a model
or automatically resolve cases. Kanban is manual tracking with worker dispatch
disabled. Read [the operating loop](docs/OPERATING-LOOP.md).

## Bring your context

Start with [the simple knowledge guide](docs/NATIVE-KNOWLEDGE-QUICKSTART.md).
Import only relevant documents into a readable selected view; see
[knowledge staging](docs/KNOWLEDGE-USE-AND-CONTROL-MAPPING.md). Include scope,
ownership and policy dates when known. Ask “What knowledge did you use, and how
did it affect this recommendation?” Conflicting or missing policy remains visible.
CE operating guidance is not your organization's AWS policy.

## Before sharing or upgrading

Read [acceptance and remaining limits](docs/V0.1-RELEASE-PLAN.md), keep private
credentials/state/transcripts out of shared files, and back up your Docker volume
or EBS plus deployment configuration. S3 evidence alone does not restore chat.
Review source changes before using the explicit workstation `--upgrade` option.

Legacy console and prototype deployments are archived outside this release.
Use the two native setup guides above.
