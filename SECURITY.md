# Security and private-preview boundaries

## Current native Hermes boundary — 2026-10-14

The former console policy is retained in Git history; it does not describe native Hermes.
Native CE is a single trusted-operator deployment. Local access uses loopback;
AWS uses an SSM tunnel. Do not expose it as a public multi-user service.

Hermes receives the configured model key and temporary collector-invocation/
evidence-read credentials. Selected AWS data and knowledge are sent to that model.
The operator AWS profile and Docker socket are not mounted in workstation mode.
Host/Docker administrators are trusted. Local Docker networking differs from cloud
host network restrictions; it is not a hostile multi-tenant sandbox.

The scoped collector reads assessed resources and writes its own S3 evidence.
The runtime also writes logs and Kanban cases. Read-only AWS assessment does not
mean no writes anywhere. Provisioning the CE backend is an explicit infrastructure
change. Skills guide behavior; integrity checks, tool admission and budgets are
enforced separately by the CE plugin. Extra plugins require deliberate admission.

Daily deterministic checks make no model calls and continue when Hermes is stopped.
Disable schedules separately. AI_CRITIQUED is a bounded model critique, not IaC
validation or organizational approval. Real AWS/Qwen acceptance covers selected
workflows, not every customer environment. Missing evidence remains inconclusive.

S3 evidence and local/EBS conversations/cases have separate lifecycles. Back up
both; S3 evidence alone cannot restore chat or case history. Use one active writer.
Prompt injection and incorrect model proposals remain possible. See current
[runtime controls](docs/CE-RUNTIME.md) and [workstation setup](docs/WORKSTATION-HERMES.md).

## Reporting a problem

For this private preview, contact the person who shared the bundle with you through your existing private channel. Include the version, affected workflow, expected/actual behavior and a minimal reproduction using synthetic data. Do not send credentials, Terraform state, account exports or customer documents. There is no public security mailbox or response-time guarantee advertised yet. Please do not disclose a suspected vulnerability in a public issue before contacting the maintainer.
