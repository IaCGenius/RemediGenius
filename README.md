# RemediGenius Community Edition

**Your cloud's native security tools are powerful. RemediGenius makes them usable.**

Ask questions about your AWS security findings in plain language. Get prioritized,
evidence-backed answers and fix proposals informed by your own policies, then
reassess after your change window.

By design, the agent requests bounded reads from a separate collector with a
configured allowlist. Fixes are proposals you review and apply yourself.

AWS us-east-1 · DeepSeek v4.1 Flash · Self-hosted · Apache-2.0 · [v0.1.3](https://github.com/IaCGenius/RemediGenius/releases/tag/v0.1.3)

Provided as-is. You choose your model provider and AWS backend and are responsible
for their configuration, data handling and charges. See [your responsibility](docs/LIMITS.md#your-responsibility).
Validated configuration: AWS us-east-1 and DeepSeek v4.1 Flash. Other supported models are your choice.

![Agent helps identify the decisions needed before preparing a fix](docs/images/hermes-remediation-decisions.jpg)

[![CI](https://github.com/IaCGenius/RemediGenius/actions/workflows/community.yml/badge.svg)](https://github.com/IaCGenius/RemediGenius/actions/workflows/community.yml)
[![Release](https://img.shields.io/github/v/release/IaCGenius/RemediGenius)](https://github.com/IaCGenius/RemediGenius/releases)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

![CE architecture: user and selected knowledge through Hermes, scoped execution, durable evidence and follow-up](docs/diagrams/ce-mvp-architecture.png)

[Explore the architecture](docs/diagrams/ce-mvp-architecture.html) · [Architecture and capability detail](docs/CURRENT-CE-OFFERING.md)

## Start with a useful question

- **Security posture:** “Read current Security Hub findings. What needs attention first, and what coverage is missing?”
- **Investigation:** “Show EC2 CloudTrail management events for the last five days. State actual time coverage and collection limits.”
- **Remediation:** “Explain this finding using our policy. Prepare a CLI fix, save a case, and help me reassess after our change window.”

## Choose your setup

Hermes is an open-source agent runtime by Nous Research. CE adds the `ce-desk`
profile, scoped AWS tools and readable security skills. Bring a model supported
by Hermes; the tested configuration is DeepSeek v4.1 Flash.

CE reuses Hermes's conversation, skills, model routing and manual Kanban. A small native runtime plugin admits bounded operations and shares retrieved context with a critic. Separate deterministic Lambda collectors retrieve AWS records and write receipts to S3. The model interprets evidence; it does not rewrite source observations or apply customer-cloud fixes.



| | Workstation | Your AWS account |
|---|---|---|
| Hermes compute | Official pinned Docker container | Same container on Spot EC2 |
| Collection and evidence | AWS Lambda and private S3 | AWS Lambda and private S3 |
| Conversations and cases | Named Docker volume | Retained encrypted EBS |
| Login | Local dashboard, generated credentials | Private SSM tunnel, generated credentials |
| Walkthrough | [Start on your workstation](docs/WORKSTATION-HERMES.md) | [Deploy in AWS](docs/NATIVE-CE-QUICKSTART.md) |

Both paths use your AWS and model accounts and incur their charges. Local means local agent compute, not offline. Start with [Start Here](START-HERE.md) and [required inputs and credentials](docs/ONBOARDING.md). The cloud path requires an existing subnet and private bucket; the workstation Terraform creates its own evidence bucket. Source and Terraform remain inspectable and customizable.

## Offline rule check (no AWS or model needed)

```sh
python -m pip install -e .
python tools/demo.py
```

A clearly labeled synthetic rule example, using Python 3.11+ with no AWS credentials,
model key or cloud deployment. [What this demo shows](docs/DEMO.md). This is not a demonstration of the live agent.

## What you get

[Community skills](docs/COMMUNITY-SKILLS.md) add focused IAM, S3, framework-mapping, CloudTrail, reassessment and case-summary guidance. These are included in v0.1.3, together with receipt-derived collection summaries and a conservative one-page default.

| Included in v0.1.3 | Boundary |
|---|---|
| Scoped AWS reads, records, counts and receipts | Bounded queries; unavailable services are not healthy services |
| Selected organizational knowledge | Import files, publish/mount a view, show sources and their effect on advice |
| Layered prioritization | Coverage, exposure, business context and existing control metadata; no compliance certification |
| CLI-first remediation proposals | Ask for Terraform/CloudFormation alternatives or source-specific edits; drafts need operator review |
| Saved findings and reassessment | Native manual Kanban and fresh evidence; no automatic closure |
| Configurable daily collection | Deterministic AWS checks, independent of agent compute; no unattended model investigation |
| Linux tool validation | Pinned Terraform/AWS provider, AWS CLI and cfn-lint; real diagnostics and up to three correction attempts; no deployment |
| Bounded AI critique | Same loaded references and bounded evidence; not a substitute for tool validation |

See [scope and limits](docs/LIMITS.md) for what is not included and [model/data choices](docs/MODELS.md) before connecting your account.

[Illustrated first-use walkthrough](docs/WALKTHROUGH.md) · [Login and profile screenshots](docs/NATIVE-CE-QUICKSTART.md#3-retrieve-your-login-open-the-tunnel-and-select-ce-desk)

## Bring context, see it used, return later

1. Ask Hermes what sources and scope it can actually read, then collect one bounded result.
2. Follow [the knowledge walkthrough](docs/NATIVE-KNOWLEDGE-QUICKSTART.md) to import one real policy or ownership note. Generated views are readable; edit originals and re-import rather than editing view hashes.
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
| Deterministic collection | `modules/aws-read-executor` |
| Workstation / Spot Terraform | `deploy/aws-workstation` / `deploy/aws-native` |
| Launchers and verification | `tools` / `tests` |

Validation is scoped to the documented release baseline. Never include credentials, Terraform state, private policies or unredacted transcripts in public issues.

See [deterministic remediation validation](docs/REMEDIATION-VALIDATION.md) for the pinned tools and validation workflow.
