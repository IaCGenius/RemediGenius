---
type: Guide
title: How the security desk works
description: Collection, P1–P4 scoring, issues, decisions and knowledge in RemediGenius Community Edition, in one page.
tags: [remedigenius, triage, priorities]
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-21T00:00:00Z"}
---

# Pipeline

1. **Collect (read-only).** Security Hub, GuardDuty, Inspector, IAM Access Analyzer, AWS Config, CloudWatch alarms and
   AWS Health, for every onboarded account and region. Every AWS call passes a guard that allows only
   describe/get/list/lookup/search operations.
2. **Score.** Each finding starts from its source severity, then signals move it: active threat, root use, public
   exposure, public exploit, EPSS, detection gap, fleet size, toxic combinations on one resource, business criticality,
   goals. Every adjustment is written into the finding's reasons.
3. **Group into issues.** Findings that one change fixes (same control, same package, same CIS family) become one
   issue, so 40,000 Inspector findings read as a handful of upgrades.
4. **Decide.** The user records acknowledged, investigating, fixing, accepted_risk, false_positive, suppressed or
   resolved, always with their reason and through the approval prompt.

# Priorities

| Priority | Score | Meaning |
|---|---|---|
| P1 | 70+ | act now (today) |
| P2 | 50–69 | fix this week |
| P3 | 30–49 | plan in the backlog |
| P4 | <30 | monitor or accept |

A CVE's severity alone never makes P1: exploitability and exposure decide urgency for vulnerabilities.

# Knowledge

The desk's knowledge is one OKF bundle. The `remedigenius/` folder is shipped (these guides, the
[source guides](/remedigenius/sources/) and the [playbooks](/remedigenius/playbooks/)). Everything else is the
organization's own knowledge; see [how organization knowledge changes triage](/remedigenius/guides/organization-knowledge.md).

# Answering well

- Lead with what needs attention, P1 first, with the ref, the resource and the one-line reason.
- Verify current state before recommending a change: findings can be stale. See [where to look](/remedigenius/guides/where-to-look.md).
- Say what you could not see (a source off, a read denied, an account not covered).
- Fixes are proposals in the user's IaC, never changes you make.
