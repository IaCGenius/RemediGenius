# Implemented CE architecture: start here

> This diagram records the rc10 implementation, which the owner subsequently rejected as the CE product architecture. It is preserved for understanding and reuse. See [the corrected Hermes-first direction](https://github.com/IaCGenius/RemediGenius/blob/aab2f8a7c74a87fc60684e1afc8ec983fd89fd5b/docs/HERMES-FIRST-REALIGNMENT.md).

Open [the interactive architecture diagram](ce-brain.html). This describes the cloud CE implementation at code checkpoint `b11e455`, not a future product design. The diagram simplifies supporting IAM, networking and secret delivery; these remain documented in [the cloud operations guide](../HERMES-CLOUD.md).

## Read the diagram in this order

1. **CE workspace:** the application you see in your browser. It owns evidence, deterministic rules, knowledge review and the selection of files for an investigation.
2. **S3 workspace:** durable storage outside the replaceable Spot host. Evidence is a recorded observation with source/time/coverage; knowledge is reviewed organisational context. Both are distinct from saved AI answers.
3. **CE skill files:** versioned, readable instructions maintained with CE. The investigation controller adds the investigation skill to the selected snapshot. The diagram shows a logical part of the console image, not a separate service or database.
4. **Host broker:** a small trusted process on the Spot host. It validates the queued snapshot and starts the pinned Hermes container. Temporary job files live in host memory-backed storage.
5. **Hermes agent:** a temporary agent engine. It receives the question, skill and selected evidence/knowledge. Its two tools read and search those files. It does not independently browse the whole S3 store or collect from your AWS account.
6. **Bailian LLM:** the externally hosted model currently called by Hermes. The model is not installed on the Spot host. DeepSeek configuration is an option, but no DeepSeek key or successful test has been supplied.
7. **Return path:** the model's answer returns through Hermes and the broker to the CE console. CE stores an unreviewed AI result in S3 and displays it. Return arrows are omitted from the overview to keep the main path readable; they are not a separate direct LLM-to-S3 connection.

**The shared brain is therefore a combination, not one component inside Hermes:** CE manages durable knowledge and evidence; skills guide the investigation; Hermes operates the agent loop; the external LLM performs model inference.

## How information arrives

Existing CE adapters can collect bounded AWS evidence through separately scoped read roles; file imports, document intake and reviewed notes also feed the workspace. The deployed cloud host's default IAM role only handles CE storage and its exact model secret: it does not grant whole-account collection. The live acceptance used an explicitly selected historical AWS acceptance-resource export. It was not a continuous production scan.

When a request starts, CE resolves applicable reviewed knowledge against the selected assessment and resource. Missing scope remains unknown; no environment value is invented. Raw documents and every organisational fact are not automatically included. Follow-ups explicitly include the previous AI answer as unreviewed context alongside a freshly prepared snapshot.

The host obtains the exact configured model key from Secrets Manager into temporary storage. Hermes receives the model key but no AWS credentials. The trusted console and broker share the host role; this is not IAM isolation from a compromised console. No remediation or arbitrary builder execution is enabled in this investigation path. The earlier v2 builder/kiosk work is separate.

## Where to inspect the implementation

| Responsibility | Source |
|---|---|
| Browser and APIs | `rgce/static/hermes.js`, `rgce/app.py` |
| Snapshot, consent and result receipts | `rgce/hermes_jobs.py`, `rgce/workspace.py` |
| Evidence / reviewed context storage | `rgce/store.py`, `rgce/object_storage.py` |
| Investigation skill | `rgce/static/remedigenius-investigate.SKILL.md` |
| Trusted worker launcher | `deploy/hermes/broker.py` |
| Native Hermes integration | `deploy/hermes/runner.py`, `deploy/hermes/Dockerfile` |
| Spot host, IAM, network and secret setup | `deploy/aws-hermes/` |

## Diagram verification

Archify architecture, showcase profile: all 9 deterministic artifact checks passed, zero composition errors or warnings. Automated browser containment passed at 1440×900, 1600×1000, 1920×1080 and 2048×1320. Light large-desktop and dark laptop screenshots were visually inspected: labels and routes are readable, with no overlapping components. The JSON specification, delivery hash receipt and browser evidence sit beside the HTML. No deployment was changed while producing this diagram.
