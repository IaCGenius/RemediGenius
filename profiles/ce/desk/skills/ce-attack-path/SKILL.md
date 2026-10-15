---
name: ce-attack-path
description: Build a short, citation-backed potential attack path from a small set of findings and evidence. Separate observed facts from inferred steps.
license: Apache-2.0
---

# Grounded attack-path narrative

Use after triage when the operator asks for possible attack paths. Limit to findings already in receipts.

## Working procedure

1. **Frame** — List the receipt IDs and finding IDs that will be used.
2. **Inspect** — Extract exact resources, permissions, and public exposure fields.
3. **Deterministic checks** — Follow the connection rules in `references/path-rules.md`. Only connect facts that the rules allow.
4. **Interpret** — Write the path as numbered steps. Mark each step “observed” or “inferred”. Stop when evidence ends.
5. **Propose** — Optional containment notes, labeled AI-generated.
6. **Review** — Call `ce_review`.

## Limits

- Does not invent resources or permissions.
- Does not call external threat-intelligence services.
- Maximum three inferred steps.

Read `references/path-rules.md`.
