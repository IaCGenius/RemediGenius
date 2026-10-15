# Vision checkpoint — experiment now, finish the knowledge loop next

Recorded 2026-10-14. This describes the saved implementation and acceptance
records, not a new live validation or a release approval.

Later the same day, the owner requested work on the operating gap. See
[operating-loop guide](OPERATING-LOOP.md) and its linked acceptance record for
daily checks, saved native Kanban cases and remediation follow-up. This remains
an incremental step; it does not complete the knowledge/continuous-assurance vision.

> Your core architecture is implemented. Your larger vision—a security system
> that accumulates organizational understanding and continuously helps improve
> posture—is only partly implemented.

The owner wants to experiment with the current system before returning to finish
this vision. Preserve the current work. This checkpoint does not request a runtime
change, deployment, automatic upgrade or public release.

## The intended outcome

Use the security tools an organization already has. Pull relevant observations,
preserve trustworthy evidence, apply selected organizational knowledge, investigate,
prepare an actionable proposal, and reassess. Hermes is the conversational brain;
collection, normalization, permissions and evidence remain independently inspectable.

The differentiating loop is:

**Understand my environment → use my organization's knowledge → explain what
matters → remember my decisions → check whether those decisions still hold.**

## Where we actually are

| Original idea | Current native CE position |
|---|---|
| Hermes as the brain, readable skills and replaceable models | Implemented: one native CE profile, security skills and Hermes provider configuration; Qwen used for validation. |
| Reuse AWS-native tools, with collection on demand | Scoped executor supports 44 operations across 10 services. Real Security Hub, CloudTrail and multi-account EC2 journeys tested; not every operation is live-tested. |
| Deterministic collection and normalization | Separate executor preserves original responses, defined summaries, observation times, hashes and receipts. |
| Disposable compute and durable storage | Spot runtime, separate Lambda collection and S3 evidence/knowledge implemented. Sessions/configuration remain on retained encrypted EBS, not S3 session backups. |
| Reusable capabilities rather than a script per question | Generic executor and operation schemas implemented. Unsupported operations still need admission and testing. |
| Shared organizational knowledge, exposed in selected slices | Intake, Markdown conversion, collections, provenance and selected views implemented. Publishing a view and retrieving it are distinct steps. |
| Explain how accumulated knowledge affects decisions | Partial. The agent can retrieve and cite context; deterministic knowledge-use receipts and a complete reusable decision history are missing. |
| Scoped exceptions and conflicting knowledge | Skills can interpret context. Persistent conflict resolution and deterministic applicability are not implemented in the native runtime. |
| Proposals and reassessment | Investigation/proposal guidance and deterministic snapshot comparison exist. Proposal quality needs human review; a changed record is not proof of remediation. |
| Remember false positives and resurface changed risks | Native case decisions can record scoped false positives/accepted risks. Automatic applicability, suppression and reopening are not implemented. |
| Continuous CISO-relevant information | Daily deterministic snapshots and comparisons now persist in S3 independently of Spot. Recurring prioritized AI briefings and notifications are not implemented. |
| MCP/API access from existing AI workflows | Proposed native interfaces; older implementations are preserved but not connected to the native CE runtime. |
| Easy onboarding for a new company | Infrastructure and operating instructions exist. Effortless onboarding has not been demonstrated with an independent new organization. |

This is more than a chatbot: supported questions can produce real AWS observations
through scoped execution, durable evidence and repeatable comparisons. It is not
yet the complete organizational security second brain.

Implementation effort has so far gone more heavily into execution controls than
into a simple, visible knowledge and decision loop. That imbalance is the main
product gap to address, rather than adding connectors for their own sake.

## What the current experiments should reveal

Use real supported AWS questions and retain the session/run references. For each
experiment, record a short note:

- What you asked and which account/region/time period you intended.
- What was useful, confusing or missing in the answer.
- Which evidence receipts supported the answer and what coverage was incomplete.
- Which supplied knowledge the agent retrieved or claimed to use.
- What you expected it to remember or do differently next time.

Keep account details, transcripts and AWS exports in private local working storage
or the configured private evidence store, not committed public documentation.
No new administrative process is needed to experiment.

Known limitation from acceptance: Qwen once converted missing information into
an assertion about what the user had said. The review model also made incorrect
objections where its excerpts lacked context. Evidence remains inspectable, but
model review is not a correctness guarantee. Partial or denied collection must
not be interpreted as secure posture.

## Resume with one complete experience

After the owner's experiments, prioritize this end-to-end experience:

1. Investigate a real AWS finding and retain its evidence references.
2. Apply a relevant organization policy or scoped exception, showing the source.
3. If sources materially conflict, preserve both and ask only for the decision
   needed to proceed. Save a small readable resolution; no approval committee.
4. Record the operator's decision with scope, reason, source versions and review
   date. Keep it distinct from cloud facts and model interpretation.
5. Reassess with fresh evidence and explain why the decision still applies,
   needs review or no longer applies. Missing evidence must remain unknown.
6. Show what knowledge was retrieved separately from what the model claims
   influenced the recommendation.

These steps are a proposed completion target, not a claim that the whole loop
already works. Reuse existing components and readable files; avoid another custom
console or a separate collector for every question. The owner decides publication.

Resume instruction:

> Read this checkpoint and RESUME-HANDOFF.md. Review my experiments first. Preserve
> the Hermes-first architecture and finish the simplest useful organizational
> knowledge/decision/reassessment loop. Distinguish implemented behavior from
> plans, keep evidence deterministic, and validate changes with real AWS and Qwen
> before updating release claims.

## Supporting records

- [Resume handoff](RESUME-HANDOFF.md): saved source, runtime and reconnect state.
- [Product and integration contract](CE-PRODUCT-AND-INTEGRATION-CONTRACT.md):
  CE value, extension points and proposed decision lifecycle.
- [Knowledge use and control mapping](KNOWLEDGE-USE-AND-CONTROL-MAPPING.md):
  intake, visibility, exceptions and unfinished mapping/use receipts.
- [Acceptance results](CE-RUNTIME-ACCEPTANCE.md): actual validation and limitations.
