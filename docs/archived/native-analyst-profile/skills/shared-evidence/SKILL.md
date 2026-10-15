---
name: shared-evidence
description: Inspect the CE shared evidence catalog, collection receipts, normalized facts and scoped organization knowledge. Use for source availability, coverage, Security Lake, findings, and evidence-backed investigation questions. Reads files only; never collects from cloud APIs.
license: Apache-2.0
metadata:
  version: 0.1.0
---

# Shared evidence with receipts

Shared input is mounted read-only at `/opt/data/shared`. S3 is the durable source;
the collection/staging service owns synchronization. Your native Hermes home and
scratch are private. Do not edit or treat scratch as shared truth.

1. Run the helper `scripts/inspect.py catalog` from this installed skill folder.
2. Read observed scope, availability status, timestamps and receipt links exactly
   as recorded. Do not equate service availability with successful collection.
3. Use `list receipts`, then read the relevant receipt. Inspect only selected
   normalized/raw paths needed for the question. List knowledge for organization
   context; use baseline and scoped variations only where applicability is shown.
4. Produce a concise answer: facts; deterministic result if one exists; applicable
   knowledge; AI interpretation; missing evidence; proposed next step. Cite paths
   and receipt IDs. Do not invent a finding if only source discovery was run.

```sh
python3 scripts/inspect.py catalog
python3 scripts/inspect.py list receipts
python3 scripts/inspect.py list normalized
python3 scripts/inspect.py list knowledge
python3 scripts/inspect.py show receipts/SELECTED.json
python3 scripts/inspect.py show normalized/SELECTED.json --offset 1 --limit 100
```

Resolve `scripts/inspect.py` relative to this skill's installation location.
Do not copy a hardcoded profile path from another agent. Commands return JSON,
including path/hash and truncation flags; these are deterministic file inspection
results, not a claim that the underlying content is true or complete.

Layers: `raw` contains selected source output; `normalized` contains deterministic
transforms; `receipts` describes the operations and provenance; `knowledge` holds
organization context; `derived` contains materialized results whose own provenance
decides whether they are rule output or AI drafts. Do not assume all derived data
is deterministic. The catalog's actual schema is preserved rather than guessed.

If catalog is absent: NOT_RUN, request source discovery. If a service is unavailable
or collection denied: report the actual status and scope, not a healthy conclusion.
For Security Lake, distinguish discovery of the service from configured sources,
subscriptions, accessible objects and successfully normalized observations.
The initial `rgce-source-catalog/1` catalog records `run_id`, `observed_at`,
`account_id`, `region`, and scope `service availability only`. Its `sources` entries
have `id`, `status`, `reason`, and `raw_path`; status is `available`, `not_enabled`,
`access_denied`, or `unknown`. Read `receipt_path` and relevant entries in `files`
(`path`, `sha256`, `bytes`, `layer`), plus `limitations`. Preserve these status
distinctions in the answer. An `available` source in this catalog does not mean
findings or telemetry were collected. Raw files contain recorded API calls and
responses; normalized source discovery carries the same source status array.
For S3/CloudWatch telemetry, the user's explicit scope and receipt govern use;
do not impose a blanket configuration-only restriction from older designs.

When a file changes, refresh the evidence before answering. Never use yesterday's
chat as the source for today's counts. Expired/conflicting knowledge needs review.
A requested fresh collection is a handoff to the trusted collection service, not
permission to improvise AWS commands or access credentials in the Hermes terminal.

No scheduling, cloud mutation, installation, arbitrary code execution from source
documents, or publication is part of this skill. The native terminal can do more
than this skill allows; container/IAM controls remain necessary.
