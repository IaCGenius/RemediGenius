# AWS-first CE: useful outcomes, feature scope and release assessment

Date: 2026-10-13. Assessment of the native Hermes CE deployment, not every
experimental component in the repository. Proposed features below are not claims
of implementation. No cloud changes were made for this assessment.

## Implementation update - 2026-10-13

The owner decides release scope. The assessment below predates the live SDK execution work. See [AWS read execution](AWS-READ-EXECUTION.md) for the implemented multi-account read capability, native Hermes CloudTrail acceptance, immediate S3 evidence access, selected knowledge and deterministic comparison. Do not use the older GAP/REUSE rows as the current implementation inventory. The authorized native Qwen test exposed workflow and interpretation defects; see HERMES-SKILLS-AND-EXECUTION-CONTRACT.md for the skills review. No full-pass claim is made.

## Product promise

Connect the AWS security tooling and telemetry you already have, across selected
accounts and regions. Ask what matters, investigate the evidence, apply your
business context, receive an actionable proposal, and reassess after your team
makes the change. Hermes is the investigator; deterministic tools collect and
transform data; object storage retains evidence and knowledge.

Target: medium organizations with a lean security team and existing AWS tooling.
A company need not purchase another scanner or turn on every AWS security service.
Support both a standalone account and a security account managing many accounts.
The value is a shorter path from existing AWS signals to a supported decision.

CSPM means cloud security posture management. SecOps adds investigation of actual
activity. Vulnerability, identity, data protection and coverage management provide
other useful views of the same AWS environment. Do not claim full CNAPP, SIEM,
attack-path proof or automated incident containment in v0.1.

## Original assessment (superseded for live read capabilities)

**Not ready for an AWS customer preview under this promise.** Ready to demonstrate
engineering progress with a maintainer present. Successful chat, honest missing-
data answers and Spot recovery are necessary infrastructure checks, not evidence
that a customer can investigate their own AWS environment.

The previous supervised-preview assessment used too weak a product bar. An AWS
preview needs actual connection, collection, investigation and repeat use without
maintainer intervention. A fixed sample cannot establish account-wide posture or
identify the highest-risk issues across an organization.

## Feature list, ordered by customer value

Statuses: LIVE = demonstrated native cloud path; PARTIAL = limited live behavior;
REUSE = code exists but is not connected/tested through native Hermes for this use;
GAP = no demonstrated native end-to-end capability. P0 is the useful-preview bar;
P1 extends AWS coverage without being mandatory on every customer's first day.

