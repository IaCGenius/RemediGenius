---
name: ce-case-summary
description: Generate a self-contained Markdown summary of a saved case including receipts, knowledge citations, proposals, and critic notes.
license: Apache-2.0
---

# Audit-ready case summary

Use with ce_case when the operator wants an exportable report.

## Working procedure

1. **Frame** — Identify the case ID.
2. **Inspect** — Pull case notes, linked receipt IDs, and knowledge sources via ce_case and shared-evidence.
3. **Deterministic checks** — Include every receipt ID and timestamp that the case references. Follow the template in `references/summary-template.md`.
4. **Interpret** — Assemble the Markdown. Separate observed facts, knowledge, and AI proposals.
5. **Propose** — None (this skill only exports).
6. **Review** — Call `ce_review` on the draft summary.

## Limits

- Does not modify the case.
- Does not include raw credentials or full policy documents unless already in the case notes.

Read `references/summary-template.md`.
