# Explore views: timeline, campaign, graph

The desk answers three exploration questions — what happened to a finding, where a campaign stands, and what is related
to an entity. Each answer carries its own completeness and cutoff, because an operations screen that hides those is worse
than no screen (CE-23).

These are view models over the scoped query service (`rgtriage/queries.py`), not a second query engine. They are plain
dictionaries, so the dashboard, the CLI and the agent all render the same facts.

## Finding timeline

`views.finding_timeline(timeline_result)` turns episodes into rows where these are **separate fields**:

| Field | Means |
| --- | --- |
| `observed_at` | when the source says it saw the finding |
| `applied_at` | when a change was recorded as applied (an operator/receipt fact) |
| `verified_at` | when a passing, target-bound proof closed the episode |
| `ingested_at` | when the desk received the observation |
| `recurrence_at` | when the finding came back in a new episode |
| `disposition` | the administrative state (`open`, `verified`, `suppressed`, `accepted_risk`, `false_positive`, `closed_manual`) |

`application_is_not_verification` is always true, `verification_required` is true until a proof exists, and
`late_ingestion` is true when ingestion lagged observation by more than an hour. A June 10 application, a June 15
verification and a June 16 ingestion read as three different facts; a late ingestion never looks like a late fix.

Each row also carries `source_coverage` and `projection_watermark`, so a person can see what was inspected and which
commit the answer reflects.

## Campaign membership

`views.campaign_page(page, receipt=None)` shows a page of the frozen membership plus counts whose authority is
stated:

- `board_preview_used` is false and `source` is `campaign_members`: the full membership is read through the ordinal
  cursor, never reconstructed from the bounded board preview;
- `member_count` and `total_members` come from the committed campaign and the membership table;
- when an attested receipt is supplied (`campaign --summary`), `authoritative` is true, `counts_source` is
  `attested_computation`, the counts come from the receipt and `receipt_id` identifies it;
- otherwise `authoritative` is false, `counts_source` is `membership_page`, and `counts_note` says the numbers come from
  stored member states. A page count is never presented as a computed count.

A campaign that is not committed, or that this installation may not read, returns a `state` of `unavailable` or `denied`
with `usable_for_decision: false` — not an empty success.

## Graph exploration

`views.graph_view(graph_result)` returns bounded nodes and edges where every edge says how it is known:

| Field | Meaning |
| --- | --- |
| `status` | `observed`, `derived`, `hypothesis` or `retracted` |
| `label` | `observed`, `derived by <version>` or `hypothesis` |
| `evidence` | retained evidence ids, or the derivation that produced the edge |
| `may_authorize` / `trusted_action_allowed` | true only for `observed` and `derived` edges |

Authority is decided from `status` alone, so a caller cannot annotate a hypothesis into authority. If any edge in the
returned neighbourhood is not authoritative, the view sets `trusted_actions_allowed: false` and lists the ids in
`hypotheses`: an unsupported or hypothesized relationship is visible and cannot justify a trusted action until a person
reviews it.

Depth is capped at two and the edge count is capped, with `truncated` set when the bound was reached.

## Freshness

`freshness()` (and every view) reports a state instead of implying currency:

| State | Meaning |
| --- | --- |
| `ok` | complete, within the maximum age, usable for a decision |
| `loading` | still being read |
| `partial` | the evidence set was incomplete or truncated |
| `stale` | older than the maximum age; the cutoff is reported and it is **not** current operational state |
| `recovery_incomplete` | a recovery did not finish, so the projection is not active |
| `denied` | this installation may not read that scope |
| `unavailable` | the requested artifact does not exist yet |

A graph answer's cutoff is its newest assertion, not the wall clock, so a stale graph says how old it is and does not
pretend to describe the present.

## CLI and agent surface

```
rgtriage campaign                        # committed campaigns
rgtriage campaign camp-1 --after 100     # one page of the frozen membership
rgtriage campaign camp-1 --summary       # the attested count computation
rgtriage campaign --graph <entity>       # bounded neighbourhood
```

The `rg_triage` tool exposes the same three as `action=campaign` with `campaign_id`, `after`, `summary` and `graph`.
The tool description tells the agent that a page count is not attested and that a hypothesis cannot close anything.

## What this does not do

It does not add a graph backend or a second storage path, it does not render unbounded graphs, and it does not return
evidence object bytes or secrets to a browser. The dashboard panels consume these models; they do not recompute them.