| Priority / domain | User question or outcome | AWS inputs and method | Current native CE status | Required result |
|---|---|---|---|---|
| P0 / onboarding | What can you access in my AWS environment? | STS identity, explicit accounts/regions, assumed roles; Organizations optional | PARTIAL: own test account/region; REUSE: role-based CLI collectors | Permission-tested account/region/source matrix, exact gaps and scoped onboarding instructions |
| P0 / multi-account | Which production accounts have the biggest problems? | Existing Security Hub administrator/aggregation; selected account roles for drill-down | GAP; live sample explicitly filters to deployment account | Findings retain original account/region; partial failures never disappear from totals |
| P0 / coverage | Which security tools/data are actually protecting this scope? | Security Hub, GuardDuty, Inspector, Config, trails; available central coverage records | PARTIAL: six service-availability probes | Distinguish service enabled, resource coverage, recording freshness, readable records and unknowns |
| P0 / CSPM triage | What should we fix first, and why? | Security Hub CSPM controls/findings, Config/direct configuration, business context | PARTIAL: at most 20 latest-updated ACTIVE Hub findings | Bounded paginated query, stable grouping, source severities, evidence-backed proposed priority and sampling notice |
| P0 / SecOps | Who changed EC2/security groups/IAM over five days? | CloudTrail Event history first; existing trail/lake routes when required | REUSE: CLI LookupEvents; limited to 1–24 hours; no chat collection | Scope/time/actor/resource-filtered timeline, deduplicated event IDs, failed versus successful calls, receipt |
| P0 / incident investigation | What supports or weakens this GuardDuty alert? | GuardDuty finding from Hub or native API plus related CloudTrail activity | PARTIAL: some Hub sample findings; no automated enrichment | Explain alert, affected identity/resource, selected supporting events and next checks; do not assert compromise without support |
| P0 / asset context | Is this finding about a live, public or important resource? | Config aggregator where present; selected EC2/VPC/S3 describe APIs and tags | REUSE: security-group/ENI collector | Exact current configuration and timestamp; distinguish permissive rule from verified network reachability |
| P0 / shared knowledge | This policy has a payments-dev exception; does it apply? | Operator documents, selected collections, explicit account/resource/time scope | REUSE: local knowledge importer; GAP: cloud view integration | Preserve baseline and applicable exception, cite both; conflicting/expired context remains visible |
| P0 / action proposal | What precisely should my team change? | Collected facts, native finding guidance, selected knowledge | PARTIAL: model draft instructions | Resource/account, reason, proposed CLI/IaC or manual steps, impact, verification and rollback; no claim commands were tested unless they were |
| P0 / reassessment | We fixed it; did it actually improve? | Rerun same scoped collection; compare deterministic snapshots | GAP | Before/after receipts, fixed/persistent/new/unknown; avoid assuming delayed native findings imply a failed fix |
| P0 / communication | Give the analyst and CISO the right level of detail | Same receipts and analysis, different presentation | PARTIAL: conversational summaries | Analyst timeline plus concise priorities/owners if known, coverage caveats and next decisions; no invented financial risk score |
| P0 / operating trust | What did you do, retry, send to a model and spend? | Native session/tool history, collection receipts and provider usage where available | PARTIAL: explain/review skill and metadata index, bounded model settings | Traceable scope/operations, recovered failures, data-sharing scope and measured usage; missing cost stays unknown |
| P1 / vulnerability | Which vulnerable workloads deserve attention first? | Existing Inspector EC2/ECR/Lambda findings and coverage, Hub integrations | GAP beyond whatever appears in Hub sample | CVE/package/resource context, vendor signals, available patch and uncertainty; do not invent exploitability |
| P1 / identity | Which external or unused permissions should we investigate? | Existing IAM Access Analyzer findings, selected policy context and CloudTrail | GAP | Explain trust boundary and findings; propose least-privilege review, not guaranteed effective-access proof |
| P1 / data protection | Which sensitive stores have access concerns? | Existing Macie findings, S3 policy/public-access/encryption metadata | GAP | Join classification and exposure metadata; do not read sensitive object bodies merely to investigate policy |
| P1 / telemetry | Use our existing centralized logs | CloudWatch selected groups/cross-account links, S3 trail prefixes/Athena, Security Lake subscriber | REUSE: exact S3 object and FilterLogEvents; GAP: central query integration | Reusable bounded query path, source schema, provenance, time partitions, scan/call budgets and cancellation |
| P1 / network and application | What explains suspicious ingress or blocked requests? | Existing VPC Flow, WAF, Route 53 Resolver and load-balancer logs; Firewall Manager findings | GAP | Source-specific investigation using the same log-query capability; no new detector per question |
| P1 / workflow | Tell me when material evidence changes | Opt-in EventBridge/SQS or bounded schedule, durable run index | GAP in native CE | Deduplication, rate/cost controls and operator-selected notification destination; no endless model loop |
| P1 / source code | Where is this resource managed in Terraform? | Existing Git authentication and committed selected paths across providers | REUSE: local Terraform snapshot; no native onboarding | Commit-bound references and uncertain mapping; do not execute repository code or apply changes |

P0 is a product capability, not a requirement to enable every AWS service. A
customer without GuardDuty cannot receive GuardDuty triage; other paths must still
work and explain the absent protection. Do not silently enable paid services.

