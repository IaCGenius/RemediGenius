---
name: ce-security-brief
description: Turn collected AWS security findings into an evidence-backed executive decision brief and prioritized work, using organizational context without inventing risk facts.
license: Apache-2.0
---

# From findings to decisions

Write as a security adviser: plain language, business consequence, practical next
action. Do not claim a human consultant reviewed the output. No theatrical personas,
extra agents or extra rewrite/model calls. Use the existing interpretation and review.

## Analyse the selected population

Consider all collected findings, not only a severity preview. Use deterministic
counts/grouping and compact evidence projections to identify common controls,
affected assets, threat activity and recurring issues. If only a subset was inspected,
state exactly that; do not claim the remainder was triaged. Partial collection means
partial prioritization. Do not assign unsupported exact counts to deduplicated issues.

Group related records by supported control, resource or incident relationship.
Retain original findings for traceability; shared resource names alone do not prove
one incident. Distinguish confirmed conditions, alerts needing investigation, sample
findings, accepted scoped exceptions and stale observations.

## Recommend an order, not a renamed severity list

Explain the order using observed exposure/reachability, credible active threat
signals, privilege/blast radius, asset/data importance, control dependencies,
compensating controls and evidence confidence. Missing context is unknown.
Keep AWS severity as source metadata; business priority is an AI recommendation.
A High alert about possible destructive activity may deserve investigation before
several Critical posture records. This is an example, not a universal sorting rule.
Do not turn a configuration weakness into a claim of exploitation.

Use action-oriented groups when supported: investigate now, plan the corrective
change, or monitor/clarify. These are proposed sequencing, not fabricated SLAs.
Explain why each chosen issue goes first and what evidence could change that order.
Ask at most one high-value context question rather than blocking the whole answer.
Use operator knowledge for purpose, owners, expected activity and exceptions; cite
its source and distinguish operator assertions from AWS observations.

## Present a decision-ready brief

Lead with the overall conclusion and the most important decision, not counts.
Then give up to three priority issues: what is happening, why it matters, the
recommended next action, confidence or specific missing evidence. Include the
population/count summary once as supporting evidence, not the headline.
Mention remaining issue groups without pretending they were individually assessed.
Do not paste UUIDs, tool names, budgets, receipt fields or the same severity counts
through every paragraph. Evidence references remain available separately.
Use user-facing actions, not internal skill names, in recommendations. A missing
validation step is a dependency or uncertainty, not a second security issue.
Do not fill three slots when only one supported priority exists. Describe historical
finding claims as reported conditions until fresh configuration confirms them.

When implementation planning is requested, connect each issue to a suggested owner
role (label unconfirmed ownership), prerequisites, change approach, verification and
rollback. Use ce-remediation-plan. Do not fabricate a change window, agreed date,
financial impact or precise effort estimate. Ask if the user wants a Kanban case;
only an explicit request authorizes saving it.

Review both factual support and usefulness: can the user tell what to address first,
why and what to do next? A correct list of IDs alone is not an adequate triage brief.
For a pure count or conceptual question, answer directly without forcing a plan.
