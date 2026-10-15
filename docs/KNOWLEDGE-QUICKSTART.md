> Historical console workflow. Native Hermes users: see [the current knowledge guide](NATIVE-KNOWLEDGE-QUICKSTART.md).

# Reusable knowledge: advanced operations

For the simplified rc4 workflow, start with [Your knowledge](KNOWLEDGE-SIMPLE.md).
The detailed controls described below now live under Knowledge > Advanced.

Open **Shared knowledge → Reusable organizational guidance**. This is separate
from the older assessment-specific note form. No model or cloud calls are required.

## Publish a baseline and a contextual variation

1. Add a source file or paste source text in the source library. Check the conversion.
2. Create a concept. Give it a stable ID (`networking/private-backends`), title,
   requirement key (`networking.backend-access`), concise statement, author and
   review timestamp (`2027-01-01T00:00:00Z`). Select its supporting source.
3. Set exact applicability fields. Blank fields mean unconstrained within this
   local workspace, not unknown and not access control. Use one requirement per
   concept so an override cannot accidentally replace an entire standards document.
4. Save the draft, open Review concept for publication, inspect its metadata and
   source citations, then publish with a local reviewer name.
5. For a variation, create another ID using the same requirement key. Select the
   exact published baseline it overrides. Retain every baseline scope selector and
   add application/environment/component selectors as needed. Broader scope is rejected.
6. Keep unchanged requirements as separate concepts with their own requirement keys.
   A variation to public ingress must not erase a private-backend requirement.

Reviewers are local operator assertions, not authenticated organizational identities.
Publishing authorizes the concept and its declared baseline relationship locally.

## Use the knowledge

Open **Investigate** on a finding. The Reusable knowledge used panel shows effective
concept versions, modified baselines, exclusions, missing context and conflicts.
If the application, environment or component is unknown, fill in the reviewed
resource-context form. This mapping is pinned to that assessment and resource;
new observations require confirmation rather than inheriting stale classifications.

`READY` means explicit applicability checks passed. `NEEDS_CONTEXT` means potentially
relevant knowledge is missing, stale, withdrawn, conflicting or not yet effective.
`NO_KNOWLEDGE` means no eligible guidance was found; it does not mean policy compliance.
When blocked, candidate statements may be displayed for review but are not supplied
as resolved contextual guidance in a proposal.

**Prepare proposal** includes applicable guidance beside the deterministic template
and saves an immutable knowledge-use receipt. This does not rewrite code or alter
scanner findings, severity or cloud configuration. The operator adapts the exact
change to the cited guidance. **View saved knowledge-use receipts** compares the
latest 100 historical receipts with current resolution and marks CONTEXT_CHANGED.

MCP `investigate` and `prepare_proposal` expose the same resolution without writes.
`list_knowledge_concepts` provides current publications and review health. MCP calls
do not persist receipts; the console action does. All nine MCP tools remain read-only.

## Refresh without losing history

Upload the revised source, select old/new versions in **Refresh after a source
changes**, and record the replacement. This is an explicit source relationship;
CE does not infer that identical filenames represent successive versions.
Concepts citing the old source and variations depending on them become needs-review.

Use **Revise this concept**, select the new source, review changes and publish.
Then revise affected variations to reference the new baseline. Existing approvals
do not transfer to changed content. Concurrent revisions must reload the current
version rather than silently overwrite it. A review timestamp is stale on or after
the exact instant; reading a concept never extends it.

Withdrawal blocks a version's use. A withdrawn applicable concept remains an explicit
review blocker until its replacement is reviewed; CE does not silently fall back
to broader guidance. Historical records and old receipts remain inspectable.

## OKF interoperability

Use **Export OKF** for a Markdown concept with YAML frontmatter. The file import
control brings an OKF concept into a draft. Standard and unknown non-CE metadata
are preserved; imported `verified` assertions never create local approval.
Unknown types can be retained as drafts. Publishing requires the supported `rgce`
applicability extension. Superseded/withdrawn publication exports are deprecated.

Supported extension (all relations use exact local publication hashes):

```yaml
type: Security Guidance
title: Portal public ingress
status: draft
stale_after: 2027-01-01T00:00:00Z
rgce:
  requirement: networking.ingress
  scope:
    account: "111122223333"
    application: portal
    component: ingress
  overrides: []   # Select a baseline publication in the UI, or enter its hash.
  depends_on: []  # Other required, reviewed concept versions.
```

Additional exact selectors: provider, region, resource, rule, environment.
`effective_from` is supported inside `rgce`. Unknown CE extension fields are rejected
to avoid pretending unsupported conditions were evaluated. General expressions,
wildcards and semantic conflict resolution are not supported. Multiple effective
concepts for the same requirement produce a conflict requiring review.

This is single-concept OKF exchange, not a complete bundle migration implementation.
Cross-workspace source IDs and dependency hashes must be re-established locally;
generic imports do not remap or execute dependencies. No attester or executor from
an imported document is run. There is no certification claim of full OKF conformance.

## Validation

Automated tests exercise reuse across assessments, narrower variations, preserved
requirements, cross-account exclusion, missing mappings, conflicts, expiry boundaries,
future-effective concepts, concurrent revision rejection, source-change propagation,
historical receipts, imported-trust isolation and malformed metadata rejection.
Browser tests exercise authoring, publication, resource context, proposal receipts,
baseline revision, dependent review and narrow screens using synthetic data only.

Run `scripts/test.ps1`. For optional UI checks against a running local console:
`python tests/browser_knowledge.py` and `python tests/browser_smoke.py` with Playwright
and Edge installed. These add synthetic records; use a separate `--home` directory.

Still future: automatic extraction/synthesis into concepts, semantic search,
scheduled connector refresh, authenticated multi-user approvals, full portable bundle
dependency migration and runtime computation attestation. Current deterministic
checks and content hashes do not establish those capabilities.