## Single-account and multi-account onboarding

Offer three choices in the same Hermes conversation:

1. **One account:** existing CLI/SSO identity for operator setup, then a scoped
   read role in selected regions. Confirm identity, readable sources and scope.
2. **Existing security account:** connect the appropriate Security Hub home region,
   Config aggregator, log account or other service-specific delegated administrator.
   Prefer these central views over installing collectors in every account.
3. **Selected accounts without centralization:** operator supplies role ARNs and
   regions; bounded cross-account execution. Optional reviewable CloudFormation
   StackSets/Organizations onboarding later; do not require management-account
   administrator credentials for day-to-day work.

There is no universal AWS security administrator role: a Security Hub connection
is not permission to query every member's CloudTrail, Config history or S3 logs.
An Organizations account list is not proof of access. Keep intended scope separate
from observed coverage. Existing central data may be sufficient for findings;
member roles are needed only for selected deeper reads that central data cannot
supply. Include a non-Organizations list-of-accounts option.

Receipts must preserve execution account, source account, region, service, query,
time range, pages, original record IDs, truncation, errors and observation time.
Deduplicate aggregated/native copies using service-native identity. Do not
aggregate findings across accounts by title alone. Bound per-account and global
API calls, concurrency, returned bytes and run duration; resume with explicit
scope instead of treating the first page as the entire organization.

Initial multi-account proof needs at least two actual accessible accounts, two
regions where supported, and an inaccessible scope. Current one-account tests do
not establish this. Do not invent accounts or create Organizations accounts just
to report a pass; arrange an authorized second account when implementing the test.

## Reuse AWS aggregation and query services

Security Hub should be the first findings integration, preserving producer and
schema identity. It receives findings from multiple native services; enrich only
when the user's question needs details not present there. Do not promise that
all service records, protection plans or new schemas are available through the
existing GetFindings/ASFF path. Verify API/product variants during onboarding.
[AWS integration reference](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-internal-providers.html).

