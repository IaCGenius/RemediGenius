# Clear answers and runtime-owned results

This source change keeps the package version unchanged. It does not replace the
published v0.1.3 tag or its qualification record.

New investigations return these sections in a fixed order:

1. Answer — AI interpretation.
2. Observed facts — AI summary with evidence references.
3. Evidence and checks — runtime-reported collection metadata and review state.
4. Knowledge used — AI explanation with selected-source references.
5. Proposals — at most three AI suggestions, only when useful.
6. Limits / next step.

The final model step returns a small JSON object. The controller validates its
shape and checks E/K reference IDs against results in the frozen packet. It renders
the headings and collection metadata itself. Schema discovery is not AWS-state
evidence. Missing pagination stays unknown. Missing knowledge is not evidence that
the organization has no policy. No extra rewrite model call is added.

The check proves that a cited source was returned, not that the source supports
every claim. The summary, sufficiency decision and recommendations remain AI
judgments. Runtime metadata stays separate. Model text cannot supply additional
status fields or Markdown headings in the structured response.

An invalid answer contract blocks final delivery. The retained draft and evidence
remain available for diagnosis. There is no new automatic retry loop. Existing
saved answers and already-started investigations keep their previous contract.

Investigation output explicitly reports that fix validation did not run in that
stage. If the operator requests a fix, the existing validator follow-up reports
its actual result, attempt count and artifact hash separately. Neither a critique
nor a successful investigation converts validator FAIL into PASS. Keep returned
artifact bytes unchanged; an edit requires a new validation.

## Writing reference

[Shared writing guidance](../profiles/ce/desk/skills/ce-investigation/references/clear-writing.md)
is loaded with investigation instructions and referenced by SOUL for other answers.
It uses short active sentences, consistent terms and direct instructions. It is
ASD-STE100-inspired, not a claim of formal controlled-vocabulary compliance.
Commands, source identifiers, receipts, hashes and diagnostics must retain their
exact meaning and content. Style does not change permissions or execution results.

## Evaluation

Run `python -m pytest -q tests/test_answer_contract.py tests/test_flexible_investigation.py tests/test_native_execution_contract.py`.
These are constructed boundary tests, not live AWS evidence. They check reference
membership, consistent layout, invented-status rejection, denied tools, persistent
budgets and legacy compatibility. Resource-family cases test the same contract
without matching exact prose or teaching resource-specific answers.

For model evaluation, retain tool traces and saved workflow records. Count initial
completion, bounded recovery, blocked contracts and exhausted budgets separately.
Check the same packet hash across interpretation/review/finish, the actual dispatched
operations, evidence references and tool results. Repeated answers need consistent
facts within the same scope; they do not need identical wording. Read the result
to assess semantic correctness and usefulness; a structural pass is insufficient.

GitHub Actions includes these tests in its existing test discovery, but is disabled
pending the owner's billing repair. Local test success is not a hosted CI result.
