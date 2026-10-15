---
name: aws-serverless
description: "AWS Lambda design knowledge for kiosk functions: memory and timeout sizing, cold starts, concurrency, layers, error handling, idempotency, production gotchas and exact-error troubleshooting. Use while designing or debugging a kiosk function."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  upstream: aws/agent-toolkit-for-aws@2cb0fa1c2e668e1bb075028800b6b27efb95779e plugins/aws-core/skills/aws-serverless
---

# aws-serverless (adapted for the kiosk)

Use AWS's own Lambda guidance while you **design** a kiosk function. The kiosk deploys for you, so read
upstream for *what to build*, never for *how to deploy*.

## Read (in `references/upstream/references/`)
| Need | File |
|---|---|
| Memory/timeout sizing, cold starts, layers, `/tmp`, payload limits | `lambda.md` |
| Concurrency, throttling (your function has reserved concurrency = manifest `concurrency`) | `concurrency.md` |
| Fan-out and orchestration ideas (the kiosk's run machine is a Step Functions Map) | `orchestration.md`, `architecture.md` |
| Production readiness: idempotency, retries, structured logs, anti-patterns | `production.md` |
| An exact error string you see in `kiosk logs` | `troubleshooting.md` |

## Does not apply here
- SAM, CDK, CloudFormation, `aws lambda create-function`/`update-function-code`, console steps: **the gate
  deploys**. Use `kiosk submit`.
- API Gateway, function URLs, event source mappings, VPC config, SnapStart, provisioned concurrency,
  Lambda Managed Instances, microVMs, durable functions: not offered by this kiosk. If a task needs one,
  say so to the owner instead of working around it.
- Powertools: not in the runtime layer; use `ctx.log` (structured, redacted) instead.
- Runtime and architecture are fixed by the kiosk: Python 3.13, x86_64.

Upstream's own text: `references/upstream/UPSTREAM-SKILL.md` (background only).
