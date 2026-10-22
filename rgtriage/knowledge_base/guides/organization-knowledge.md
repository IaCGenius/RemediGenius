---
type: Guide
title: How organization knowledge changes triage
description: Which concept types change priorities, the review rule, and how to draft a concept for review.
tags: [remedigenius, knowledge, okf, review]
sources:
  - {id: okf, resource: "https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md", title: Open Knowledge Format v0.2, author: org:google-cloud}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-21T00:00:00Z"}
---

# What changes priorities

Only concepts a person has reviewed (OKF trust tier *human-reviewed*, status *stable*) change scores. The effect
is cited in the finding's reasons with the concept path.

| Type | Folder | Effect |
|---|---|---|
| Application | `applications/` | Resources whose tags match `remedigenius.match_tags` get its criticality; findings show its owner |
| Account | `accounts/` | Every finding in `remedigenius.account_id` gets its criticality (an application match is more specific) |
| Risk Exception | `exceptions/` | Matching findings count as accepted risk until `remedigenius.expires`; then they return |
| Security Goal | `goals/` | Matching resource types, categories or signals get extra points |

Team, Policy, Runbook, Architecture, Note and Reference concepts are context for answers and fixes; they never
change a score.

# Drafting a concept (agent)

You cannot add to the bundle. Write a draft to the proposals folder at `knowledge/<folder>/<slug>.md` and tell the
user to review it in the dashboard **Knowledge** tab. Use this shape:

```markdown
---
type: Application
title: Payments
description: Card payment API and its database.
status: draft
generated: {by: remedigenius-agent, at: "2026-10-21T10:00:00Z"}
remedigenius:
  match_tags: {app: payments}
  criticality: mission_critical      # mission_critical | business_critical | non_critical | test_development
  owner: /teams/payments-team.md
---

What the user told you, in their words, and when.
```

Account uses `account_id` (12 digits), `criticality`, `environment`. Risk Exception uses at least one of
`control_id`, `finding_type`, `resource`, plus `expires: YYYY-MM-DD` and `approved_by`. Security Goal uses
`resource_types`, `categories`, `signals` and `points` (1–15). Never write `verified`: only a person reviews.

# Asking for missing knowledge

Ask one question at a time, only when the answer changes a priority or an owner (for example "Who owns
`payments-db`, and would an outage stop card payments?"). Then draft the concept from the answer.

Related: [how the desk works](/remedigenius/guides/how-the-desk-works.md) · [where to look](/remedigenius/guides/where-to-look.md)
