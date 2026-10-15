---
name: ce-terraform-snippets
description: Provide inspectable Terraform hardening snippets for common findings. Adapt them to the specific resource and cite the source snippet.
license: Apache-2.0
---

# Terraform hardening snippets

Use when the operator requests Terraform instead of CLI. Start from a receipt that identifies the resource.

## Working procedure

1. **Frame** — Name the resource type, identifier, and receipt.
2. **Inspect** — Extract current configuration fields.
3. **Deterministic checks** — Select the matching snippet from `references/snippets.md`.
4. **Interpret** — Adapt the snippet with the exact resource name/ID from the receipt. Cite the snippet section.
5. **Propose** — Output the adapted Terraform. Label “AI-generated — operator review required”. Include a verification note.
6. **Review** — Call `ce_review`.

## Limits

- Snippets are static examples. They do not generate complete modules.
- Does not run terraform plan or apply.

Read `references/snippets.md`.
