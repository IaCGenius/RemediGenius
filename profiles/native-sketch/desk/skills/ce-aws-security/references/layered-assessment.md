# From AWS findings to an operator's next decision

Use this procedure for an initial assessment, prioritization, framework questions,
or “what should we work on next?”. Keep one CE profile. These are assessment
lenses, not new agents, permission roles or another scoring engine.

## Start with a useful bounded answer

Read the configured targets and selected knowledge index. Reuse answers already
provided. If business context is missing, ask at most three short questions in
one message while continuing the requested evidence assessment:

1. Which application/accounts are most important, and which are production?
2. What matters now: incident investigation, exposure reduction, or an audit/change deadline?
3. Are there relevant policies, exceptions, owners or change constraints to use?

Do not wait for a questionnaire before reporting an observed urgent issue. Without
answers, explicitly use a provisional exposure/incident lens, not an invented
company policy. Framework preference is optional and does not change AWS facts.

## Five layers, selected as needed

| Layer | Question | Evidence and limits |
|---|---|---|
| Coverage | What can we assess reliably? | Exact accounts, regions, operations, observation times, errors and pagination. Enabled is not populated or complete. |
| Threat and exposure | What needs attention first? | Source findings, observed configuration and relevant activity. Distinguish suspected activity, confirmed compromise and configuration weakness. No invented attack paths. |
| Business context | Why does this matter here? | Relevant selected policy, purpose, owner, criticality and exceptions. Cite source/version/scope; unknown purpose remains unknown. |
| Control mapping | Which requirements does the same issue affect? | Preserve source SecurityControlId, AssociatedStandards and RelatedRequirements when present. Identify standard/version. Additional AI mappings are suggestions requiring an authoritative reference, not verified compliance. |
| Action and follow-up | What useful decision can be made now? | Up to three next actions, prerequisite, impact, uncertainty, owner if supplied, fix format, and a concrete reassessment condition. Offer a case only when useful. |

Use existing Security Hub findings first. A control may appear in multiple
standards. Group the same underlying issue for the operator but retain original
finding IDs, native severity and deterministic counts. Do not count framework
labels as independent risks or pretend that grouping changed source records.
Use deterministic projections/aggregation for totals; do not manually recount a
truncated preview. Source compliance status is not an organization-wide attestation.

Keep each conclusion within its observation: a failed Config control means the
source reports a Config coverage gap, not that all reliable change history is
absent. A refreshed GuardDuty/Security Hub finding establishes its current reported
status, not containment or remediation. For recorder operation, configuration alone
is insufficient; request recorder status or state that it remains unverified.
Do not present these limited checks as verification of the stronger outcome.

## Show what changed the priority

For each proposed priority, give a compact explanation:

“Observed: [receipt/time/condition]. Context: [knowledge path/version and scope,
or not supplied]. Priority: [AI judgment and reason]. Next: [decision/action].”

Use plain categories such as investigate now, plan a change, or clarify context.
Never fabricate a numeric risk score or downgrade native severity. An exception
can change an organization-policy conclusion or action without erasing the
technical observation, changing an AWS control result, or closing an incident.

If two policies conflict, identify the exact conflicting statements and overlapping
scope. Prefer an explicit scoped variation only when applicability is established;
newer import time is not automatic precedence. Ask the operator which applies,
and continue unaffected work. Unknown/mixed-purpose resources remain unresolved.

On a later assessment, reread relevant context and fresh evidence. Explain whether
the priority changed because of cloud facts, new knowledge, or changed user goals.
Do not claim a persisted knowledge-use ledger or automatic case reopening.

## References

- AWS consolidated control findings: https://docs.aws.amazon.com/securityhub/latest/userguide/controls-findings-create-update.html
- Source field changes and standard mappings: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-changes-consolidation.html

These references explain AWS semantics; they do not prove enabled standards or
coverage in the connected account.
