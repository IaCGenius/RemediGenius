# Inventory and source fallback

Use this procedure for any AWS resource family, not only security-service findings.
An existing configured account is already connected. Do not call missing inventory
an onboarding problem or propose provisioning resources to answer a read question.

## Choose sources in order

1. Config aggregator discovery first. If an accessible aggregator covers the target,
   query with SelectAggregateResourceConfig and explicit account/region/type scope.
   An aggregator's existence alone does not establish coverage or freshness.
2. If none exists, or coverage is missing, use account-local SelectResourceConfig
   and ListDiscoveredResources. Describe recorder/status when recording is unclear.
   An empty aggregator list does not prevent local queries. Empty Config results
   establish no matching recorded resources, not absence in the account.
3. When Config is empty/unavailable/incomplete, use Cloud Control list_resources
   for the relevant AWS:: resource types. Use cloudformation list_types with a
   TypeNamePrefix filter or describe_type when names/handler support are uncertain.
   This is not provisioning and does not require the resource to be in a stack.
   Inspect the root SDK schema before selecting a nested field. On
   UNKNOWN_SCHEMA_FIELD, use the returned parent/available fields to correct the
   schema lookup within the existing action budget; it is not an AWS access error.
   get_resource reads configuration by the identifier returned by list_resources.
4. Existing admitted service reads can enrich configuration. Resource Explorer
   can search an existing index/view; tagging can find tagged resources. Neither
   proves absence of unindexed or untagged resources. Do not enable an index.
5. CloudTrail answers who/when/how and success versus failure. An attempted Create
   with an error is not a created resource. Model availability/inference profiles
   supplied by AWS are not necessarily customer-created resources.

Prefer a useful grouped plan: discover aggregator and local Config inventory in
the first round when coverage is unknown; use the relevant Cloud Control types in
the next round if Config has no data. Keep criteria within available rounds/reads.
The preferred source order is not a requirement to spend every read proving the
same empty source. Existing fresh source-coverage receipts can avoid repeated probes.

## Spend the budget on resources

Reserve at least half of the six cloud reads for actual resource enumeration or
configuration. Start with aggregator discovery and a scoped local Config SELECT,
not a sequence of recorder/status/registry prerequisites. Recorder diagnostics
can explain coverage later; no active recorder does not rule out retained records.
If the relevant standard AWS resource type is known, call Cloud Control directly;
registry discovery is not a mandatory prerequisite for each type. Group independent
resource-type reads in one round. Return found resources first and name unqueried
types as gaps. Never let "process complete" imply an exhaustive family inventory.

When registry discovery is needed, use cloudformation list_types parameters:
`{"Visibility":"PUBLIC","Type":"RESOURCE","Filters":{"TypeNamePrefix":"AWS::<service>::"}}`.
Replace the service placeholder with the relevant AWS namespace. TypeNamePrefix is
inside Filters, not at the root. The default PRIVATE visibility can return an empty
list even when AWS resource types exist; that is not an unsupported-service result.
The default provisioning filter is FULLY_MUTABLE; immutable types need a separate
query when relevant. Registry types describe capabilities, not deployed resources.
See [AWS ListTypes](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ListTypes.html).

Use existing indexed or tagged resource discovery to identify relevant types when
helpful, then enrich them through Cloud Control. Those sources have incomplete
coverage; do not silently treat their results as all resources in the account.

## Failures and credentials

For each attempted source name the operation, target, region, observed time and
actual failure: no aggregator, no recorded matches, AccessDenied, unsupported type,
throttle, missing required parameter or timeout. Do not merge these into "no access".
Do not repeat a denied request or tell the operator to grant admin access.

The collector uses the Spot instance role or the workstation AWS profile. An
explicit executor target can assume its configured role with an external ID;
the current launchers configure one account. SecurityAudit/ViewOnlyAccess provide metadata permissions;
the admitted operation catalog and target scope still constrain execution. Cloud
Control also needs the resource schema's downstream list/read permissions. A
missing dependency is a permission gap, not a reason to generate a new collector.
No credential values, private handler or alternate RoleArn may be passed by chat.

## Pagination and large data

For inventory/history requiring completeness request max_pages=10, unless the user
sets a smaller bound. Check has_more, pages_returned and stop_reason. A page is not
a time window. Continue with the exact continuation_parameters, same scope and
filters, within the remaining budget. Never silently restart at page one.
Each batch remains in S3. Use deterministic summaries and targeted projections;
do not send complete raw event bodies to the model. Different batch counts may
overlap; do not claim a deduplicated total unless a deterministic aggregation ran.
If the budget is reached, deliver partial records plus the saved continuation and
offer to continue. Do not claim the requested period was fully covered.

## Delivery and retained work

Return the actual resources found before discussing gaps. Distinguish current
configuration, historical activity and AI interpretation. Source errors stay next
to their attempted source. A BLOCKED assessment retains its results and receipts;
ce_assessment show returns the collected summaries. Cancellation does not erase
these results. Do not invent infrastructure failures from an empty model exception.
