# Operating-loop acceptance — 2026-10-14

This is an incremental deployment, not a declaration that every CE feature is
release-ready. The owner decides publication. Customer AWS resources were not
remediated. Actual AWS observations and Qwen were used for live acceptance;
unit-test doubles are separately identified below.

## Verified so far

- EventBridge Scheduler enabled at 24-hour intervals; configurable 1–168 hours.
  A self-deleting one-time schedule used the identical target, role and payload.
  Its event was `2026-10-14T19:43:07Z`; the report was observed at
  `2026-10-14T19:43:50.167071+00:00`, status OK. Security Hub ACTIVE findings and
  Config recorder configuration both collected successfully and compared UNCHANGED.
  This tests real timer delivery, not only a direct Lambda invocation.
- Initial deployment needed two corrections: scoped list permission for a missing
  initial report, and literal Scheduler context tokens instead of JSON-escaped
  angle brackets. Corrected scheduled execution is RECOVERED, not a first-pass success.
- Scheduler retries and asynchronous Lambda retries are both zero. Concurrency is
  one. No scheduled model calls are made. Latest RUNNING/failed/partial observations
  remain distinguishable from successful collection.
- Native Kanban adapter lifecycle exercised against a real existing Config receipt:
  triage → blocked → review → done → archived, with comments and identity deduplication.
  Early tests exposed native initial-state/triage-transition requirements; corrected
  transitions all returned true. Acceptance cards were explicitly cancelled and
  archived; the underlying Config condition was not claimed fixed.
- A Spot replacement retained the board and comment history. Qwen read both archived
  acceptance cards using ce_case. Dashboard returned HTTP 200. Package integrity
  passed; default and ce-desk routes used the same Qwen3.8-max configuration, with
  board worker/review dispatch disabled.
- 28 focused local regression tests passed: runtime gate, bounded evidence review,
  same-session context retention/isolation, and a comparison exception producing
  PARTIAL rather than OK, packaged guidance in review, and duplicate review-label removal.
  Failure injection uses doubles; it is not
  evidence of a real cloud collection.

## Live model correction and remaining validation

The first Qwen operating-loop turn was PARTIAL. It read retained case history and
correctly distinguished cancellation from remediation, but called the older Config
receipt the latest scheduled check. It also duplicated the review-status heading.
The correction explicitly routes scheduled questions to `scheduled/latest.json`
and supplies tool names, arguments and preflight time to the reviewer. The real
Qwen retest in session `20261014_195441_5036fe` correctly reported the scheduled
event, both sources and UNCHANGED comparisons, 24 ACTIVE findings, and the fresh
empty Config recorder list separately from the older cards. Core retrieval is
RECOVERED. The model repeated an equivalent review-status line at the end. A final
runtime correction removes model-written review-status lines deterministically;
the runtime supplies the authoritative label.

The next real Qwen turn created open case `t_3554b5cc` with the observed Config
recorder absence, a CLI-first proposal, explicit missing role/scope/destination,
verification steps, rollback limits and no claim of execution or closure. It
corrected the reported Terraform boolean to Enabled/Disabled strings and explained
root/MFA constraints. This also exposed missing skill-reference context in the
critic; the final package includes bounded pinned fix/follow-up guidance separately
from cloud evidence. Provider validation is still NOT_RUN.

Authenticated native `/api/plugins/kanban/board` returned HTTP 200 for both root
and ce-desk profile routes, showing the open case and two archived acceptance cards.
This is an API workspace smoke test, not a full browser interaction rerun.

Final deployed verification: source archive
`6f4990ab00fbc4918ebb6d3c73b0c413044befdf499b918fa3465acac182ba84`;
package and active-instruction integrity checks passed, dashboard HTTP 200.
Qwen session `20261014_200705_efbefb` resumed the real open case after another
Spot replacement, preserved its missing inputs, explained the prepared CLI fix,
correctly described MFA Delete as a string with root/MFA constraints, and left the
case open and unchanged. The critic no longer complained that the packaged fix
reference was absent. The answer had one runtime heading; it still repeated the
same review result in an explanatory closing sentence. This is not a guarantee
that all model prose or unvalidated proposals are correct.

Final infrastructure inspection found one native ASG member, zero retired-prototype
members, and only the intended enabled daily schedule under the native prefix.
Terraform validation passed. No public release was performed.

Private original outputs, Terraform plans and command results remain under
`.rgce/native-sketch/`; they are excluded from Git. No unredacted independent UI
test artifacts were copied into the repository.

## Still outside this increment

No automatic customer remediation, provider validation of generated IaC, scheduled
LLM investigations, notification delivery, automatic reopening/suppression, or
cross-AZ Kanban recovery. Cards use retained EBS; scheduled evidence uses S3.
The full independent 18-case UI pack has not been rerun for this increment.
AI_CRITIQUED is a model critique, not a verified remediation or certification.