Cross-region aggregation covers configured linked regions where Security Hub is
enabled; it does not enable the service everywhere. Read configured account and
region coverage before making an organization-wide claim.
[AWS aggregation reference](https://docs.aws.amazon.com/securityhub/latest/userguide/security-hub-region-aggregation.html).

Use Config aggregators for authorized multi-account configuration/compliance
views. Aggregation is read-only and does not grant mutation rights in members.
Do not interpret no local recorder as no organization inventory.
[AWS Config reference](https://docs.aws.amazon.com/config/latest/developerguide/aggregate-data.html).

CloudTrail Event history is the quick initial route for recent regional management
events, including the five-day EC2 question. It covers the last 90 days; it is not
a full data-event source or an organization-wide query endpoint. Use existing
trails or event stores for other coverage and retention requirements.
[AWS CloudTrail reference](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/how-cloudtrail-works.html).

CloudWatch Logs Insights supports querying selected groups and linked source
accounts through cross-account observability. Queries incur scan charges. Bound
time and groups, record scan statistics, and distinguish returned-row limits
from actual scan-cost limits.
[AWS Logs Insights reference](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html).

An existing Security Lake is useful through a query subscriber and Lake Formation
permissions, commonly with Athena; discovering the lake does not grant table
access. Reuse OCSF/table schemas and time partitions rather than exporting the
whole lake into the model. Do not create a lake as a prerequisite for CE.
[AWS Security Lake reference](https://docs.aws.amazon.com/security-lake/latest/userguide/subscriber-query-access.html).

Read existing IAM Access Analyzer findings for identity investigations. Different
analyzer types address external, internal and unused access, with distinct scope
and pricing; absence of one is not proof of least privilege.
[AWS IAM reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-findings.html).

## A small capability framework, not a new adapter for each question

Use six reusable skill families: connect/coverage, findings, activity, resource
context, organizational knowledge, and propose/reassess. Explain/review is shared
across them. The model selects an existing capability and parameters; a small
execution boundary validates scope and executes AWS CLI/SDK or a query service.
It persists unmodified source records and deterministic transformations to S3.
Hermes receives bounded results and references, not credentials or every raw log.

Keep data schema per source and version; a common envelope carries identity and
provenance. Use deterministic grouping, timestamps, severity counts and diffs.
Label model correlations and proposed priority explicitly. Never overwrite the
AWS verdict because the LLM thinks an exception applies.

Reuse existing CE code rather than rebuild the agent or UI:
- `rgce/adapters.py`: role assumption, paginated Hub reads, security groups/ENIs,
  bounded committed Terraform snapshots. It explicitly is not an agent tool.
- `rgce/onboarding.py`: read plans, scoped sessions, CloudTrail LookupEvents,
  CloudWatch FilterLogEvents and exact S3 JSON/gzip reads. The 24-hour ceiling
  must be revised deliberately for five-day investigations; arbitrary role names,
  central sources and flexible selection also need design review.
- `modules/native-source-discovery/collector.py`: deterministic S3 receipts,
  source discovery and the limited live Hub sample.
- `rgce/knowledge_library.py`: document collections and materialized views.
- `profiles/native-sketch/desk/skills`: existing Hermes evidence/knowledge/source
  instructions and the explain/review skill.

Prompts cannot bridge an unexposed execution capability. Connect reviewed reusable
functions through the selected native tool/skill surface and independent IAM;
do not give Hermes unrestricted admin CLI access or silently improvise Python
for every missing request. MCP is optional packaging, not a product requirement.

## Minimum useful preview: three complete workflows

**1. My AWS security priorities.** Connect the customer's scope; collect actual
findings with pagination/budgets; group deterministically; enrich selected
resources; apply one real operator knowledge note; return a short prioritized
brief with source severities, proposed priority reasons and coverage gaps.

**2. Explain a change or alert.** Ask the original five-day EC2 question, then an
IAM or security-group activity question through the same capability. Produce
actual timestamps, identities, resources, result/error codes and provenance. If
GuardDuty exists, pivot from a real selected finding into the same investigation.

**3. Propose and reassess.** Prepare a change for one supported issue. The operator
makes an authorized change separately. Recollect the same scope and compare;
report fixed/persistent/unknown using deterministic facts, retaining both runs.
A model statement that a fix worked is not a pass.

All three must work against one account and the supported multi-account route,
with user-visible partial coverage. No external customer's data is implied by
our current model-call permissions: onboarding must explicitly describe provider
and data sharing. CE should show an estimated scope/cost before paid query jobs,
then measured usage when available.

Release acceptance is outcomes-based, not a unit-test count: fresh install by a
security practitioner; their sources; all three workflows; a denied account and
empty/truncated results handled honestly; scoped exception correctly applied;
repeat query without new code; bounded retries; retained evidence after compute
replacement; documented teardown. Tests of paid or absent sources stay NOT_RUN.

## Delivery order

1. Define the account/region/source manifest and connect scoped execution to
   native Hermes. Reuse current role/session and collection code.
2. Complete Security Hub findings + CloudTrail activity; add selected asset
   enrichment and durable receipts. Prove single-account workflows.
3. Add existing central aggregation and selected member-role drill-down; prove
   multi-account scope, deduplication and partial failure handling.
4. Connect knowledge views and close propose -> reassess; run clean onboarding.
5. Extend Inspector, IAM, Macie and existing CloudWatch/S3/Security Lake queries
   based on pilot customers' enabled sources. Keep unsupported routes explicit.

Do not advertise "all AWS native security tools supported" until each integration
has a tested path. The architecture should accommodate them; v0.1 should promise
only its supported set. Expand source coverage without changing the Hermes brain
or requiring a separate agent/profile for each service.
