# Hermes-powered CE: cloud-first completion plan

The integrated Hermes experience is part of Community Edition. The rc9 workspace-only preview is not completion of that experience. This work deploys a separate CE Spot environment; it does not update the local preview or the parked existing product engine.

## Release outcome

A practitioner opens the private CE workspace through SSM, sees the configured Hermes version and model, selects an assessment and contextual evidence, reviews the disclosure scope, and starts an investigation. Progress and the final answer appear in the workspace. Answers cite selected records and remain visibly AI interpretation; deterministic findings and reviewed guidance retain their original provenance.

## Implementation sequence

1. Reuse pinned upstream Hermes AIAgent APIs, native provider configuration and existing investigation skill. Keep Hermes upgradeable independently of CE. No new inference SDK or mandatory MCP.
2. Add a bounded investigation controller: snapshot selected evidence and applicable knowledge, require explicit model-disclosure consent, persist a request receipt, stream safe progress, allow cancellation, validate citations, and persist a reviewable result.
3. Run Hermes in a disposable, unprivileged container for each investigation. A trusted host broker launches it; neither the console nor the agent receives a Docker socket. The agent has selected read-only files, model credentials, no AWS credentials and no metadata/console network access.
4. Deploy dedicated CE Spot compute through a separate Terraform root, with SSM-only access, pinned application/agent images, narrow storage IAM, and a model secret fetched into host tmpfs. Keep the existing local and v2 deployments unchanged.
5. Test actual browser-to-cloud-to-Hermes-to-S3 flow using only the previously approved selected fixture export. Verify cancellation/failure, invalid citations, read scope, metadata denial, and recovery after compute replacement. Do not call mocked responses live acceptance.
6. Package source, deployment instructions, readable skills/configuration, troubleshooting, honest release limits and sanitized acceptance receipts. Mark ready only after the integrated path succeeds.

## Persistence and interruption

CE remains the single durable writer. Requests and completed results are immutable S3 records; transient job files and model sessions are disposable. A recovered request without a terminal result is interrupted, never silently replayed to a model. The operator starts a fresh consented investigation. One active workspace writer only.

## Model and review boundaries

Provider setup uses Hermes capabilities. CE displays non-secret provider/model identity; secrets never enter exports, prompts, browser responses or Terraform state. Initial live tests use the already approved synthetic fixture and configured provider. Broader account evidence requires explicit selection and consent. A successful model call is not a correct security conclusion; citation checks and human review remain separate.

Pi may review the four previously approved storage/document/knowledge source files. Broader source disclosure is not inferred from that narrow prior approval. Internal subagents can inspect implementation without sending it to another configured model provider.
