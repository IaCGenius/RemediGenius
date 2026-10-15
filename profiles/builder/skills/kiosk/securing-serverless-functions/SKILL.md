---
name: securing-serverless-functions
description: "Security checklist for kiosk function code: input validation, no secrets in code/env/logs, least data in outputs, safe parsing, injection risks. Use before every kiosk submit."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  upstream: mukul975/anthropic-cybersecurity-skills@54a798831d2266a3ca61ce68a7acb80b81160d57 skills/securing-serverless-functions
---

# securing-serverless-functions (adapted for the kiosk)

The kiosk already enforces much of upstream's hardening: one role per class and agent (least privilege,
made by Terraform), signed code only, pinned dependencies, no network in tests, forbidden process and
dynamic-code calls. What remains is **your code**. Check before every `kiosk submit`:

- **Validate the unit**: types, sizes, allowed values; return FAILED with a reason on bad input.
- **Treat input text as data**: never build code, shell commands, SQL or file paths from it.
- **No secrets** in code, tests, `env`, outputs or logs. `ctx.log` redacts common key shapes, but do not log
  input wholesale.
- **Least data out**: write only what the task needs to outputs; no copies of raw inputs "just in case".
- **Safe parsing**: `json.loads`, never `eval`; bound loops and sizes; handle malformed data.
- **Fail closed**: an unexpected state returns FAILED, never a guessed success.

Upstream's IAM, secrets-manager, scanning and monitoring steps are the kiosk's job (Terraform and the gate),
not yours: never try to create roles or policies. Background: `references/upstream/UPSTREAM-SKILL.md`.
