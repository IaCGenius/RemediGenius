---
name: ce-cloudtrail-triage
description: Apply local high-risk event patterns to collected CloudTrail management events. Distinguish successful events from API errors.
license: Apache-2.0
---

# CloudTrail high-risk event triage

Start from a CloudTrail LookupEvents or event receipt.

## Working procedure

1. **Frame** — State the time window and receipt ID.
2. **Inspect** — Extract EventName, EventSource, UserIdentity, ErrorCode, and ResponseElements exactly.
3. **Deterministic checks** — Match against the pattern list in `references/high-risk-events.md`.
4. **Interpret** — List matched events with receipt citation. Note successful vs error.
5. **Propose** — Optional follow-up reads. Label AI-generated.
6. **Review** — Call `ce_review`.

## Limits

- LookupEvents covers regional management events for 90 days only.
- Does not query external threat feeds.

Read `references/high-risk-events.md`.
