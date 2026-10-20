# Changes

## Account and knowledge onboarding

- Add a short account/context onboarding skill using existing Hermes chat and
  knowledge stage/publish tools; remove stale claims that chat cannot save context.
- Prepare a bounded account status document from scheduled Config, EC2 and
  Security Hub reads. Store source evidence in S3 and render a readable workspace page.
- Default Spot refresh remains daily; expose `schedule_interval_hours` (1–168).
- Record the goal-first improvement backlog and UI walkthrough. Background checks
  do not call a model or automatically publish organizational knowledge.

## AWS procedures and decision briefs

- Route security tasks through selected pinned AWS procedures and share those
  procedures with every investigation model step.
- Add contextual prioritization and a separate attributed remediation-planning skill.
- Lead reports with conclusions and proposed actions; retain evidence and partial
  result disclosure. No new permissions or extra model steps.
- See [Security triage](docs/SECURITY-TRIAGE.md) for usage and skill-source decisions.

## Profile instruction clarification

- Align the security-desk objective with usable native findings: related issues,
  account context, relevant operator knowledge and an actionable next decision.
- Clarify identity, skill/tool naming and inventory routing in SOUL.md.
- Consolidate review-label, writing and retry rules; remove stale Lambda wording.
- Keep live inventory inside the existing assessment workflow. This instruction
  cleanup does not introduce the proposed faster retrieval path.

## Unreleased — read discovery and first-use corrections

- Replace the fixed service ceiling with a pinned AWS-derived read catalog,
  service discovery, SDK schemas and an operation-scoped audit session.
- Keep account/region, workflow, page, byte and action limits. Preserve
  service-specific SDK continuation tokens and distinguish denial from absence.
- Add IAM credential-lifecycle report normalization without generating reports.
- Rank collected Security Hub findings before displaying compact details, so
  the first preview does not hide higher-severity findings later in the pages.
- Separate investigation IAM from RemediGenius CE storage/recovery permissions. Add optional
  workstation audit-role provisioning and document upstream telemetry prompts.
- Bound critic context around the current request, draft and collected evidence.
  Report omitted context instead of silently claiming a complete review.
- Let an investigation conclude from sufficient collected evidence when its
  read allowance is used. Do not repeat reads just to inspect their results.
- Allow clearly labelled general control explanations without requiring a live
  AWS observation or a pinned compliance mapping.
- Disable unrelated bundled skills in the RemediGenius CE profile without deleting files or
  disabling operator-added skills. Preserve sessions, knowledge and model setup.

Pi/DeepSeek UI checks, 252 local regressions and a collector Docker build are
recorded in [validation](docs/RELEASE-VALIDATION.md). Public documentation uses
RemediGenius Community Edition / RemediGenius CE consistently. Existing release
tags are unchanged.

## Documentation updates after v0.2.0

- Separate current setup and recovery diagrams; embed static images for GitHub.
- Explain compute, model, IAM, evidence and retained-state boundaries.
- Archive old Lambda diagrams and the obsolete multi-cloud concept in v2.
- No runtime, deployment or release-tag changes.

## v0.2.0 — single-compute deployment

- Run deterministic collection on the Docker workstation or Spot host. New AWS
  setup creates its own private S3 bucket and instance role; no Lambda or
  EventBridge deployment is required.
- Add SQLite-aware private S3 checkpoints with hash-checked restoration to an
  empty runtime home. Retained EBS/Docker storage takes precedence.
- Add reviewed chat knowledge notes: stage, inspect, explicitly publish, then
  reuse the source and scope in later investigations.
- Include the optional pinned Hermes browser UI, using the same gateway,
  authentication and ce-desk conversations. Keep native Kanban available.
- Enforce operator read caps, bounded pagination and shared review context.
  Keep AWS observations distinct from interpretation and validation labels.
- Expand inventory procedures around Config, Cloud Control and SDK schemas,
  with admitted metadata reads and explicit coverage gaps.
- Correct keyless workstation onboarding, optional-UI login redirects, retained
  knowledge ownership and setup instructions. Add actual fresh-install screenshots.
- Use shared ASD-STE100-inspired writing guidance. No formal compliance claim.

**Migration:** use new Terraform state. Preserve the original source, state and
runtime data before retiring a Lambda-based installation. This is not a directory
rename or an automatic legacy-session conversion. See [upgrading](docs/UPGRADING.md).

Validation uses DeepSeek v4.1 Flash and AWS us-east-1. The record distinguishes
local regression checks, real model/UI tests, tool validation and recovery tests:
[release validation](docs/RELEASE-VALIDATION.md). No customer-cloud remediation is
applied. GitHub Actions remains paused; existing release tags are unchanged.

## v0.1.3

The published release provides bounded DeepSeek investigations, retained profile
upgrades, deterministic fix validation and the workstation/Spot deployment paths.
See its [qualification record](docs/RELEASE-VALIDATION.md#v013-qualification) and
[GitHub release](https://github.com/IaCGenius/RemediGenius/releases/tag/v0.1.3).
