# Public product and private testing boundary

The public repository contains product source, the Hermes profile, reusable deployment/install tools,
synthetic fixtures, repeatable tests, licensing and user-facing documentation. Sanitized release validation
belongs here too: users need to know what was and was not tested.

Private testing contains environment settings, Terraform state, credentials, account inventories, raw logs,
chat databases, imported documents, ad hoc SSM scripts, screenshots and chronological debugging notes.
Keep these outside the public checkout when possible. `.rgce/` remains ignored for existing active tooling.

## Migration rules

1. Inventory and classify before moving. `.gitignore` does not remove already tracked files or Git history.
2. Copy private evidence to a separate private workspace and verify hashes before retiring originals.
3. Update relative-path dependencies before moving active Terraform state or helper scripts. Preserve rollback
   and test connectivity. Never relocate or delete active state merely to make the working tree look clean.
4. Replace detailed lab diaries with concise, sanitized public results and reproducible procedures. Preserve
   product lessons and known limitations; remove private identifiers and machine-specific commands.
5. Build release artifacts from reviewed allowlists, then inspect their contents independently of Git status.

Public tests are part of the product's maintainability, not local clutter. Keep `tests/`, synthetic samples,
Terraform modules and the reusable Spot validation harness. Exclude ad hoc session scripts and test outputs.

This migration is staged. Creating a private workspace does not mean all historical local state has moved,
nor does an ignored directory prove that older public commits contain no private information.
