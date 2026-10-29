# What leaves your environment — RemediGenius Community Edition

RemediGenius Community Edition (RemediGenius-CE) is a skill pack, a read-only desk and a dashboard tab on top of
[Hermes](https://github.com/NousResearch/hermes-agent), using the **model provider you configure**. It runs no model of
its own. Self-hosting the application does not make inference local: that depends on the endpoint you choose.

| Data | Goes to | When |
| --- | --- | --- |
| Findings, resource identifiers (account ids, ARNs, names, IPs), IaC excerpts, knowledge concepts, chat | your model provider (`model_base_url`) | every conversation turn that uses them |
| Read-only API calls | AWS, from your account's read role | scans, `doctor`, the agent's live checks |
| Every collected AWS response page (findings, configuration, alarms) | your S3 bucket under `raw/` (Spot) or the durable folder (workstation) | during every scan, before a fact derived from it is committed |
| Findings and desk facts (OCSF findings, scans, coverage, decisions, fix and GitHub events) | Apache Iceberg tables in the same bucket or local warehouse | one commit per completed scan, and one per human decision or GitHub operation |
| Conversations, decisions, knowledge, settings, model key | the Hermes home checkpoint in your S3 bucket (Spot) or a local folder (workstation) | every 2 minutes |
| Pull request lookups (optional, only if you configure a token) | GitHub | fix tracking |
| Repository reads and pull requests (optional, only if you connect GitHub: [docs/GITHUB.md](GITHUB.md)) | GitHub (`api.github.com`, from the desk, never the agent) | repository files of the connected repo, the proposed change and a sanitized PR description |

**Never leaves the desk:** AWS credentials (the agent has none), secret values, decrypted data, CloudWatch log
events. The desk's guard refuses those reads even with administrator credentials.

**Raw evidence in durable storage.** Each collected response page is written once to `raw/`, gzip JSON keyed by
the SHA-256 of its stored bytes. The object contains account configuration and finding details (resource names,
ARNs, IPs, policy text) but is never sent to your model provider. The agent cannot read the raw store: it asks
the desk to resolve a finding and cites what it returns. The bucket is private with public access blocked and
versioning on; SSE-S3 is the default and SSE-KMS an option. Retention and lifecycle are operator settings
(`storage` in `triage.yaml` and the Terraform stack). Raw objects contain sensitive configuration, so give the
bucket the same care as the checkpoints. See [STORAGE.md](STORAGE.md).

**When storage is unavailable.** Collection continues into a bounded local buffer (256 MB by default) and then
pauses with visible status rather than dropping evidence. A decision is acknowledged only after its fact is
committed; otherwise the desk says it is saved locally and not yet durable.

**Local inference:** any OpenAI-compatible endpoint works, for example Ollama or vLLM on your own hardware
(`model_base_url: http://<host>:11434/v1`). Answers from smaller local models are less reliable; validate with the
offline evaluation before relying on them. `rgtriage doctor` says whether the configured endpoint is local or a
third-party provider.

**Scope:** one named operator, one organization per installation. It is not multi-user or multi-tenant: an MSP runs
one installation per customer. The installer shows this notice once and records the acknowledgement; the dashboard
Knowledge tab shows it until you dismiss it.

```
 you ──chat──▶ Hermes (dashboard) ──prompt + tool results──▶ your model provider
                  │
                  └─ rg_triage tool ─▶ desk (read-only) ─▶ AWS APIs (read role)
                                          └─▶ S3 bucket / local folder (raw evidence, Iceberg, checkpoints)
```
