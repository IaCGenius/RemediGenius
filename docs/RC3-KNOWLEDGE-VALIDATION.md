# rc3 validation receipt

Validated locally on Windows with synthetic inputs, 2026-10-12.

- Complete release script: 80 CE tests, 38 deterministic rule cases, legacy result
  checks and 30 Lambda kiosk tests passed.
- Final knowledge/core run after adding AI concept-citation coverage: 36 passed.
- Existing browser smoke passed (sample, evidence, proposals, comparison, documents,
  assessment-note approval, MCP config, source-text injection and mobile layout).
- Knowledge browser passed: draft/review/publication, exact baseline variation,
  missing application context, human mapping, effective guidance, saved receipt,
  changed baseline and dependent review. Original receipt remained reproducible.
- Mobile revision-hash wrapping was corrected and the browser check passed.
- `pip check`: no broken requirements. No cloud or model calls in these tests.

Knowledge regression cases include cross-account exclusion, preserved unrelated
requirements, missing and conflicting knowledge, exact expiry boundary, future
effective dates, stale-source dependency propagation, optimistic revision rejection,
malformed YAML and alias/tag rejection, unknown-field preservation, imported-trust
isolation, deprecated exports and scoped dependencies. AI annotations may cite
resolved concepts but remain unreviewed model interpretations.

No live AWS collector or external Hermes/model session was exercised in this change.
See KNOWLEDGE-QUICKSTART.md for supported behavior and explicitly deferred features.
