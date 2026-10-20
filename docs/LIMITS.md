# Current scope and limits

## Your responsibility

RemediGenius CE is provided as-is under the Apache-2.0 license, without warranty
or assurance of any kind. You run it at your own risk. You choose and configure
your model provider, AWS accounts, IAM, regions, storage and schedules, and you
are responsible for what data reaches your provider, for any change you make to
your cloud, and for the AWS and model charges you incur.

## Supported scope

RemediGenius CE is a public, single-operator release. The validated baseline is AWS us-east-1
with DeepSeek v4.1 Flash. Other models/regions are configurable, not yet qualified.

- Collection is bounded by configured accounts, regions, operations and IAM.
  The setup guides configure one account. Extra target/role support exists in
  the executor, but multi-account onboarding is not wired into these launchers.
- Hermes prepares fixes; it does not apply customer-cloud changes. Generated
  CLI/Terraform/CloudFormation needs operator validation.
- Daily checks collect configured evidence without model calls. They do not
  automatically investigate every change or resolve cases.
- Selected knowledge requires operator intake/publication/activation. No live
  Confluence sync or automatic organization-wide ingestion is shipped.
- Native Kanban is manual. Conversations and cases use the retained Docker/EBS
  volume. Private S3 state checkpoints can restore them to an empty runtime;
  evidence receipts alone cannot. Changes since the last successful checkpoint
  can be lost. See [recovery](../deploy/aws-single/README.md).
- Model critique is bounded and can miss errors. Source evidence remains
  independently inspectable. A model label is not certification.
- No Security Lake analytics, public production MCP/API/A2A service, multi-user or multi-tenant operation or autonomous board workers is shipped.
- Model requests send selected evidence and knowledge to your configured provider.
  Self-hosting compute does not make inference local. See [models](MODELS.md).
- No RemediGenius CE adoption telemetry is collected. Feedback is voluntary. Upstream runtimes
  and providers have their own settings and data policies.
  Hermes may show **Help improve Hermes? Send to Nous**. This is an upstream
  opt-in prompt, not RemediGenius CE telemetry. Choose **No** or **Skip** if you do not want
  to send it. Do not include AWS evidence, organization knowledge or credentials
  in an optional feedback submission.
  New RemediGenius CE profile setup declines this upstream offer by default. An explicit
  existing operator opt-in is preserved during an upgrade.

See [AWS coverage](AWS-CAPABILITIES.md), [acceptance](RELEASE-VALIDATION.md)
and [security](../SECURITY.md). Legacy console and prototype deployments are archived outside RemediGenius CE.


### Collection limits

The reader enforces numeric page budgets independently of the model.
An omitted page budget collects one page across the runtime and deterministic
collector. Explicit multi-page requests remain supported within the
configured ceiling. Service parameters such as MaxResults control page size,
not the number of pages. Scheduled checks retain their explicit configured budgets.

The runtime displays actual scope, pages and completeness from collection results
above the model's interpretation. PARTIAL means the collected sample is incomplete;
it is not a healthy result or an exhaustive assessment. These bounds fix the
previous silent three-page default; they do not guarantee the model interprets
every natural-language instruction correctly.

### Generated artifact checks

Current source supports isolated Linux Terraform/AWS CLI/CloudFormation tools
with one pinned toolchain and up to three attempts per format. A tool PASS applies
to the identified artifact and the specific syntax/schema checks, not to resource
existence, security impact, rollback, permissions or model narrative. No plan/apply
is executed. Unsupported versions/modules are explicit gaps. See
[validation details](REMEDIATION-VALIDATION.md).
