# Reuse the CE core in the hosted product

CE and the hosted product should share versioned contracts and tested domain code, not exchange whole working directories. This release does not modify or resume the existing hosted engine.

## Bring across

- Evidence envelopes, content hashes and origin labels from `rgce/core.py` and `rgce/store.py`.
- Versioned deterministic rules and regression cases; keep source-provider findings distinct.
- Knowledge concepts, exact-scope variations, supersession/withdrawal, dependency handling and use receipts from `rgce/knowledge.py`.
- Readable export and citation contracts from `rgce/workspace.py`.
- Bounded source collection and provenance from `rgce/adapters.py` and `rgce/onboarding.py`.
- Object persistence and recovery contract, including original-file retention and write-before-success behavior.
- Restricted read/storage role patterns and the fixed-code Lambda reader; carry its limitations as well as its code.
- Synthetic fixtures and sanitized acceptance results. Raw customer/test-account exports, credentials and Terraform state stay private.

## Do not inherit as hosted guarantees

The local operator's review is not authenticated organizational approval. Single-writer S3 recovery is not a multi-tenant transactional database. Local API tokens are not organization authentication. A successful model transcript is not factual correctness or prompt-injection immunity. Readable skill instructions do not constrain an agent's other tools.

The hosted layer must supply tenant authorization, authenticated reviewers, concurrent revision control, scheduling/budgets, credential brokering, managed retention, and independent remediation approval/execution. Keep these outside the reusable rules/knowledge contracts.

## Integration sequence

1. Record the CE commit and artifact hashes as an upstream dependency; compare its envelope with the existing engine's result format.
2. Add a thin translator at the existing collector output boundary. Preserve account/tenant scope and source provenance; never infer approval from imported metadata.
3. Shadow-run both pipelines on the same permitted snapshots. Compare findings and knowledge selection, especially incomplete evidence and scoped variations.
4. Adopt file exports and evidence-backed investigations first. Keep the existing infrastructure and schedules unchanged until contract checks pass.
5. Reuse the domain package as a pinned dependency after defining its stable public API. Do not copy CE's SQLite implementation into the hosted tenancy layer by default.
6. Add hosted execution separately, retaining a distinct action identity and collecting new evidence after an approved change.

Releases should test the same synthetic source -> finding -> guidance -> proposal -> reassessment contract in both products. This makes CE useful independently while keeping improvements transferable.

## rc8 correctness contracts to carry forward

Reuse the regression cases for revision-chain ordering after clock rollback, retained variation scope/baseline on edit, transitive prerequisite exclusion, and complete document receipt recovery. The host's transactional store must also handle an uncertain durable commit before accepting another approval; CE's restart-required guard is a single-process mechanism, not the hosted concurrency design. Keep immutable historical decision receipts separate from evaluating today's guidance with a supplied freshness clock.
