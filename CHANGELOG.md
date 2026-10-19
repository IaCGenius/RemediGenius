# Changes

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
