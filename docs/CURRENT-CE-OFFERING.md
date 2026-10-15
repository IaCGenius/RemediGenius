# Current native CE offering

Updated 2026-10-15. [Open the architecture diagram](diagrams/ce-mvp-architecture.html).

**v0.1.0 validated baseline: AWS `us-east-1` and Qwen 3.8 Max.** Configuration remains extensible; other regions/models are outside the validated baseline.

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
with explicit publication and mounting of views for Hermes to read.

The knowledge design uses small context/task selections, readable sources
and explicit unknowns. CE does not claim full OKF schema conformance. Hashes identify bytes; they do not establish truth.

The updated tool returns metadata with content and checks its hash. The skill
explains which source changed a recommendation. Conflicts remain explicit until
applicability is resolved. Refresh means re-importing changed originals and
publishing a new selected view. Explicit `--replaces` excludes an old revision from new views while preserving
its original and prior views. Automatic sync or authority decisions are not implemented.
See [the knowledge quickstart](NATIVE-KNOWLEDGE-QUICKSTART.md).

See [release validation](RELEASE-VALIDATION.md) and [known limits](LIMITS.md).

See [release validation](RELEASE-VALIDATION.md) and [known limits](LIMITS.md).
