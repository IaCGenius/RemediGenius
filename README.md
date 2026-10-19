# RemediGenius Community Edition

**Your cloud's native security tools are powerful. RemediGenius makes them usable.**

Ask questions about your AWS security findings in plain language. Get prioritized,
evidence-backed answers and fix proposals informed by your own policies, then
reassess after your change window.

By design, the agent requests bounded reads from a separate collector with a
configured allowlist. Fixes are proposals you review and apply yourself.

AWS us-east-1 · DeepSeek v4.1 Flash · Self-hosted · Apache-2.0 · [Releases](https://github.com/IaCGenius/RemediGenius/releases)

Provided as-is. You choose your model provider and AWS backend and are responsible
for their configuration, data handling and charges. See [your responsibility](docs/LIMITS.md#your-responsibility).
Validated configuration: AWS us-east-1 and DeepSeek v4.1 Flash. Other supported models are your choice.

![Agent helps identify the decisions needed before preparing a fix](docs/images/hermes-remediation-decisions.jpg)

[Validation record](docs/RELEASE-VALIDATION.md) · GitHub Actions is paused; local checks are recorded separately.
[![Release](https://img.shields.io/github/v/release/IaCGenius/RemediGenius)](https://github.com/IaCGenius/RemediGenius/releases)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

## Architecture

```mermaid
flowchart LR
  U[Operator] --> UI[Hermes dashboard or optional hermes-ui]
  UI --> H[Hermes ce-desk: model and CE skills]
  H --> G[CE scope, workflow and budget checks]
  G --> S[Local Unix socket]
  S --> C[Deterministic Python collector]
  C --> AWS[AWS metadata and security APIs]
  C --> B[Private versioned S3 bucket]
  G --> V[Isolated Linux fix validator]
  H --> D[Retained sessions, cases and model configuration]
  D --> CP[SQLite-aware checkpoint every two minutes]
  CP --> B
  B --> R[Verified restore before Hermes starts]
  R --> D
```

The collector runs on the same compute as Hermes: the Docker workstation or the
Spot EC2 host. It is deterministic Python, not a model, and it writes raw
responses, normalized summaries and receipts to S3. There is no Lambda function
and no EventBridge schedule. The earlier Lambda deployment is archived in the
separate v2 project. Detail: [architecture and recovery boundaries](docs/SINGLE-HOST-MIGRATION.md)
and [capability detail](docs/CURRENT-CE-OFFERING.md).

AWS credentials stay in the collector. On Spot, the instance role supplies the
collector's metadata/security reads plus narrow access to CE's own bucket and
retained EBS volume; Hermes receives no AWS credentials and runs with
`AWS_EC2_METADATA_DISABLED=true`. A model cannot widen its own access by changing
a prompt. See [permissions](docs/IAM.md).

## Deployment

Choose [AWS Spot](deploy/aws-single/README.md) for a persistent browser-accessible
installation, or [Docker workstation](docs/LOCAL-COMPUTE-WORKSTATION.md) to use your
own machine. Both use the same CE profile and deterministic collector.
See the [validation record](docs/RELEASE-VALIDATION.md) for exact test scope.

## Start with a useful question

- **Security posture:** “Read current Security Hub findings. What needs attention first, and what coverage is missing?”
- **Investigation:** “Show EC2 CloudTrail management events for the last five days. State actual time coverage and collection limits.”
- **Remediation:** “Explain this finding using our policy. Prepare a CLI fix, save a case, and help me reassess after our change window.”

## Choose your setup

The guides clone `main`. For a reproducible installation, select the published
release tag you intend to run and record `git rev-parse HEAD` plus the package
SHA-256. Earlier tags retain their original deployment design; do not use their
Terraform state with the single-compute stack.

Inventory is bounded by supported operations, configured scope, permissions and
pagination budgets. A populated Config aggregator and member-account deployment
are not covered by the current acceptance run. See [the validation record](docs/RELEASE-VALIDATION.md).

Hermes is an open-source agent runtime by Nous Research. CE adds the `ce-desk`
profile, scoped AWS tools and readable security skills. Bring a model supported
by Hermes; the tested configuration is DeepSeek v4.1 Flash.

CE reuses Hermes's conversation, skills, model routing and manual Kanban. A small native runtime plugin admits bounded operations and shares retrieved context with a critic. A separate deterministic local collector retrieves AWS records and writes receipts to S3. The model interprets evidence; it does not rewrite source observations or apply customer-cloud fixes.

| | Workstation | Your AWS account |
|---|---|---|
| Hermes compute | Official pinned Docker container | Same container on Spot EC2 |
| Collection and evidence | Local collector and private S3 | Instance-local collector and provisioned private S3 |
| Conversations and cases | Named Docker volume + S3 checkpoints | Retained encrypted EBS + S3 checkpoints |
| Login | Local dashboard, generated credentials | Private SSM tunnel, generated credentials |
| Walkthrough | [Start on your workstation](docs/LOCAL-COMPUTE-WORKSTATION.md) | [Deploy in AWS](deploy/aws-single/README.md) |

Both paths use your AWS and model accounts and incur their charges. Local means local agent compute, not offline. Start with [Start Here](START-HERE.md) and [required inputs and credentials](docs/ONBOARDING.md). The cloud path requires an existing subnet and creates its private bucket; workstation Terraform creates its own storage bucket. Source and Terraform remain inspectable and customizable.

## Offline rule check (no AWS or model needed)

```sh
python -m pip install -e .
python tools/demo.py
```

A clearly labeled synthetic rule example, using Python 3.11+ with no AWS credentials,
model key or cloud deployment. [What this demo shows](docs/DEMO.md). This is not a demonstration of the live agent.

## What you get

[Community skills](docs/COMMUNITY-SKILLS.md) add focused IAM, S3, framework-mapping, CloudTrail, reassessment and case-summary guidance. These are included with receipt-derived collection summaries and a conservative one-page default.

| Included | Boundary |
|---|---|
| Scoped AWS reads, records, counts and receipts | Bounded queries; unavailable services are not healthy services |
| Selected organizational knowledge | Import files, publish/mount a view, show sources and their effect on advice |
| Layered prioritization | Coverage, exposure, business context and existing control metadata; no compliance certification |
| CLI-first remediation proposals | Ask for Terraform/CloudFormation alternatives or source-specific edits; drafts need operator review |
| Saved findings and reassessment | Native manual Kanban and fresh evidence; no automatic closure |
| Configurable daily collection | Deterministic AWS checks on the selected compute; pause when it is off; no unattended model investigation |
| Linux tool validation | Pinned Terraform/AWS provider, AWS CLI and cfn-lint; real diagnostics and up to three correction attempts; no deployment |
| Bounded AI critique | Same loaded references and bounded evidence; not a substitute for tool validation |

See [scope and limits](docs/LIMITS.md) for what is not included and [model/data choices](docs/MODELS.md) before connecting your account.

[Illustrated first-use walkthrough](docs/WALKTHROUGH.md) · [Login and profile screenshots](docs/WALKTHROUGH.md#2-sign-in-and-select-ce-desk)

## Bring context, see it used, return later

1. Ask Hermes what sources and scope it can actually read, then collect one bounded result.
2. Follow [the knowledge walkthrough](docs/NATIVE-KNOWLEDGE-QUICKSTART.md) to import one real policy or ownership note. Generated views are readable; edit originals and re-import rather than editing view hashes. To add a short operator note through chat, ask CE to stage it, review the exact text and scope, then send the returned `publish knowledge <id>` phrase.
3. Ask: “Which knowledge did you use, why does it apply, and what changed in your recommendation?” Conflicts and unknown applicability stay explicit.
4. Prepare a proposal and save it on [native Kanban](docs/OPERATING-LOOP.md). After your change process, return to the case and collect fresh evidence.

## Evidence, limits and project source

- [Release validation](docs/RELEASE-VALIDATION.md) and [upgrade safely](docs/UPGRADING.md)
- [Release scope and known limits](docs/V0.1-RELEASE-PLAN.md)
- [AWS capabilities and scope](docs/AWS-READ-EXECUTION.md)
- [Runtime controls and extension boundaries](docs/CE-RUNTIME.md)
- [Answer format, evidence labels and clear writing](docs/ANSWER-CONTRACT.md)
- [What CE adds to Hermes](docs/CE-PRODUCT-AND-INTEGRATION-CONTRACT.md)
- [Contributing and reporting issues](CONTRIBUTING.md)

| Source | Location |
|---|---|
| Native profile and readable skills | `profiles/ce/desk` |
| Runtime gate and bounded critic | `profiles/ce/desk/plugins/ce-runtime` |
| Deterministic collection | `deploy/collector` |
| Workstation storage / Spot Terraform | `deploy/workstation-storage` / `deploy/aws-single` |
| Launchers and verification | `tools` / `tests` |

Validation is scoped to the documented release baseline. Never include credentials, Terraform state, private policies or unredacted transcripts in public issues.

See [deterministic remediation validation](docs/REMEDIATION-VALIDATION.md) for the pinned tools and validation workflow.

## Optional browser UI

Use the [additional Hermes browser UI](docs/HERMES-UI.md) with the same `ce-desk`
profile, model, skills and knowledge. The native dashboard remains available.
Enable it with `hermes_ui` in your workstation configuration or Spot tfvars.
Known limitations (for example the Bots panel can stay loading; use Sessions) are
being fixed separately and are not part of the current validation claim. See the
guide for setup, login, tested capabilities and known UI limitations.
