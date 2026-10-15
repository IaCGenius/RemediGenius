# Native Hermes CE sketch

This pack makes Hermes the interactive agent. It contains one installable native
profile distribution, not another agent loop or chat server. Use Hermes Desktop
and its remote gateway, or the native CLI. No schedule is installed or enabled.

* **desk** explains coverage, investigates evidence and drafts proposals with receipts.

It uses the readable `shared-evidence` skill and deterministic inspection
helper. The helper reads files only; it never calls AWS, a model, or a database.
The skill does not collect or normalize data with an LLM.

## Install

Stage a private copy of the distribution and substitute `__MODEL_NAME__` and
`__MODEL_BASE_URL__` in config.yaml. Supply `MODEL_API_KEY` through the native
Hermes environment/secret mechanism, never in these files. The template uses
Hermes's native OpenAI-compatible provider; users can configure another native
Hermes provider instead. Endpoint compatibility still requires a real test.

```sh
hermes profile install /opt/ce-profiles/desk --name ce-desk --yes
hermes -p ce-desk chat
```

The distribution format matches the existing deployed v2 profile packs. Native
profile commands and Desktop connection are reused; this pack itself has not
established a cloud connection or run a model acceptance test.

For an isolated per-role runtime, install only that role's distribution in its
private Hermes home. Mount the staged evidence tree at `/opt/data/shared:ro` and
give the role a separate writable `/opt/data/work`. Never mount another role's
private home or credentials. Do not inject AWS credentials or expose IMDS.
The terminal is a native general-purpose tool: skill text is not a sandbox.
The host/container policy enforces read-only shared data and cloud authority.

Set `HERMES_TUI_TOOLSETS=file,skills,terminal,clarify` on the native gateway.
The inspected upstream Desktop gateway otherwise lets automatic coding posture
override configured CLI toolsets in a code workspace. The explicit pin avoids
that expansion. Use a clean dedicated Hermes home with no default MCP servers,
plugins or hooks. The pack requests only those same CLI toolsets.

Connect Desktop using the deployment's SSM tunnel, gateway URL and native login.
Pick the installed CE profile and open a new session after profile updates.
Do not continue an old conversation when evaluating new instructions.

## Shared durable data

```text
/opt/data/shared/
  catalog.json
  raw/
  normalized/
  receipts/
  knowledge/
  derived/
```

S3 is authoritative; a separate deterministic service stages this read-only
snapshot. This pack does not implement synchronization. Catalog and receipts
must carry observation times, scope, collection status and source references.
The helper preserves their contents without inventing a schema or interpreting
availability as successful collection. Missing files yield NOT_RUN or ERROR.
Catalog availability is not a security assessment or verification of coverage.

Native Hermes sessions and scratch live outside shared evidence. Their backup
and recovery are deployment responsibilities; this pack does not claim S3-native
session durability. Drafts in scratch are not published knowledge or results.
Publishing must be a separate deterministic, consented operation with a receipt.

## Orchestration actually provided

The native CLI supports `hermes -p ce-desk chat`; Desktop selects `ce-desk`.
One conversation can move from a summary to investigation and a remediation
proposal. No profile switching or automatic delegation is required. The former
analyst source is retained under `docs/archived/native-analyst-profile`; bootstrap
archives an existing analyst home outside the active profiles directory without
deleting its history. Open a new chat to load the combined instructions.

Try: “Which sources are available, when were they observed, and what is missing?”
Then: “Is Security Lake available, and do we have any actual collected records?”
Then: “Investigate this normalized record, apply relevant scoped knowledge, and
draft verification and rollback steps without changing AWS.”

Expected answers cite the current catalog, selected evidence and receipts; say
not checked when unsupported; distinguish deterministic facts, reviewed knowledge
and AI interpretation. A successful answer does not manufacture a collection.

## Provenance

Structure and operating pattern adapted from the existing RemediGenius
desk/results and analyst distributions. The new helper contains no organization
facts or credentials. The earlier proprietary skill text/code was not copied;
only the files-first inspection pattern was reused. Upstream Hermes is unmodified.

Run `python profiles/native-sketch/tests/test_inspect.py` for deterministic helper
checks. Synthetic fixtures are test-only and are never shipped as live evidence.
