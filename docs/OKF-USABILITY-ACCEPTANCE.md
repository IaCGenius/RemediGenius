# Knowledge usability update

2026-10-15 UTC. This builds on the native Hermes workflow, not the historical CE
console. It borrows the OKF idea of selected, attributable context without adding
a second agent runtime or claiming complete OKF schema compatibility.

## Implemented

- Guided knowledge conversation in the existing `ce-knowledge` skill: reuse what
  is already supplied, ask for one useful missing input, offer a readable draft,
  and distinguish chat from persisted knowledge.
- A compact source/applicability/decision-effect explanation for knowledge use.
  This is a skill instruction, not a deterministic knowledge-use ledger.
- Operator `list` command showing document IDs, scope and active/replaced status.
- Explicit `add --replaces ID` refresh in the same collection. New views omit
  replaced revisions; originals and old views remain available. Newer import time
  never silently wins. A previously replaced revision cannot be branched by a new
  sequential replacement; select the current active revision instead.
- Optional `--source-ref` records provenance without fetching external URLs.
- [Native knowledge quickstart](NATIVE-KNOWLEDGE-QUICKSTART.md). Historical console
  instructions remain preserved and clearly labelled.

## Local verification

Full repository suite: **195 passed, 4 skipped**. Focused library/runtime suite:
**36 passed**. New tests use explicitly synthetic local documents only; they are
not represented as AWS or organizational acceptance evidence. They verify old
view/original preservation, explicit refresh chains, repeat-import identity,
rejection of invalid replacement targets and no automatic precedence.

Initial sandbox runs failed or stalled during Windows temporary-directory setup;
the stalled processes were stopped and tests rerun successfully outside that
sandbox. The real operator policy was also listed successfully with its actual
scope. A missing collection produces a short actionable CLI error.

## Deployment

Runtime archive:
`68624e0b34f9a3a350894312001a80ba952891d3c2a0c6478462eaabe8168d0a`.
The source-only CE infrastructure plan changed three resources, added/destroyed
none. The retained profile was explicitly upgraded with a backup. All 59 integrity
entries passed; Qwen 3.8 Max and manual Kanban were retained. No customer AWS
configuration, organization policy or case was changed. Operator-side library
commands ship in the source package; they are not write tools granted to Hermes.

## Live acceptance

Session `20261015_041114_da3a64` completed with exit 0 using the real selected
operator S3 policy, whose content hash matched. Qwen separated tool operating
guidance from organization policy, correctly explained the conditional logs-only
exception, did not infer bucket purpose, showed a context/effect table and asked
for the missing classification. It stated that chat cannot publish knowledge and
that AWS/cases/knowledge were not changed. No AWS read was needed for this task.

The refresh command omitted scope, exposing a real usability defect. The operator
CLI now inherits scope on an explicit replacement unless a new scope is supplied;
new imports still require scope. Titles are also retained unless explicitly changed.
After this refinement all six library tests passed. An isolated copy of the real
operator policy/library exercised the exact no-scope replacement command, retained
its scope/title and original, and built a one-document view. Nothing was published
to the shared view. The native skill need not gain write access to make refresh usable.
The answer shortened source paths/hashes and its critic incorrectly questioned a
command from the loaded skill. Overall: useful policy/onboarding behavior, PARTIAL
for precise citation presentation. Do not call this complete knowledge-use auditing.

Fresh browser UI acceptance was unavailable because the browser tool failed to
initialize even after reset. The restored tunnel's login endpoint returned HTTP
200; that is a health check, not UI acceptance. This model test used Hermes's
native oneshot interface, not browser automation.

## Remaining usability limits

Import, selected-view creation and S3 publication remain operator steps. Direct
chat attachment import, authenticated Confluence sync, automatic expiry and a
persisted knowledge-use ledger are not implemented. This update improves guided
onboarding and refresh; it does not claim a one-click document connector.
