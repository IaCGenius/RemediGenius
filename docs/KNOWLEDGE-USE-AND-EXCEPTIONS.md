# Knowledge use and exception decisions

rc3 implementation: [Reusable knowledge quickstart](KNOWLEDGE-QUICKSTART.md) now
documents implemented applicability, contextual variations and refresh. Risk
acceptance remains separate. The current-behavior section below is historical rc2.

Correction: organizational knowledge variations are distinct from risk acceptance.
See [Knowledge foundation](KNOWLEDGE-FOUNDATION.md) for the governing design of
baseline applicability, contextual variations, reuse and refresh. The risk-acceptance
workflow below remains a separate possible feature, not the model for all knowledge.

Status: current behavior and next-release contract, 2026-10-12.
Structured exception enforcement described below is not implemented.

## What works today

Upload a policy, ownership record or runbook; label its topic, scope and owner.
Read the conversion, then capture a concise insight against an assessment with a
source citation. Review and approve that version. Investigations include approved
notes for that exact assessment. Notes are assessment-wide; resource applicability
is not validated. New assessments require renewed context review.

Proposals use fixed deterministic steps and reference approved note IDs. The UI
displays the referenced notes; the steps are not automatically tailored from them.
MCP agents can search documents and retrieve selected excerpts. The supplied skill
requests retrieval but cannot guarantee an agent did it. Upload is not proof of use.
Current search is literal-word search across the latest 500 source records; a miss
does not establish that no relevant policy exists.

Example prompt: “Investigate this finding. Retrieve relevant ownership, policy and
runbook sources. Show the versions used, unreviewed claims and conflicts. Separate
your suggested action from the rule result. Do not treat an exception document as
an enforced exception.”

## The user experience we need next

Use relevant knowledge, not the whole library. Select by question, resource,
organization/account/application scope and decision time. LLM relevance suggestions
are inference; applicability and approval status checks should be deterministic.

Each investigation and proposal needs a **Knowledge used** panel:

| Item | What the user sees |
| --- | --- |
| Applied context | Exact version, cited passage, approved statement and scope match |
| Decision impact | Owner identified, access constraint added, runbook selected or exception considered |
| Excluded context | Draft, expired, revoked, wrong scope, conflicting or unreadable, with a reason |
| Missing context | The specific decision blocked, with an Add context or Request review action |
| Provenance | Source observation, code-derived result, human assertion or AI interpretation |

Persist this context-use receipt with the proposal; later source changes cannot
rewrite its history. Guide onboarding around “Who owns this?”, “What access is
required?”, “Is an exception valid?” and “How do we verify and roll back?” The library
supports those decisions; uploading files is not the completed workflow.

## Exceptions are structured decisions

An uploaded document supports a proposed exception; it cannot approve itself.
Extraction may suggest fields, but a human must confirm them. Required fields:
exact rule/control, provider/account/resource scope, reason, accountable owner,
approver, effective and expiry times, cited versions, compensating controls and
their evidence, and a review date. Start with exact selectors, not wildcards.
Approval identity is a local operator assertion until authenticated approvals exist.

Lifecycle: draft → pending review → approved → expired / revoked / superseded.
Evaluate applicability at decision time from scope, rule, validity, revocation and
required control evidence; store the evaluation and inputs with the decision.

| Condition | Expected product behavior |
| --- | --- |
| Approved, current and matching | Keep finding visible; show “Exception applies until DATE”, owner and conditions; adapt risk treatment to its terms |
| Unreviewed or awaiting approval | “Exception claimed — not approved”; no risk-acceptance status |
| Expired or revoked | “Exception no longer applies”; remediation review required; no silent renewal |
| Wrong scope/control | Do not apply; show why it does not match |
| Missing/stale compensating evidence | “Cannot establish applicability”; request the exact missing evidence |
| Conflicting policies or decisions | Show both; require resolution; neither newest text nor the LLM silently wins |
| Missing owner/approver | Block approval and identify the missing field |

Exceptions change treatment of risk, not configuration or rule severity. Risk
accepted and remediated are distinct outcomes. Expiry must be evaluated without an
LLM; reminders are a separate future opt-in feature.

Example: a deliberately public distribution bucket has time-limited approval.
The public-access finding remains visible, with its approved purpose and monitoring
conditions. An unrelated bucket cannot inherit this exception. Expiry requests
renewal or remediation review; it does not claim the bucket configuration changed.

Today an exception file or approved note is context only. Keep the user's existing
exception register authoritative; CE cannot yet validate, expire or enforce it.

## Failure behavior belongs in the product

- Empty/image-only conversion: show Needs extraction review/OCR, not Knowledge ready.
- Changed source: preserve old citations; request review of affected decisions.
- Model unavailable: deterministic checks and reviewed context remain usable.
- No retrieval match: show missing context and search limits, not a confident conclusion.
- Conflicting approved notes: surface the conflict; approval does not prove truth.
- Sensitive sources: explain model disclosure at connection time; upload is not consent to model use.
- Embedded instructions: treat source text as data; it cannot grant tools or approvals.

## Release gates

1. Now: truthful onboarding and approved context visible in investigation/proposal views.
2. Next: resource applicability, review dates, revocation/supersession and persisted
   context-use receipts. Ambiguous context requires a decision, not silent resolution.
3. Exception gate: draft/review forms, deterministic applicability and distinct
   risk-treatment status. Test cross-account mismatches, expiry boundaries, revoked
   versions, conflicting decisions and missing control evidence end to end.
4. Then: retrieval-assisted proposals with citations and labeled inference. Hermes
   attachment intake and future connectors use the same lifecycle.

Do not advertise automatic policy-aware remediation or exception enforcement until
the corresponding gates pass. A new operator should understand why an action was
suggested, which knowledge mattered, what was excluded and what needs their review.
