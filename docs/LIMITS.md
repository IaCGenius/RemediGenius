# Current scope and limits

CE is a public, single-operator release. The validated baseline is AWS us-east-1
with Qwen 3.8 Max. Other models/regions are configurable, not yet qualified.
Azure and GCP are future direction, with no delivery date promised.

- Collection is bounded by configured accounts, regions, operations and IAM.
  Explicit additional account targets exist; automatic organization enrollment
  does not. CE is not artificially restricted to one account.
- Hermes prepares fixes; it does not apply customer-cloud changes. Generated
  CLI/Terraform/CloudFormation needs operator validation.
- Daily checks collect configured evidence without model calls. They do not
  automatically investigate every change or resolve cases.
- Selected knowledge requires operator intake/publication/activation. No live
  Confluence sync or automatic organization-wide ingestion is shipped.
- Native Kanban is manual. Conversations/cases need the retained Docker/EBS
  volume; S3 receipts alone cannot restore them.
- Model critique is bounded and can miss errors. Source evidence remains
  independently inspectable. A model label is not certification.
- No Security Lake analytics, public production MCP/API/A2A service, hosted
  multi-tenancy or autonomous board workers is shipped.
- Model requests send selected evidence and knowledge to your configured provider.
  Self-hosting compute does not make inference local. See [models](MODELS.md).
- No CE adoption telemetry is collected. Feedback is voluntary. Upstream runtimes
  and providers have their own settings and data policies.

See [AWS coverage](AWS-MVP-CAPABILITIES.md), [acceptance](MVP-ACCEPTANCE.md)
and [security](../SECURITY.md). Legacy console and prototype deployments are archived outside CE.
