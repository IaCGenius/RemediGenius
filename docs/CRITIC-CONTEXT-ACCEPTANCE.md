# Critic shares the skills Hermes loaded

The CE operator asks a question normally. No new configuration, agent profile or
manual review packet is required.

The CE runtime observes Hermes's native `skill_view` results and automatically
includes those exact results, including opened reference files, in `ce_review`.
They accompany the current request, concise draft, capability manifest, runtime
limits and bounded same-session CE evidence. The critic can now check a documented
operator-side workflow even when that command is not an admitted runtime tool.
Skills remain guidance; they do not become AWS observations or execution approval.

This fixes a specific integration gap: native skill reads bypassed CE's own tool
handler. The critic previously received two fixed remediation references, but not
the knowledge publication reference Hermes had just opened. It wrongly challenged
the documented publisher command. The integration now uses Hermes's supported
`post_tool_call` hook, rather than a separate collector or model client.

## Scope and cost

- Loaded reference results are retained within the same session and recovered from
  native conversation history or the existing retained review-context cache.
- Skill context is bounded to 32,000 serialized characters. Older results are
  dropped when necessary; the review packet explicitly flags omitted context.
- The complete review packet is bounded to 90,000 characters. An oversized packet
  returns NOT_REVIEWED without calling the model.
- One review per turn and the existing review timeout/token cap remain in effect.
- Audit records include source-result hashes and counts, not reference bodies.
- This is shared retrieved context, not the whole model conversation or hidden
  reasoning. AI_CRITIQUED remains an AI critique, not correctness certification.

The explain/review skill describes these limits. Hermes should resolve internal
review comments against the supplied sources and surface material uncertainty,
rather than exposing an avoidable internal disagreement to the operator.

## Verification

2026-10-15: full local suite **207 passed, 4 skipped**. Focused regressions cover
exact native result forwarding, restart persistence, session isolation, unrelated
tool exclusion, bounded omission, history recovery and no model call for an
oversized review packet. Constructed local cases are separate from live evidence.

First live Qwen 3.8 Max run (`20261015_105303_3c72b8`): the native session contained
two skill reads (ce-knowledge and references/onboarding.md). Both SHA-256 values
matched the critic audit exactly. One review received both results and two CE
evidence excerpts; no skill context was omitted. The critic explicitly cited
onboarding.md, accepted the documented publication workflow, and corrected a
citation-path issue. The original missing-reference defect is resolved in this run.

User-facing answer: **PARTIAL**. After review, Qwen introduced an incorrect config
directory in its copyable command, followed by a parenthetical correction. The
reviewed draft had the correct path. This is a final-answer generation defect,
not missing reviewer context. The onboarding skill was tightened to preserve
supported commands, copy supplied paths verbatim, and replace corrections in place.
A subsequent run is recorded below; this first result is not erased.


Final live run (`20261015_110053_3a7462`), same question and real selected policy:
**PASS for this targeted acceptance**. Qwen returned the complete policy path,
correct copyable workstation command, preview-token instructions, the separate
activation step and the missing bucket-use classification. No internal review
disagreement or corrected-but-still-wrong command remained. One Qwen review received
two actual skill results and two CE evidence excerpts, with no omitted skill
context. Both skill-result hashes exactly matched the native session records.
The critic returned “No issues identified, not certified correct.”

The first run's captured skill context also survived the subsequent Spot host
replacement with identical hashes. This verifies retained-volume recovery in this
deployment; it is not a claim that all session storage is automatically in S3.
The active profile was backed up/upgraded and passed all 59 integrity checks;
Qwen 3.8 Max and manual Kanban remained selected. Final deployed source archive:
`67b72d056cf79fab67e789400cfca5c5ebdc1ed610663aab1482159c910b4248`.

Private trace/response records are under `.rgce/layered-acceptance/critic-skills*`
and `critic-retention.json`; they are excluded from the shareable source archive.
The localhost login endpoint returned HTTP 200 after tunnel restoration. These
were native Hermes oneshot tests, not a new browser UI acceptance pass. Earlier
UI coverage and remaining limitations retain their recorded statuses. No cloud
posture fix or knowledge publication was performed by these model tests.
