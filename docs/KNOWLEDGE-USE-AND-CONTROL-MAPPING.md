# Show what knowledge CE has, what it used, and what it can assess

Status checked against source on 2026-10-14. This is a usability and implementation
plan alongside instructions for existing tooling; proposed behavior is labelled.

Current continuation: the existing `ce-aws-security` skill now contains a
`references/layered-assessment.md` procedure for source-native control mappings
and business prioritization. No separate `ce-control-mapping` agent is needed for
that first step. `ce_knowledge` now returns metadata and verifies content hashes
with each content read. This is retrieval provenance, not a complete knowledge-use
ledger or deterministic applicability engine. See [current offering](CURRENT-CE-OFFERING.md).

## The user-facing promise

For every recommendation, the operator should be able to follow:

**AWS observation → technical control → applicable organization knowledge →
recommendation → verification.**

Framework mappings add a separate link from a technical control to a named,
versioned requirement. They do not prove the requirement is satisfied.

Accumulation should mean reusable, attributable context and decisions—not simply
more files or an agent remembering more conversation. Keep three stores distinct:
source evidence, operator knowledge, and model-generated interpretations. A model
answer does not automatically become trusted organization knowledge.

## What users can stage and where it is useful

These are suggested collection names, not new mandatory taxonomy.

| Collection | Useful contents | Where it affects an investigation |
|---|---|---|
| `org/policies` | Account baseline, logging/retention requirements, access rules | Explains organization expectations alongside observed configuration |
| `apps/payments` | Owner, purpose, data sensitivity, environments and resource/account identifiers | Prioritizes impact and identifies the right owner; identifiers establish applicability |
| `org/architecture` | Network boundaries, shared services, logging destinations | Guides evidence selection and identifies assumptions needing live verification |
| `org/runbooks` | Approved investigation and remediation procedures | Shapes proposals and verification steps; grants no execution permission |
| `org/exceptions` | Exact scope, baseline variation, reason, owner, effective/expiry dates | Explains applicable variations; never changes native AWS severity or proves safety |
| `org/decisions` | Confirmed lessons from incidents or prior investigations, with receipts | Reuses operator knowledge instead of repeatedly rediscovering it |
| `frameworks/aws-baseline` | Named framework/version, applicable controls, source references, reviewed mappings | Connects technical evidence to requirements; avoid unversioned control numbers |

Start with an account/application ownership note and one baseline. Do not require
an operator to upload all governance documents before their first useful AWS read.
Never stage credentials. Scope the view to the data the model is permitted to see.
Use framework material the operator is entitled to use; public reference links and
control identifiers do not imply permission to redistribute a whole publication.

### Existing staging workflow

The operator CLI accepts MD, TXT, CSV, PDF, DOCX, PPTX and XLSX, up to 5 MB per
source, subject to format/conversion checks. The document dependencies must be
installed; image-only documents need an OCR/readable version. It preserves the
source, extracted Markdown and metadata. Conversion does not establish correctness.

Illustrative commands using an operator-created source file:

```powershell
python -m rgce.knowledge_library --root .rgce/library add --collection org/policies --file .rgce/inbox/aws-baseline.md --scope "AWS development accounts; owner and applicability stated in document" --title "AWS development baseline"
python -m rgce.knowledge_library --root .rgce/library view --collection org/policies --output .rgce/views/aws-dev-v1
```

The input file must exist. Add other sources/collections as needed, then explicitly
select each collection with repeated `--collection` arguments. Selection is exact,
not automatically recursive. Each exported view needs a new output directory.

