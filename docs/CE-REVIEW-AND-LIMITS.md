# Explain, review, and improve CE

CE keeps the native Hermes conversation/tool history. The `ce-explain-review`
skill supplies one answer structure: outcome, sources, actual work, limits and
next decision. An operation that failed then succeeded is **RECOVERED**, not PASS.
This is an agent instruction; it is not a deterministic grader of model answers.

## Operator workflow

Ask: "Review the last three days. Start with the review index; show recurring
failures and proposed skill changes. Do not apply anything."

The read-only `review_log.py` helper returns a bounded session index without chat
content. Native Sessions/Logs provide detailed investigation records. The helper
does not infer failures or costs from message counts. Select the sessions to
review, or supply a redacted export when the agent has no session-reading tool.
Ask to save a dated Markdown report in the private workspace `reviews/` folder.
The report is an AI draft, with references and unknowns, not cloud evidence.

The retained Hermes EBS volume holds sessions and private reports across Spot
replacement. It is not an S3 backup. Shared cloud evidence remains in S3. Losing
the retained volume without a snapshot would lose these private review records.

## Bounded defaults

| Layer | Default | What enforces it |
| --- | --- | --- |
| Tool correction | Initial attempt + at most one justified retry | SOUL/skill instruction, not a hard per-operation interceptor |
| Permission, missing tool/auth/source | Stop; explain prerequisite | SOUL/skill instruction and existing IAM/filesystem boundaries |
| Model iterations per user message | 24 | Native `agent.max_turns`; final grace responses and bounded workflow auxiliary calls may add calls |
| Provider attempts | 2 total in pinned 0.21.7 | Native `api_max_retries: 2`; installed source counts attempts, unlike current web-doc wording |
| Outage recovery cycles | 0 | Native `auto_recovery_cycles: 0` |
| Wall-clock budget | 480 seconds | Native wrap-up guidance and timeout adjustment; not a hard kill; CE separately stops admitting tools at this elapsed limit |
| Terminal command | 30 seconds | Native terminal timeout |
| Review scope | 3 days, 10 sessions by default | Metadata helper bounds; operator selects detailed content |

These are not a dollar/token ceiling: SDK retries, native grace responses and
model output length can add usage. Keep provider-side spending limits. Automatic
goals, delegation, cron reviews and optimizer runs are not enabled by this change.

## SkillOpt: adopt the method first

[Microsoft SkillOpt](https://github.com/microsoft/SkillOpt) optimizes skill text
from recorded trajectories and evaluates candidate edits against held-out tasks.
It is optional offline tooling, not installed or running in CE. Its published
integration list does not establish a native Hermes integration.

For CE: select/redact examples -> classify environment versus skill failures ->
propose an exact skill diff -> test on representative and held-out examples ->
show results and rollback version -> operator approves -> install -> recheck.
Never optimize on customer logs automatically or allow the candidate to grade
itself as the only acceptance criterion. Preserve deterministic source/verdict
checks and examples covering missing data and scoped knowledge exceptions.

Start with a manual review every few days. A future opt-in scheduled review needs
an explicit model-call/spend budget, selected data scope, and a proposal-only
output. No unattended optimizer or live-skill rewriting is enabled now.

Reference: [native Hermes configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/).
Runtime source takes precedence when public docs differ from the pinned release.
