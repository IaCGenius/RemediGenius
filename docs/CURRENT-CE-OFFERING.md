# Current native CE offering

Updated 2026-10-14. [Open the architecture diagram](diagrams/ce-current-offering.html).
The diagram includes the bounded session-reliability test result.
Older console/rc2/rc3 designs are not automatically native Hermes features.

## What an AWS operator gets

One Hermes profile on workstation Docker or AWS Spot, using the operator's model.
Both use independent scoped Lambda execution and S3 evidence. Sessions/cases use
retained Docker volume or EBS; S3 alone does not restore conversations. Multiple
accounts require explicit role onboarding, not automatic organization enrollment.

The loop: inspect coverage → investigate existing findings/activity → apply
business context → prepare CLI/Terraform/CloudFormation proposals → save a manual
Kanban case → reassess after the operator's change process. Daily bounded checks
run independently of Hermes. Frequency is configurable. Checks do not call a model,
apply fixes or automatically close cases. See [operating loop](OPERATING-LOOP.md).

## Skills, not additional profiles

| Skill | Responsibility |
|---|---|
| ce-aws-read | Scope, collection, deterministic projections/counts and comparisons |
| ce-aws-security | Layered assessment, triage, proposals and case follow-up |
| ce-knowledge | Relevant context, exceptions/conflicts and source onboarding |
| ce-source-tools | Available source/tool integrations and their actual boundaries |
| ce-explain-review | Explain tools, limits, failures and critique status |

The new assessment reference uses coverage → threat/exposure → business context
→ framework mapping → action. Three optional questions establish important apps,
immediate goals and constraints. Missing context does not block a bounded read.
Source severity stays intact. The model explains priority without inventing a score.

Reuse Security Hub control IDs and supplied standard/requirement metadata. One
issue can affect multiple standards; grouping avoids duplicate remediation work,
not source counts. AI-added mappings remain suggestions, not compliance proof.
[AWS consolidated findings](https://docs.aws.amazon.com/securityhub/latest/userguide/controls-findings-create-update.html).

## Build useful knowledge quickly

Start with a real application/ownership note, one policy and an applicable exception.
The existing library preserves original files, converted Markdown and provenance.
Exact collections create small views. No new database or approval committee.

File intake reuses MarkItDown. For Confluence, start with selected exports in
supported formats or saved text, retaining page reference/version when known.
A private URL is not a connector. Authenticated Confluence sync and automatic chat
attachment ingestion are not shipped. Use [native staging](KNOWLEDGE-USE-AND-CONTROL-MAPPING.md),
not the older console upload guide. Operators publish/mount views; Hermes reads.

Borrow from the local OKF project: small context/task selections, readable sources
and explicit unknowns. Do not introduce its separate runtime or claim full schema
conformance. Hashes identify bytes; they do not establish truth.

The updated tool returns metadata with content and checks its hash. The skill
explains which source changed a recommendation. Conflicts remain explicit until
applicability is resolved. Refresh means re-importing changed originals and
publishing a new selected view. Explicit `--replaces` excludes an old revision from new views while preserving
its original and prior views. Automatic sync or authority decisions are not implemented.
See [the knowledge quickstart](NATIVE-KNOWLEDGE-QUICKSTART.md).
The [knowledge usability acceptance](OKF-USABILITY-ACCEPTANCE.md) records the newer
guided-onboarding deployment, inventory/refresh checks and real Qwen result.
The operator [preview-and-publish workflow](KNOWLEDGE-PUBLICATION-ACCEPTANCE.md)
now verifies and publishes selected views to S3. Activation remains explicit.

## Release gates

- Preserve [UI rerun](UI-RERUN-2026-10-15.md) partial results and the real
  [organization-policy test](ORG-EXCEPTION-ACCEPTANCE.md).
- Updated skills/provenance and session overlay are deployed: repository suite
  192 passed/4 Windows skips; kiosk suite 30 passed. Eight UI terminal generations
  and saved-chat resume passed with memory below 1.4 GiB of the 3 GiB limit.
- Real Qwen knowledge onboarding/provenance passed; broad assessment interpretation
  remains partial. See [the detailed acceptance](LAYERED-ASSESSMENT-ACCEPTANCE.md).
- Final proposal format-consistency retest passed. CloudTrail counts and bounds
  independently matched AWS after projection corrections (RECOVERED); narrative
  attribution remained imperfect. These are operator-reviewed draft outputs.
- The current source ZIP and checksum are delivered under `dist/native-preview/`.
  Consult its `RELEASE.json` for the exact commit; older ZIPs are historical.
- No GitHub remote is configured. Publishing a repository remains outstanding.

## Session compatibility overlay

Pinned Hermes retains up to sixteen dashboard terminals; serial UI tests exhausted
the medium host's 3 GiB container limit. The new overlay sets two terminals and a
ten-minute detached TTL, preserving Hermes's native cleanup/admission logic.
It is not an upstream configuration option. Exact upstream source hash verification
fails closed on image changes until reviewed. No custom reaper or database deletion.

At capacity, Hermes can reclaim a detached terminal; all attached slots cause its
native capacity error. Finish a run before leaving it to start another. Saved
conversation resume and live terminal continuity are different acceptance checks.
