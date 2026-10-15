---
name: ce-cis-mapping
description: Map Security Hub findings and configuration evidence to CIS AWS Foundations Benchmark and AWS FSBP controls using local tables. Cite exact findings and controls.
license: Apache-2.0
---

# CIS / FSBP mapping

Use when the operator asks for framework alignment. Start from Security Hub findings or configuration receipts.

## Working procedure

1. **Frame** — Identify the finding IDs or resource types and the receipt.
2. **Inspect** — Extract native severity, resource, and control IDs exactly as returned.
3. **Deterministic checks** — Look up the finding or resource type in `references/cis-fsbp-map.md`. Report the matching CIS/FSBP control IDs and levels exactly as listed.
4. **Interpret** — State which controls are covered, partial, or not evidenced. Cite the receipt and the map entry.
5. **Propose** — Optional prioritization note only. Label AI proposals.
6. **Review** — Call `ce_review`.

## Limits

- Mapping tables are static and local. They do not query external compliance services.
- Absence of a mapping does not mean the control is satisfied.

Read `references/cis-fsbp-map.md` for the lookup tables.
