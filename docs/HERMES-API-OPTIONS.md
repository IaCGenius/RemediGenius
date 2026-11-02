# Serving RemediGenius through native Hermes interfaces

Reviewed 2026-11-02 against the running CE Hermes 0.21.7 source and official documentation.
No endpoint was enabled or exposed during this review.

## HTTP: the recommended no-custom-code agent interface

The running image contains `gateway/platforms/api_server.py` with `/v1/chat/completions`, `/v1/responses`,
`/v1/runs`, `/v1/models`, `/v1/capabilities`, and run approval/status endpoints. A client sends a question;
the agent uses its profile's skills/tools and returns the answer. This is the appropriate built-in path for
another application to ask RemediGenius to investigate or explain evidence.

Setup uses `API_SERVER_ENABLED=true`, a strong `API_SERVER_KEY` supplied through the secret mechanism,
and the Hermes gateway. The documented default listener is loopback port 8642. Use the `remedigenius`
profile and an explicit restricted `platform_toolsets.api_server` entry; do not assume CLI restrictions
cover another platform. Start behind the existing private tunnel and verify authentication rejection,
profile selection, allowed tools and approval behavior before wider access.

The key permits agent work and access to the installation's data. CE remains single-operator and
single-organization; enabling this API does not provide multi-tenant isolation. The standard CE deployment
does not publish this port. Exposure is a separate decision, not required for this MCP release.

## MCP: conversation bridge, not an automatic CE tool export

Current Hermes offers the official `mcp-serve` plugin: `hermes plugins install mcp-serve`, then
`hermes -p <profile> mcp-serve`. It serves over stdio. The catalog requires Hermes >=0.22.0, newer than
CE's pinned 0.21.7. The installed image's `hermes mcp serve --help` exposes `--accept-hooks`
and verbosity, but no `--tools` option. Do not apply newer plugin instructions to that pin.

Its documented surface lists/reads conversations, polls events, sends through connected messaging channels
and handles approvals. Optional `--tools` exposes a fixed allowlist of Hermes capabilities. That list does
not contain `rg_triage` or `rg_analytics`; it is not a universal exporter of installed plugin tools, nor an
arbitrary "ask the RemediGenius agent" MCP endpoint.

Use native HTTP for full agent requests without custom code. Use native MCP for its supported bridge/tools.
Direct CE tool export needs an upstream-supported export feature or an adapter; do not promise it merely
because Hermes can act as an MCP server. No Hermes version upgrade is included in this proposal.

References:
- [API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
- [Official MCP Serve](https://hermes-agent.nousresearch.com/docs/plugins/mcp-serve)
- [Programmatic integration](https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration)
