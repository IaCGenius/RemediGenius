# What RemediGenius CE adds to Hermes

Hermes supplies the agent runtime: conversations, model routing, skills, sessions
and manual Kanban. RemediGenius Community Edition adds readable AWS investigation
procedures, bounded execution and review, deterministic collection with S3
receipts, selected organizational knowledge, and remediation proposals with
fresh reassessment.

| Extend | Current contract |
|---|---|
| Knowledge | Import files, select a view and mount/publish it. Scope and provenance guide interpretation; knowledge does not grant permissions. |
| Model | Operator chooses provider/credentials. DeepSeek v4.1 Flash is the current test baseline. |
| AWS accounts | Setup configures one account. Extra executor targets are not a supported launcher onboarding flow. |
| Operations | Existing generic executor and SDK schema discovery; new admitted operations require permission/manifest review. |
| Skills/plugins | Reuse Hermes capabilities, with deliberate admission and integrity checks for the RemediGenius CE package. No automatic trust in newly installed code. |
| Other agent integrations | Readable skills and exported knowledge are reusable. A public native MCP/API/A2A service is not shipped. |

The old custom console, MCP server and builder are archived outside RemediGenius CE. They are
not alternative supported interfaces. RemediGenius CE has one trusted operator;
managed multi-tenant hosting is a separate product, not a switch in this release.

See [runtime controls](CE-RUNTIME.md), [knowledge onboarding](NATIVE-KNOWLEDGE-QUICKSTART.md),
[models](MODELS.md), and [limits](LIMITS.md). Source and third-party attribution are
in [NOTICE](../NOTICE). Self-hosted compute does not mean offline model inference.
