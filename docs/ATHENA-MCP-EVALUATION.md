# Athena and AWS Data Processing MCP: live experiment

Evaluated 2026-11-02 UTC on the existing disposable CE Spot lab. This is an experiment, not a released feature
or a new default Hermes connection. No CE table was migrated or modified.

Follow-up: bounded desk reports are now exercised through live Hermes chat. See
[MCP context review](MCP-CONTEXT-REVIEW.md) for the routing, observed context costs, interpretation correction
and remaining release gates. The original direct-vendor experiment below is retained as its own evidence.

## Decision

Keep the desk's current/history tools as the default for individual users. Offer Athena analytics only when
cross-table SQL or larger historical exploration provides enough value to justify extra IAM, query results,
cost controls and semantic guidance. Reuse the upstream query tool; do not expose the full data-engineering
catalog or rebuild its service connectors.

The existing desk retains an important advantage beyond speed: its historical answers bind evidence to a
committed batch, coverage and durability watermark. Arbitrary Athena SQL does not automatically preserve that
contract. SQL results must not replace the board's priorities or certify resolution without scope-aware evidence.

## What actually ran

- Official `awslabs.aws-dataprocessing-mcp-server==0.2.2`, installed in a separate Python 3.11 environment.
- Actual MCP initialize/list-tools/call-tool over stdio on the Spot host, using temporary analytics-role credentials.
- 36 vendor tools discovered, including five Athena tools. The experiment invoked only
  `manage_aws_athena_query_executions` for start/status/results.
- `--allow-write` was **not** enabled. Upstream SQL validation permits SELECT and rejects DDL.
  `--allow-sensitive-data-access` was enabled to retrieve customer query results; a separate test without it
  confirmed that results were refused. This flag is not a substitute for IAM restrictions.
- Athena engine 3; dedicated workgroup with enforced SSE-S3 output location and a 100 MiB per-query scan cutoff.
- Dedicated role trusted only by the lab host. Permissions: CE Glue database/table metadata, S3 warehouse reads,
  query execution in this workgroup, and reads/writes in a separate query-result prefix. No raw evidence or
  checkpoint access, warehouse writes, or Glue mutation grants. The host received only an additional assume-role
  permission for this analytics role. The target-account audit role and ordinary AWS MCP transport were unchanged.

The initial harness assumed the older SDK's `isError` Python attribute. This package resolves an SDK using
`is_error`; the first submitted query was not interpreted until the harness was corrected. The extra execution
is included in the usage totals below. This is a compatibility check required before wiring into pinned Hermes.

## Results and usefulness

All four aggregate result sets exactly matched independently computed PyIceberg reads of the same tables.
These are small-dataset observations, not a performance benchmark; timings exclude shared MCP startup and
include query polling. The comparison is direct PyIceberg aggregation, not end-to-end desk history latency.

| Question | Actual result | Athena/MCP seconds | Direct Iceberg seconds | MCP calls | Athena bytes scanned |
| --- | --- | ---: | ---: | ---: | ---: |
| Current findings by priority | P1 25; P2 39; P3 119; P4 40; total 223 | 1.25 | 0.63 | 4 | 1,912 |
| Coverage by source/status | Eight source categories over five scans; Health unavailable each time | 2.28 | 1.23 | 5 | 9,845 |
| Historical observations versus distinct findings | 665 observations on Nov 1; 446 on Nov 2; 223 distinct keys each day | 3.29 | 0.65 | 6 | 31,958 |
| Verification outcomes | No recorded attempts | 1.23 | 0.15 | 4 | 0 |

An additional SQL join linked scan_runs to coverage by run_id. It returned five scans: the first contained
219 findings, the later four 223, each with eight source checks and one gap. This supports explaining a coverage
limitation alongside a trend; it does not prove that the four additional findings were newly created risks.

Two product lessons are concrete:

1. **1,111 observation rows are not 1,111 distinct issues.** Repeated collection of the same findings must not be
   described as new findings or recurrence after a fix. Recurrence requires lifecycle/proof evidence.
2. **An empty verification table means no recorded proof**, not that all fixes succeeded or failed. This lab
   cannot certify remediation-duration, recurrence or verification-success analytics using populated history.

The experiment spans only two observation dates. It cannot substantiate a 30-day trend or scale comparison.

## Failure checks

| Control | Evidence |
| --- | --- |
| DDL rejected without write mode | Actual MCP request rejected before query submission |
| Other Athena workgroup inaccessible | Actual start request to another workgroup denied |
| SQL failure is not success | Invalid-column query submitted, then reached FAILED; no result accepted |
| Pagination respected | Two-row result page returned a continuation token; next page differed |
| Result-data access explicit | Vendor server without sensitive-data flag refused get-query-results |
| Warehouse read allowed; writes denied | IAM policy simulation, not attempted writes |
| Checkpoint/raw reads and table deletion denied | IAM policy simulation, not attempted reads/deletion |

All seven submitted Athena executions finished: six succeeded and the deliberate invalid query failed.
Total reported data scanned was 64,227 bytes. This includes the first harness attempt and the join. It is
**not a bill estimate**: Athena minimum billing increments, S3 requests and result storage are additional
considerations. The 100 MiB cutoff is per query, not a cumulative budget. No running/queued queries remained.

## How to turn this into a useful CE feature

1. Keep credentials outside Hermes. Add an opt-in analytics connection using a separate scoped role/workgroup.
2. Expose only the vendor query capability through native deferred discovery or a bounded desk workflow;
   do not inject the 36-tool catalog. Verify compatibility with CE's pinned Hermes/MCP SDK first.
3. Load a short analytics skill on demand with the actual CE schema and reviewed query recipes. Always state
   whether a number counts observations, distinct finding keys, issues, verification attempts or scan runs.
4. Require account/time scope, result limits and query timeout/cancellation; record query ID, scan bytes,
   pagination, selected snapshots and coverage. Use committed-batch mappings for cross-table as-of answers.
5. Validate resource-scoped IAM, SQL controls, timeouts, throttling, cost-limit failure and expired credentials.
   Do not enable write mode to bypass a rejected query.
6. Explain answers with small aggregates and evidence references; draft durable guidance into reviewed OKF
   separately. Analytics output is not automatically organization policy or current AWS configuration.

The sample queries are in [athena-security-history.sql](../tools/experiments/athena-security-history.sql).
They are evaluation recipes, not approved production reporting views.

## Traceability and remaining limits

Private setup scripts, resource identifiers, IAM policy and usage records are under
`.rgce/knowledge-live-20261101/` (steps 073–086). Remote transcripts and comparisons are under `/data/rg-lab/`.
The isolated role and workgroup remain for maintainer review; no native Hermes connection or background query
schedule was added. Remove the added host assume-role policy, analytics role and experimental workgroup when
retiring the lab; result objects are isolated under its experiment prefix. Existing CE resources stay intact.

Not tested: native Hermes UI queries, fresh deployment, credential renewal, forced scan-cap cancellation,
cross-table snapshot consistency during concurrent collection, large datasets, multi-account reporting,
and populated remediation/verification histories. No release was published.

Upstream references:
- [AWS Data Processing MCP](https://awslabs.github.io/mcp/servers/aws-dataprocessing-mcp-server)
- [Athena Iceberg compatibility](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg.html)
