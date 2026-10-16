# Changes

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
