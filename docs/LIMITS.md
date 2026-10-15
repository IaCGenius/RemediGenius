# Current scope and limits

## Your responsibility

RemediGenius CE is provided as-is under the Apache-2.0 license, without warranty
or assurance of any kind. You run it at your own risk. You choose and configure
your model provider, AWS accounts, IAM, regions, storage and schedules, and you
are responsible for what data reaches your provider, for any change you make to
your cloud, and for the AWS and model charges you incur.

## Supported scope

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
- No Security Lake analytics, public production MCP/API/A2A service, multi-user or multi-tenant operation or autonomous board workers is shipped.
- Model requests send selected evidence and knowledge to your configured provider.
  Self-hosting compute does not make inference local. See [models](MODELS.md).
- No CE adoption telemetry is collected. Feedback is voluntary. Upstream runtimes
  and providers have their own settings and data policies.

See [AWS coverage](AWS-CAPABILITIES.md), [acceptance](RELEASE-VALIDATION.md)
and [security](../SECURITY.md). Legacy console and prototype deployments are archived outside CE.


### Collection limits

The reader enforces numeric page budgets independently of the model. In v0.1.1,
an omitted page budget collects one page, consistently across the runtime, CLI
helper and Lambda. Explicit multi-page requests remain supported within the
configured ceiling. Service parameters such as MaxResults control page size,
not the number of pages. Scheduled checks retain their explicit configured budgets.

The runtime displays actual scope, pages and completeness from collection results
above the model's interpretation. PARTIAL means the collected sample is incomplete;
it is not a healthy result or an exhaustive assessment. These bounds fix the
previous silent three-page default; they do not guarantee the model interprets
every natural-language instruction correctly.
