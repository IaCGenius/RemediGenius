# What leaves your environment — RemediGenius Community Edition

RemediGenius Community Edition (RemediGenius-CE) is a skill pack, a read-only desk and a dashboard tab on top of
[Hermes](https://github.com/NousResearch/hermes-agent), using the **model provider you configure**. It runs no model of
its own. Self-hosting the application does not make inference local: that depends on the endpoint you choose.

| Data | Goes to | When |
| --- | --- | --- |
| Findings, resource identifiers (account ids, ARNs, names, IPs), IaC excerpts, knowledge concepts, chat | your model provider (`model_base_url`) | every conversation turn that uses them |
| Read-only API calls | AWS, from your account's read role | scans, `doctor`, the agent's live checks |
| Conversations, decisions, knowledge, settings, model key | your S3 bucket (Spot) or a local folder (workstation) | checkpoints every 2 minutes |
| Pull request lookups (optional, only if you configure a token) | GitHub | fix tracking |

**Never leaves the desk:** AWS credentials (the agent has none), secret values, S3 object contents, decrypted data,
CloudWatch log events. The desk's guard refuses those reads even with administrator credentials.

**Local inference:** any OpenAI-compatible endpoint works, for example Ollama or vLLM on your own hardware
(`model_base_url: http://<host>:11434/v1`). Answers from smaller local models are less reliable; validate with the
offline evaluation before relying on them. `rgtriage doctor` says whether the configured endpoint is local or a
third-party provider.

**Optional Hermes WebUI (Spot):** a separate community project ([nesquena/hermes-webui](https://github.com/nesquena/hermes-webui),
MIT, pinned), not maintained by RemediGenius or Nous Research. It runs on the same instance, reachable only through the
SSM tunnel, and sends chat to the Hermes gateway on the private container network; it adds no other destination.

**Scope:** one named operator, one organization per installation. It is not multi-user or multi-tenant: an MSP runs
one installation per customer. The installer shows this notice once and records the acknowledgement; the dashboard
Knowledge tab shows it until you dismiss it.

```
 you ──chat──▶ Hermes (dashboard) ──prompt + tool results──▶ your model provider
                  │
                  └─ rg_triage tool ─▶ desk (read-only) ─▶ AWS APIs (read role)
                                          └─▶ S3 bucket / local folder (checkpoints)
```
