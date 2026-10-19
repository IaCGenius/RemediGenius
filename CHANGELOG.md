# Changes

## Unreleased: local-compute deployment migration

- Move deterministic AWS collection to the Docker or Spot host; archive the Lambda baseline in v2 for hosted reuse.
- Add private S3 checkpoints with SQLite-aware backup and verified restore.
- Add operator-confirmed short knowledge notes through the existing CE tool.
- Honor request-local Hermes profiles and exact returned normalized artifact paths.
- Pin collector Python/SDK and keep validation separate.
- Acceptance is in progress. No new release tag or readiness claim yet.


## Unreleased

- Add opt-in Hermes browser UI for workstation and Spot deployments. Keep the native dashboard, profile data and CE runtime. Pin upstream source, preserve its MIT license, and patch selected-profile WebSocket routing.
- Document login, profile-scoped model secrets, tested chat/knowledge flows and UI parity limits.

## Inventory recovery candidate — not release-qualified

2026-10-17. See [the recovery plan](docs/INVENTORY-RECOVERY-PLAN.md).

- Expand the read catalog to account-local Config inventory, Cloud Control and
  resource-schema discovery, with AWS audit/view IAM policy attachments for
  downstream metadata reads. Existing installations require policy review/apply.
- Allow multi-page reads inside investigations and return continuation parameters
  and explicit pagination stop reasons. Retain source batches and receipts in S3.
- Include retained summaries in blocked assessment output and preserve exception
  types. Load the generic inventory fallback procedure into planning context.
- Unknown nested SDK schema fields return a recoverable error and available
  parent fields. Failed collection hops retain the precise request for diagnosis.
- Inventory framing preserves the user's objective rather than restricting it
  to a guessed tool list. Model hops have a configurable 120-second timeout,
  capped by the remaining 480-second turn deadline; no automatic retry is added.
- Runtime supplies follow-up instructions and budget counters for exhausted
  investigations. A completed run cannot be resumed with a fresh budget.
- Validation so far: 101 targeted local regression/boundary tests and Terraform
  validation passed. Live collector reads verified Config, Cloud Control and
  multi-page history with S3 receipt hashes. Native UI tests exposed framing,
  timeout and schema-error issues, then verified Config fallback and a real Cloud
  Control resource. A separate UI run returned matching VPC/log-group counts and
  completed four-page collection. Bedrock family coverage remains bounded/partial.
  Creation-history UI testing completed three pages (101 events), distinguished
  successful creates from denied attempts, and matched independent AWS reads.
  Wider qualification remains incomplete; existing release tags are unchanged.

## Unreleased — main after v0.1.3

2026-10-16. Package version remains unchanged. The v0.1.3 tag and release downloads
remain unchanged; clone `main` to use these source updates. Record `git rev-parse HEAD`
with your deployment and retain the generated source archive digest.

- New investigations use a consistent answer format with evidence and knowledge
  references checked against the returned results.
- The runtime supplies collection metadata and review/validation labels. An invalid
  final answer contract blocks delivery and retains the investigation for inspection.
- Shared ASD-STE100-inspired writing guidance promotes short, direct explanations.
  This is not a claim of formal compliance. Commands and source artifacts are preserved.
- Behavioral tests cover reference membership, invented statuses, forbidden tools,
  incomplete evidence and compatibility with existing investigations.

Validation: 168 local tests passed. Three live DeepSeek investigations completed
with valid references and the same context hash across interpretation, review and
final output. Two repeated inventory questions agreed. A fourth capability-gap
check stopped without substituting another data source. Some model explanations
remain repetitive; that writing check is partial. These checks used isolated local
Hermes, not a new Spot deployment or a new browser end-to-end qualification.

See [answer behavior](docs/ANSWER-CONTRACT.md), [validation](docs/RELEASE-VALIDATION.md)
and [upgrade instructions](docs/UPGRADING.md). Private evidence and transcripts are
not distributed. No new model call or retry loop is added for writing style.

Setup documentation now distinguishes `main` from the immutable release tag,
uses the Bash login path, and names the tested WSL2 workstation setup. Local checks
also passed the offline demo, Python wheel build, native source packaging, archive
privacy/path inspection and local documentation-link targets. GitHub Actions remains
disabled; the README links the validation record instead of a misleading CI badge.

## v0.1.3

The published release provides bounded DeepSeek investigations, retained profile
upgrades, deterministic fix validation and the workstation/Spot deployment paths.
See its [qualification record](docs/RELEASE-VALIDATION.md#v013-qualification) and
[GitHub release](https://github.com/IaCGenius/RemediGenius/releases/tag/v0.1.3).
