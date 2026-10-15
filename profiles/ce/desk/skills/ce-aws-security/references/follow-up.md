# Return to findings and finish the work

Use ce_case for the native Hermes Kanban board; this is local tracking, not cloud
remediation permission. Offer once: "Track this finding so we can return to it?"
Create only after the operator agrees. List existing cases first. identity must
contain exact account, region, resource and source finding/control ID; reuse that
identity to deduplicate repeated requests. Never create one card per imported alert.

The body is readable Markdown: scope, original finding, observed time and receipts,
operator context, chosen CLI/Terraform/CloudFormation draft, missing inputs,
verification condition, owner/change reference and next review date if supplied.
Do not invent owner, dates or approvals. Keep source facts separate from decisions.
Material changes go in comments, including revised draft and reason; retain older
versions. The native Kanban page is the workspace; cases survive a new chat.

Actions: list/show; create; comment; wait (blocked); verify (review); close (done);
archive (only after done). No dispatcher or scheduled LLM worker is enabled.
Close only for explicit disposition: verified_fix, operator_false_positive,
accepted_risk, retired, duplicate, cancelled. Verified fix/retirement needs fresh
evidence; accepted risk needs scoped operator reason and review/expiry date. The
tool records assertions, not independent truth. No inactivity-based closure, no
AWS suppression. Keep unresolved risk visible even when remediation work is closed.

When returning, show the case including its comments, not just the list summary.
Read later corrections before treating an older draft as current or proposing the
same correction again. Refresh relevant observations and compare before reusing
commands. Recheck every saved command's exact flags and format support;
a prior AI critique is not proof of syntax. Use available SDK/schema context,
state when CLI/provider validation was not run, and append corrections before
recommending reuse. For S3 PutBucketVersioning, MFA is one CLI `--mfa "SERIAL TOKEN"`
argument, not `--mfa-serial` and `--mfa-code`. Never request real tokens in chat.
A change window or a user saying "done" is not verified success.
Offer closure after verification; do not silently close. Archive to reduce clutter.
Expired decisions or changed scope require reconsideration, not automatic reopening
or suppression. If the user already has a ticket, retain its link in the case.

## Daily checks

Read ce_aws show path scheduled/latest.json to inspect the latest deterministic
check report. State status, observed_at, configured interval, scope, receipt and
comparison for each check. RUNNING/stale/failed/partial is not current assurance.
No latest report means not yet run or unavailable, not all clear. Scheduled checks
do not call a model, apply fixes, create all findings as cards or certify closure.
Use raw receipt paths to investigate changes; selected knowledge is applied during
the interactive interpretation. To change frequency, guide the operator to the
documented Terraform schedule_interval_hours (default 24; 1..168) and reviewed
apply. Do not claim to have changed a schedule through chat.

## Fix delivery adapters

One workflow, three delivery formats: CLI commands, Terraform source/import plan,
CloudFormation stack edits/change-set proposal. Save the chosen draft on the card
as a comment so it can be resumed independently of chat. Each draft must state
resource scope, preconditions, impact, rollback limits, validation performed and
post-change reads. These are preparation adapters, not execution adapters. No
terraform apply, CloudFormation deploy or AWS writes are admitted. Supplied real
source may support a specific diff; never invent repo inspection or validation.

For technical syntax, use supplied provider/version/schema context. If unavailable,
label syntax unvalidated and request the user's validation output. An AI critique
does not replace provider validation. Do not ask for secrets or one-time MFA codes
in chat or store them in cards.
