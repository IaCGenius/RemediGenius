# Troubleshooting

## Hermes-owned issues

For installation, provider/model setup, terminal/Docker and gateway problems, use
[Hermes FAQ & Troubleshooting](https://hermes-agent.nousresearch.com/docs/reference/faq#troubleshooting).
CE pins its Hermes image: do not independently update its runtime while diagnosing CE.

## CE operator actions

These codes are emitted by the CE runtime and linked from chat. Other argument
errors are for the agent to correct within its bounded attempts. A blocked read
is never evidence that a resource is healthy. Logs: retained profile
`logs/ce-runtime.jsonl`; avoid sharing credentials or raw organization data.

### CE-AUTH

Renew AWS login and restart the workstation launcher. On Spot, check the attached
instance profile and collector service; the SDK obtains temporary role credentials.

### CE-PROBE

Check the collector container/service, its Unix socket, configured target and AWS
permissions. On Spot use `systemctl status rgce-collector`; on Docker inspect the
collector logs. Follow [the identity boundary](IAM.md).

### CE-INTEGRITY

Restore the reviewed package or perform the documented explicit profile upgrade.

### CE-VALIDATOR

Start or restart CE with its validator; inspect validator container health.

### CE-TARGET

Select an alias returned by capabilities, or configure and deploy the target.

### CE-REGION

Use the configured us-east-1 target scope.

### CE-OPERATION

Choose a supported operation from capabilities; changing prompts does not grant access.

### CE-DENIED

Ask your AWS administrator to inspect the specific denied action and role/SCP; do not broaden access blindly.

### CE-KNOWLEDGE

Re-import the original document and republish the selected knowledge view.

### CE-BUDGET

Review the partial result, narrow the task and start a new turn; no automatic retries remain.

### CE-GATE

Restart CE from the reviewed package and inspect the local runtime log.

## Startup model probe

The workstation launcher makes one small tool-calling request before
opening the dashboard when a model key is configured. Spot does not run this
probe: configure the model in Hermes and send a small request to verify access. It uses the retained ce-desk model configuration, or the
seed on first installation. No AWS data or knowledge is sent. No retry loop.

| Code | Action |
|---|---|
| CE-MODEL-AUTH | Check the key, endpoint and provider account permissions (401/403). |
| CE-MODEL-ENDPOINT | Check model identifier and API base URL (404). |
| CE-MODEL-QUOTA | Check rate/quota limits and provider plan terms (429); the status alone cannot identify a plan restriction. |
| CE-MODEL-CONTEXT | Choose/configure 64k+ context; a context error can also mean the configured request exceeds its limit. |
| CE-MODEL-TOOLS | Configure a reasoning model with reliable tool calling. |
| CE-MODEL-PROVIDER | Use the documented custom OpenAI-compatible CE startup configuration. |
| CE-MODEL-CONNECTION | Check network, endpoint and TLS connectivity; no raw response/key is printed. |

A small successful request checks reachability and tool calling, not the full
context capacity or future quota. See [model configuration](MODELS.md).

## WSL2

Use Ubuntu 24.04 LTS with Docker Desktop **Settings → Resources → WSL Integration**
enabled for that distribution. `docker info` must work in Bash before launching CE.
Install the Linux AWS Session Manager plugin for the Bash tunnel. Open the local
URL in the Windows browser; WSL NAT normally uses localhost forwarding, whereas
mirrored networking shares localhost directly. Do not expose the gateway on all
interfaces to work around a local forwarding problem.
