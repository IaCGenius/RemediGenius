# What CE adds to Hermes

Hermes provides conversation, model routing, skills, sessions and manual Kanban.
CE provides readable AWS investigation procedures; a bounded execution/review
plugin; deterministic AWS collection and S3 receipts; selected organizational
knowledge; proposal guidance and fresh reassessment.

| Extend | Current contract |
|---|---|
| Knowledge | Import files, select a view and mount/publish it. Scope and provenance guide interpretation; knowledge does not grant permissions. |
| Model | Operator chooses provider/credentials. DeepSeek v4.1 Flash is the current test baseline. |
| AWS accounts | Setup configures one account. Extra executor targets are not a supported launcher onboarding flow. |
| Operations | Existing generic executor and SDK schema discovery; new admitted operations require permission/manifest review. |
| Skills/plugins | Reuse Hermes capabilities, with deliberate admission and integrity checks for the CE package. No automatic trust in newly installed code. |
| Other agent integrations | Readable skills and exported knowledge are reusable. A public native MCP/API/A2A service is not shipped. |

The old custom console, MCP server and builder are archived outside CE. They are
not alternative supported interfaces. CE has one trusted operator;
managed multi-tenant hosting is a separate product, not a switch in this release.

See [runtime controls](CE-RUNTIME.md), [knowledge onboarding](NATIVE-KNOWLEDGE-QUICKSTART.md),
[models](MODELS.md), and [limits](LIMITS.md). Source and third-party attribution are
in [NOTICE](../NOTICE). Self-hosted compute does not mean offline model inference.
