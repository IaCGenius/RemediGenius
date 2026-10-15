---
name: ce-scanner-interpreter
description: Interpret local Prowler, Checkov, or Trivy report files that the operator has placed in evidence or knowledge. Does not run the scanners.
license: Apache-2.0
---

# Local scanner report interpreter

Use only when the operator supplies a local report file (JSON or CSV) via shared-evidence or knowledge import. Never invoke the scanner tools.

## Working procedure

1. **Frame** — Identify the report path and format (Prowler JSON, Checkov JSON, Trivy JSON).
2. **Inspect** — Read the file with shared-evidence or knowledge tools. Extract check IDs, resources, and severities exactly.
3. **Deterministic checks** — Map known check IDs using `references/scanner-schemas.md`.
4. **Interpret** — Group by severity and resource. Cite file path and line or check ID.
5. **Propose** — Link to existing CE remediation skills (e.g., ce-s3-deep-dive) when the check matches. Label AI proposals.
6. **Review** — Call `ce_review`.

## Limits

- Does not download or run Prowler, Checkov, or Trivy.
- Unknown check formats are reported as unsupported.

Read `references/scanner-schemas.md`.
