# rc4 simplification validation

Local Windows validation with synthetic content, 2026-10-12:

- 85 CE tests passed, including simplified drafting, inherited variation scope,
  revision identity, bounded read-only AI review, token checks and Markdown copies.
- 38 deterministic rule cases, legacy result checks and 30 kiosk tests passed.
- Simple browser workflow passed: plain note, human confirmation, edit, hidden
  technical fields, generated review folder, AI review request, unapproved imported
  AI suggestion and mobile layout.
- Existing browser smoke and advanced knowledge lifecycle tests passed through the
  simplified navigation.
- The rc4 wheel built successfully.

Editing a generated Markdown review copy was tested: it does not affect the active
concept, and explicit regeneration restores the managed view. AI suggestions were
synthetic test responses, not live provider outputs. No model inference, AWS change,
external message or publication occurred during validation.

The console offers an existing-agent handoff, not an embedded inference service.
See KNOWLEDGE-SIMPLE.md for the user workflow and direct-edit guidance.
