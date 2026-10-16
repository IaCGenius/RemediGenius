---
name: ce-aws-read
description: Use the native ce_aws tool for scoped AWS reads, SDK schemas, exact evidence inspection and deterministic reassessment. No shell or generated collector.
license: Apache-2.0
---

# Scoped AWS execution

For security interpretation and proposals load ce-aws-security. This skill explains
execution, not conclusions. Native preflight supplies current UTC time, target
aliases/account IDs/regions and supported operations. READY proves executor
connectivity and package integrity, not source availability. Individual receipts
prove reads. Do not discover broader credentials or use another execution route.

For live reads or snapshot comparisons, load ce-investigation and use ce_assessment.
The runtime invokes the read/compare actions below inside its bounded plan; direct
chat calls to those two actions are redirected before execution. Capabilities,
schema and saved-evidence show remain available directly when no workflow is active.

The `ce_aws` adapter supports the same reusable actions for all configured
services; no task-specific collector is needed. `parameters` is a JSON object of
AWS SDK input fields, not CLI options. Supply target and region for each read.

- `capabilities`: refresh configured scope if needed; preflight normally provides it.
- `schema`: supply service, operation, and optional field path to inspect installed
  botocore input definitions. Use before drafting API inputs; never guess a shape.
  This is local metadata inspection, including write-operation shapes, not an AWS
  request or permission to execute them. It proves SDK field names/types only,
  not CLI flag spellings, Terraform arguments or CloudFormation properties.
- `read`: service, operation, target, region, parameters and max_pages. Preserve
  the user's filters and page budget. Omitted max_pages collects one page. For a
  one-page request use max_pages=1; MaxResults controls items per page, not pages.
  Increase max_pages only when the task calls for wider collection. Do not repeat
  reads to bypass a requested limit. One request yields scope, observation time,
  original source records, deterministic summary and exact S3 paths.
- `show`: path returned by read; optional JMESPath query, offset and limit (1–200
  lines). Use one compact projection; if truncated narrow it, not a new script.
- `compare`: before and after actual run IDs. Security Hub comparison uses
  ProductArn+Id, ignores transport tokens/page ordering, and preserves all finding
  fields. Incomplete, failed, mismatched or non-newer snapshots are INCOMPARABLE.
  Other services use response comparison and may retain page/order differences.

## Common request shapes

ACTIVE Security Hub findings: service `securityhub`, operation `get_findings`,
parameters `{"Filters":{"RecordState":[{"Value":"ACTIVE","Comparison":"EQUALS"}]}}`.
Do not silently add workflow/severity filters. WorkflowStatus is an input filter;
response Workflow.Status is not an input shape.

EC2 inventory: service `ec2`, operation `describe_instances`, parameters `{}`.
For multiple targets use separate reads/receipts. Do not mix account counts.

CloudTrail management activity: service `cloudtrail`, operation `lookup_events`,
parameters with timezone-aware StartTime/EndTime and LookupAttributes, e.g.
`[{"AttributeKey":"EventSource","AttributeValue":"ec2.amazonaws.com"}]`.
Calculate the actual requested interval from the preflight UTC time. LookupEvents
cannot retrieve object data events or activity outside its 90-day history.
A page limit, including ten pages, never guarantees full time coverage.

## Evidence shapes

Raw `raw/RUN/aws-read.json` contains original `pages`:
- Hub: `pages[].Findings[]`. A compact projection can select Id, Title,
  Severity.Label, Description, Resources, UpdatedAt and Compliance.
- EC2: `pages[].Reservations[].Instances[]`. OwnerId is on Reservation, not Instance.
- CloudTrail: `pages[].Events[]`; CloudTrailEvent is a JSON string. Prefer the
  normalized timeline for decoded errors and identities instead of parsing it.

Normalized `normalized/RUN/findings.json` retains Id, ProductArn, AwsAccountId,
Region, Title, Severity, Workflow, RecordState, UpdatedAt, Resources, Compliance
and Remediation. Description/Types/source observation times are in the raw records.
Its root is an object containing `findings`, not a bare list. Start normalized
queries with `findings[...]` or `findings[]`; raw queries use `pages[].Findings[]`.
An unexpected null projection is not an empty collection. Inspect `keys(@)` once
only if the actual source shape differs from this documented shape.

For totals, grouping and filtering, use the returned deterministic summary or a
`show` JMESPath aggregation over the exact stored records. Do not count a rendered
list in your reasoning and present that as deterministic computation. For example,
EC2 state counts can use `pages[].Reservations[].Instances[] | {total: length(@),
running: length([?State.Name == 'running']), stopped: length([?State.Name == 'stopped']),
terminated: length([?State.Name == 'terminated'])}`. Include other observed states
when present and check group totals equal the full returned count. Reuse the same
receipt; aggregation does not require another cloud read. If an aggregation was
not executed, say so instead of describing model arithmetic as tool output.

Normalized `normalized/RUN/timeline.json` contains `events`, with EventId, EventTime,
EventName, EventSource, Username, Resources, ReadOnly, ErrorCode, ErrorMessage,
SourceIPAddress, UserIdentity and BodyParseStatus. Username may be absent. An event
body parse error means outcome unknown, not successful API activity. The read
summary includes event-name counts, earliest/latest event times, API error count,
parse-error count and bounded error-event previews. Reuse those deterministic counts.
Keep each aggregation's denominator explicit. Counts over all returned events must
not appear under a successful-events heading. For success/error breakdowns, filter
the decoded events first and aggregate each subset separately; dry-run API errors
are not executed changes. Check subgroup totals against their stated population.

Knowledge is separate: use ce_knowledge for the selected index/document/metadata.
Do not scan all S3 or the local cache. A receipt's exact S3 path avoids stale cache.

## Boundaries and finish condition

The runtime admits structured calls; Lambda independently validates operation,
region, target, parameters and page/byte/time bounds, and IAM restricts reads.
No cloud mutation is exposed. No terminal or generated Python fallback is allowed.
Access denied stops that operation for the current turn. Budgets are supplied by
preflight; when reached, summarize partial results without another attempt.

Preserve original AWS severities, errors and partial pagination. A zero-result
successful request is empty in that observed scope; it does not establish security.
Finding changes do not certify remediation. The investigation controller reads and
reviews its frozen evidence packet; do not add another ce_review after completion.
For a direct saved-evidence answer outside a workflow, read the relevant records,
prepare a concise draft, call ce_review once, apply supported corrections and finish.


### Find CE infrastructure

For "what CE resources exist", inspect capabilities and use
`resourcegroupstaggingapi.get_resources` with TagFilters Key=Project,
Values=[remedigenius-ce], and a bounded page budget. Retain service-returned ARNs
and scope. Tag inventory omits untaggable/untagged resources: it is not exhaustive
and cannot calculate costs. Point the operator to Cost Explorer filtered by the
Project tag; do not call billing APIs or infer a bill from resource counts.
