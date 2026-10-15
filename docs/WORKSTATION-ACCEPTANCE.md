# Native workstation acceptance — 2026-10-14

This record covers native Hermes on Windows Docker Desktop with a separate real
AWS backend. It is not acceptance for every OS or the full 18-case UI pack.

| Check | Observed result |
|---|---|
| Terraform | Valid configuration; 19 resources created, none changed/deleted; subsequent plan reported no changes |
| Model/runtime | Official pinned Hermes image, CE profile v0.2.1, real configured Qwen3.8-max |
| Credentials | Operator credentials stayed outside Docker; temporary invoker identity was denied direct EC2 inventory access |
| Collection | Real Config read succeeded through Lambda; its receipt was retrieved using scoped S3 permissions |
| Schedule | Real deterministic invocation completed two checks successfully; daily AWS schedule enabled |
| Dashboard | Password login and authenticated CE Kanban endpoint returned HTTP 200 |
| Agent | Real Qwen turn collected Config evidence, cited scope/time/receipt, distinguished interpretation, and completed AI_CRITIQUED review |
| Replacement | Original conversation persisted with 11 messages and 5 tool calls after container replacement |
| Credential renewal | Explicit refresh succeeded after replacement |
| Backup | Quiesced volume archive restored into a fresh volume; original real Qwen session retained; recovered dashboard login, Kanban endpoint and CE integrity check passed |
| Regression | Existing runtime/scheduler suite: 28 passed outside the Windows sandbox |

Pinned image:
`nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b`

The Qwen evidence run was `4663d08bfc704c9aa5dcac92a8cf80b2`.
Private inputs, actual source results, model transcript and backup are retained in
`.rgce/workstation-acceptance/`; never publish that directory. The model was called
interactively. Scheduled collection did not call an LLM. No assessed AWS resource
was remediated and the existing cloud CE deployment was not modified.

## Corrections and limits

The first launcher readiness check expected a work directory the official image
does not create. It now waits for the native config and creates the work directory
as the Hermes user. The first sandboxed regression attempt failed on temporary
directory access; a second stalled. The same suite passed outside that sandbox.

The first backup restore rejected Hermes absolute symlinks. Docker also populated
a fresh volume from the image unless `volume-nocopy` was specified. The successful
restore used an empty volume, the backup created locally in this test, and trusted
archive extraction preserving native links. Do not use this procedure on archives
from unknown sources. Restored dashboard access and source integrity passed; no
additional model turn was run from the restored copy.

Native profile changes now require an explicit `--upgrade` when the packaged
source digest changes. Normal restarts retain customization. Local model/config
changes and new plugins still require operator review.

Not claimed by this run: full browser-driven acceptance, a forced 60-minute STS
expiry/SSO renewal test, unattended workstation restart, multi-account live reads,
Linux/macOS host acceptance or automatic cloud action execution. The workstation
requires AWS connectivity and Docker; it is not offline. Local chat/cases live in
the named volume, separate from S3 evidence.