The library stores `<collection>/<document-id>/source.*`, `content.md` and
`metadata.json`. A view contains selected content/metadata, `index.md` and
`manifest.json`. On workstation, set `knowledge_dir` to that local view and restart the launcher.
The agent reads the mounted view at `/opt/data/shared/knowledge`. The single-host
Spot stack uses [reviewed chat notes](NATIVE-KNOWLEDGE-QUICKSTART.md#start-in-the-hermes-chat);
it has no Terraform `knowledge_view` input or automatic file-view hydration.

Importing locally does not publish it to the running agent. Publishing a view
does not prove the agent read it. The current metadata includes source/content
hashes, origin, title, scope and import time; owner, policy dates and applicability
details must be supplied in the content. Import time is not policy effective time.

To refresh, edit the original, re-import, and build/publish a new selected view.
Direct editing of generated content breaks hash consistency and is discouraged.
The library retains versions. Use `list --collection NAME` to see their IDs and
`add --replaces ID` to explicitly replace an active document in the same collection.
New views omit replaced revisions; old files and views remain intact. Without an
explicit replacement, both sources remain active; import time does not decide authority. Conflicting versions must not be silently blended.

## How users should see accumulation and use

Prefer a readable inventory and a short answer section before building another
dashboard. Both should be exportable as Markdown/JSON and available to an external
agent through the proposed interfaces.

### 1. Inventory: what is available to this agent?

Today `index.md`, `manifest.json`, adjacent metadata and the `ce_knowledge` tool
provide the basic inventory. Ask: “Show my selected knowledge, its scope and source
dates. What important context is missing for this account?”

Proposed inventory additions: authoritative revision, owner, valid/review dates,
supersession, stale/conflicted state and last documented use. Show what is in the
selected view separately from what exists elsewhere in the operator's library.

### 2. Explanation: how did knowledge affect this answer?

Every material recommendation should include a compact **Knowledge used** section:

| Item | Explanation required |
|---|---|
| Applied | Exact document/version/hash and relevant passage; matching scope; the recommendation or priority it influenced |
| Consulted only | Read for context, but did not establish or change this conclusion |
| Excluded from considered candidates | Expired, wrong scope, superseded or conflicting; reason stated |
| Missing | Required context not supplied or applicability could not be determined |

Do not claim to have evaluated every library document when only a selected view
was read. Example, explicitly illustrative: “Development retention exception v2
changes the proposed retention target for this resource. The AWS configuration
observation is unchanged. Production policy was not applied because this is a
development resource; the owner mapping supplied that context.”

**Current limit:** the knowledge skill requests citations and applicability
reasoning, and native session traces show tool retrievals. Retrieval proves content
was provided to the model, not that it actually influenced its reasoning. The native
runtime does not yet emit a deterministic applied/excluded knowledge-use receipt.
The explanation of influence is a model assertion and should be labelled as such.

### 3. History: what did we learn or change?

Proposed per-investigation knowledge-use receipt: run/session ID, selected view
hash, retrieved documents and ranges, operator-approved revisions, scope checks,
model-claimed uses tied to recommendation IDs, exclusions and reasons. Store it
beside the investigation artifacts in S3 so compute replacement does not erase it.
Keep mechanically observed retrieval separate from model-claimed influence.

Show source updates, confirmed decisions reused, expired context and changed
recommendations. Usage count is not a quality score. A new incident lesson remains
a draft until the operator deliberately publishes it. No model retraining or
automatic self-modification is required to accumulate this knowledge.

The preserved console has `knowledge_use` records and an exact-scope resolver in
[knowledge.py](../rgce/knowledge.py); these are useful concepts to reuse, not an
already-connected native receipt system. Keep the single-operator workflow simple.

## Technical controls and framework mappings

**Today: partial support, not a general mapping engine.** `ce-aws-security` explains
AWS findings and control context. The Security Hub collector retains `Compliance`
in normalized findings and preserves complete raw responses. Therefore mappings
present in a source finding can be read with the existing evidence tool. The skill
does not currently guarantee a versioned mapping table or completeness assessment.
The older S3/security-group/IAM rules are narrow checks, not a full CIS assessor.

Security Hub's compliance metadata can include `SecurityControlId`,
`AssociatedStandards`, `RelatedRequirements` and check status. Use those fields
when supplied; consult raw legacy `ProductFields` where needed, rather than
inventing a mapping from the finding title. Different finding formats need explicit
handling. Source: [AWS control finding metadata](https://docs.aws.amazon.com/securityhub/latest/userguide/controls-findings-create-update.html).

Distinguish **CIS Benchmarks**, which specify technology configuration recommendations,
from **CIS Controls**, which organize broader safeguards. Always retain the exact
publication/version and mapping source. See [CIS Benchmarks overview](https://www.cisecurity.org/cis-benchmarks-overview).

### Recommended new skill: `ce-control-mapping` (not implemented)

Its job would be to:

1. Identify a technical control from a source control ID and resource evidence.
2. Retrieve source-native mappings first, then a selected authoritative/versioned
   mapping catalog. Retrieve only relevant entries, not an entire framework.
3. Distinguish an authoritative published mapping, an operator-reviewed mapping
   and an AI-suggested mapping awaiting review. Similar wording is not equivalence.
4. Link each control to evidence requirements and an available collection/check
   method. A control that lacks a tool is UNASSESSED, not passed.
5. Apply relevant organization context separately and show its use receipt.
6. Output control, requirement/version, mapping provenance, scope, evidence/time,
   source check status, coverage limitations and proposed next step.

The deterministic component should join validated identifiers/catalog records,
track versions and preserve results. The LLM explains applicability and can draft
mapping suggestions; it must not manufacture authoritative IDs or certifications.
Use catalog data and existing AWS checks, not hand-code a new collector per control.

One technical control can contribute evidence to several frameworks. Keep that
many-to-many relationship without counting duplicate source findings as separate
protections. A mapping means “relevant evidence,” not “fully satisfies.” A technical
check cannot establish organizational training, governance or operating effectiveness.
An accepted exception is not PASS, and missing metadata is not no applicable control.

Proposed user request: “Show which observed technical controls map to our selected
CIS AWS benchmark version. Cite the source mapping, show failed/unknown/unassessed
separately, and identify requirements needing manual evidence.” No percentage of
framework compliance should be calculated without a defined applicable-control
denominator, explicit exclusions and adequate assessment coverage.

## Small implementation sequence

1. Add the inventory and Knowledge used answer convention, with honest status labels.
2. Emit native retrieval/use receipts and expose them as readable artifacts.
3. Add the mapping skill backed initially by actual Security Hub metadata; prove
   missing-field, legacy-format, duplicate-control and version-change handling.
4. Add selected published/operator mapping catalogs and manual-evidence requirements.
5. Add deterministic freshness/applicability checks and decision revalidation from
   the [disposition design](CE-PRODUCT-AND-INTEGRATION-CONTRACT.md).

Acceptance must include unrelated and expired documents, conflicting policies,
missing resource scope, malicious embedded instructions, an unmapped control and
one control linked to several standards. It must also show that an operator update
changes context while leaving historical AWS evidence intact.

This document does not change the running skills, deployment or tested bundle.
