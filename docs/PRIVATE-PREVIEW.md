# Workstation private preview (rc9)

**Historical console bundle.** For the current native Hermes preview, start at
[START-HERE](../START-HERE.md). The instructions below are retained for earlier
artifacts and do not describe the current workstation deployment.

This page documents the separately retained rc9 workstation bundle. For the rc10 integrated cloud Hermes edition, use [Cloud start here](CLOUD-START-HERE.md) and [cloud architecture](HERMES-CLOUD.md). Its model runtime and deployment acceptance are separate from the historical workstation checks below.

The goal is a useful first conversation with your own evidence: connect existing tools, collect evidence, add shared knowledge, investigate, prepare a proposal, and reassess. This edition is independent of a hosted subscription.

## What to share

Share only the assembled `remedigenius-ce-private-preview-0.1.0rc9.zip` and its companion SHA256 file. A separate verification receipt ties the fresh-extraction checks to that ZIP hash. It contains the tested Docker image archive, source archive, native Python wheel, dependency list, source/skill links, checksums, quickstart and feedback template. Do not send the development directory, `.rgce`, cloud acceptance data, Terraform state or agent/provider configuration. The source archive includes the complete readable implementation; experimental components are labeled separately.

The recipient extracts the bundle, reads `START-HERE.md`, loads the image and starts the local Compose service. The sample needs no AWS account or model key and requires no dependency download after the image is loaded. The packaged image targets Linux amd64 (tested through Docker Desktop on Windows and on the AWS Linux host). Other platforms can build from source but are not represented as tested prebuilt images. Apple Silicon emulation is not a tested preview path.

## Supported preview promise

- Single-operator local Docker or native Python workspace.
- Evidence and deterministic rules remain separate from reviewed knowledge and AI interpretation.
- Useful document/knowledge review and selected file exports for existing agents; MCP is optional.
- Bounded implemented AWS collectors; portable workstation collection/import for Docker/S3 consoles.
- Optional durable S3 workspace and isolated AWS console deployment with explicit IAM/storage separation.
- Reviewed proposals and guarded reassessment; no automatic remediation.

The console is not a chat runtime and does not call an LLM. Hermes remains independent and uses its own model/provider setup. A user can review all artifacts in ordinary files or use the included skill with an existing agent. Credentials and admin capabilities should not follow those exports.

## Trial checklist

Use [the quickstart](V0.1-QUICKSTART.md). A useful preview is complete when the recipient can inspect a sample finding, apply reviewed guidance, see a proposal, understand reassessment limits, download a readable investigation, stop/restart without losing data, and tell you where the workflow is confusing. Real AWS access is an optional second step, not the first-run prerequisite.

## Known limits that remain visible

This is a private preview, not GA, a multi-user service or a replacement for all security tooling. Azure/GCP, native GitHub OAuth, arbitrary generated-code execution, autonomous IaC changes and hosted tenancy are not supported. Document parsing is not an OS sandbox. Knowledge approval is an operator assertion, not verified enterprise identity. S3 mode has one active writer and bounded startup recovery; local Docker volumes need backups. Imported coverage cannot assert rule clearance. Model output requires review and can be wrong.

## Validation record

The current candidate's final acceptance evidence is recorded in `docs/acceptance/rc9-results.json` and the bundle's `RELEASE.json`; historical rc6–rc8 reports retain their original scope and hashes. The release preparation checks the shareable files, installs from the wheel, starts the prebuilt image from an extracted bundle, exercises the real browser flow and verifies persistence. CI configuration is supplied; no hosted CI run is claimed before repository publication.

The final source passed 131 CE/release checks (including 10 maintainer-only private-pattern checks), 38 rule cases and 30 existing kiosk tests. Three Edge journeys passed against the Docker image. All 32 package files matched between the fresh Windows wheel and image. Actual selected AWS file collection/import, S3 recovery, migration/retry, IAM denial checks and isolated AWS instance replacement passed. The AWS test host is stopped; S3/EBS remain retained. Raw evidence stays private.

## Feedback and later publication

Use [the feedback template](FEEDBACK.md) through your existing private channel with the maintainer. No invented email address, public issue requirement or automatic telemetry upload is involved. Share synthetic reproductions and redacted screenshots.

A later public release additionally needs the intended repository, hosted CI results, a real security-contact channel and a stable-release decision. Those are publication gates, not prerequisites for sharing this private bundle. Transfer domain improvements to the existing product using [the core handoff](CORE-HANDOFF.md); this preview does not modify or restart that product.
