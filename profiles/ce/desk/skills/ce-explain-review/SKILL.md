---
name: ce-explain-review
description: Explain CE answers, capabilities, failed or recovered operations, and conduct a bounded operator-requested review with proposed skill improvements.
license: Apache-2.0
---

# Explain and improve without hidden work

Use the same short structure whenever the operator asks how, why, what happened,
what is available, or whether something passed:

1. Outcome: PASS (no failed attempts), RECOVERED (success after a failure),
   PARTIAL, BLOCKED, FAILED, or NOT_RUN. Do not convert absent evidence to PASS.
2. Sources: exact files/receipts, scope and observation time; distinguish source
   availability, collected data and knowledge supplied by the operator.
3. Work: tools actually called, deterministic results, then AI interpretation.
   Explain actions and evidence, not hidden model reasoning.
4. Limits: failed attempts, correction if any, missing/stale data, usage if measured.
5. Next: a concrete operator choice. Never imply a proposed action was executed.

## Attempts and cost

For ce_validate, allow at most three validation attempts per format, using
actual diagnostics; this is not permission to execute fixes. For other tools:
one initial tool operation plus at most one justified retry. Permission denied,
missing source/tool/authentication and unknown scope stop immediately. One retry
is allowed for a transient fault or a clearly understood argument correction.
Do not change tool, shell or code repeatedly to evade the same blocked operation.
Native configuration caps model iterations at 12 per user message; provider
retries are separately limited to one and recovery cycles disabled. The 240-second
native run budget is a wrap-up hint, NOT a hard deadline or dollar ceiling. The CE
plugin separately stops admitting tools after 240 seconds, 24 tool admissions,
or six cloud reads per turn. Native grace
responses and provider internals mean 12 is not a total API-call guarantee.
Stored-evidence show/compare operations consume tool admissions and the elapsed
tool-dispatch budget, even though they do not consume the cloud-read allowance.
The identical-read counter is per user turn, not a lifetime session quota. A later
user-requested reassessment gets a new turn budget; do not suggest changing scope
to evade a limit or claim earlier turns prevent a legitimate fresh reassessment.
Do not claim a cost unless recorded; provider budgets are the financial backstop.

## Explain enforcement accurately

The executor's operation/target/region checks, SDK parameter validation, per-call
page/byte limits, IAM and S3/file access controls run outside the model. The agent
cannot grant itself additional permissions by selecting a different prompt.
The SDK's one-attempt setting is per request. The agent can issue another request;
the "one justified correction" rule is skill guidance, not a global deduplication
or retry firewall. Likewise, proposal quality, source interpretation and the
instruction to stop investigating when sufficient remain model-dependent. There
is no implemented semantic validator that guarantees the final answer is correct.
Do not describe a successful tool call, a step cap, or a cited receipt as proof
that all conclusions in the answer were validated.

## A review the operator can request every few days

Ask for the time window only if absent; default to the last three days. Inspect at
most ten operator-selected sessions or a supplied redacted review export. If past
sessions/logs are not exposed by a native tool, say so and ask for an export from
the native Sessions/Logs UI; do not invent a system-wide audit from this chat.
For an operator-run deterministic metadata index, use `scripts/review_log.py
--home <your active Hermes profile home> --days 3 --limit 10` outside the agent. It uses the native
state.db read-only and exposes session IDs/times/message counts, not conversation
content. It reports NOT_REVIEWED until the actual selected session is reviewed.
Terminal is not admitted in this CE profile; ask
the operator for the selected export instead of executing it or inventing access.
Never dump whole histories, credentials or customer evidence into a report.

Summarize outcome counts, repeated failures, recovered attempts, missing
capabilities, measured usage (or unknown) and the three most useful improvements.
For each proposal include session/receipt references, affected skill, exact edit,
expected effect, regression examples, validation result (NOT_RUN until executed),
and rollback version. Keep environment/IAM/data gaps separate from skill defects.
If requested, return a dated Markdown AI-draft review for the operator to save.
This profile has no admitted file-write tool.
Hermes may list `skill_manage` in its native banner, but the CE execution gate
blocks it. Visible/discovered is not admitted. Read the preflight `admitted_tools`
list rather than inferring permission from the UI or the AWS operation manifest.
Do not test a mutation to discover this boundary. The operator upgrades skills
through the reviewed package outside the investigation conversation.

Never install SkillOpt, enable a schedule, edit live skills, or run optimization
as part of a review. Propose a candidate, validate against a small held-out set,
then obtain operator approval for that exact diff before applying. A review is
one bounded conversation, not a self-improvement loop. Native skill write approval
and filesystem/IAM boundaries remain necessary; this document is not enforcement.

Review scope: AI_CRITIQUED means bounded same-session evidence or loaded skill
results were supplied, not that every claim or provider syntax passed validation.
The runtime automatically shares actual skill_view results, including referenced
files, with the critic. No manual context packet is needed. This is not the whole
conversation: omitted skill context is flagged, and skills are guidance rather
than AWS observations. NOT_GROUNDED means neither evidence nor loaded skill results
were available; NOT_REVIEWED means no usable critique. Do not infer a
review count from conversation turns. Count actual tool events if exposed; otherwise
say the total is unavailable. ce_case provides local case writes, while AWS remains
read-only. Explain those separately instead of claiming no writes of any kind.
