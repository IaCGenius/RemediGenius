# MCP release: chat context and data routing

Unreleased Spot evaluation, 2026-11-02 UTC. Measurements below are observations, not a controlled
before/after token benchmark. No release has been published.

## What enters the model context

| Capability | Chat surface | When its larger content enters context |
| --- | --- | --- |
| AWS Knowledge | Five selected native MCP tools | Discovery, requested tool description, relevant AWS document/skill |
| Terraform Registry | Seven selected native MCP tools | Discovery and provider/module results |
| DeepWiki | Three native MCP tools | Discovery and repository answers |
| Managed AWS account reads | Existing bounded `rg_triage` action | Requested read result; upstream script interface is never exposed |
| Athena/Data Processing | One deferred `rg_analytics` tool | Compact schema, on-demand skill, bounded aggregate rows |
| Staged document providers | Disabled until connected | No usable tool schemas while disabled; catalog presence is not certification |

Hermes 0.21.7 already defers non-core tool schemas behind search/describe/call. Its default embedded
discovery listing budget is at most 4,000 estimated tokens, also constrained by 5% of model context.
This is a listing budget, not a cap on tool results, skill contents, or total conversation context.
Its schema estimator uses characters divided by four, not the model tokenizer. We retain native discovery.

The 36-tool AWS Data Processing catalog is kept inside the desk worker. Hermes never receives it.
The new analytics schema serializes to 717 characters locally; the live describe response was 722 characters.
The earlier general desk describe response was 9,079 characters. These are different tool surfaces, not
an overall context reduction claim. Installed skills are indexed; their full bodies load on demand.

## Observed costs

Two earlier persisted conversations illustrate where growth occurs:

- AWS walkthrough: 36,292 characters of tool responses, including three skill reads and one desk description.
- Mixed DeepWiki/Terraform conversation: approximately 153,000 characters of tool responses, including ten
  repository questions, four Registry searches and two file reads. This is not the cost of merely enabling MCP.

The first natural-language analytics test loaded `rg-analytics`, described `rg_analytics`, then obtained trend,
coverage and scan coverage. Actual response lengths were 3,940 characters for the skill, 722 for tool details,
and 1,193 + 1,535 + 1,513 for reports. The UI showed about 14.3k total context tokens at completion.
Session billing/cache counters are cumulative across calls and must not be reported as current context.
This was not an identical-prompt MCP-off comparison, so an exact percentage increase is not established.

A second fresh chat after the interpretation fix used just trend and coverage and finished at approximately
13.6k UI-reported context tokens. It explicitly distinguished five checks from five days and equal daily counts
from identical membership. Model wording remains something to evaluate; two successful examples are not a
guarantee of every answer. The reports retain full provenance even when the assistant abbreviates citations.

## Data routing contract

- Current queue, deterministic priorities: existing digest/list/current paths.
- Historical aggregates: bounded Athena MCP reports for trend, coverage, verification, scan coverage.
- Exact point-in-time answers, individual timelines and closure proof: existing committed-batch history.
- Current AWS configuration: scoped audit-role reads, using configured direct or managed-MCP transport.
- Organization policy: reviewed OKF; query output is evidence, not automatically policy.

Reports accept only an enumerated report, 1–90 days, and optional account/region. SQL is compiled by the desk,
not supplied by the model. Each relevant Iceberg table is pinned to its selected snapshot. Multi-table reports
are descriptive and do not claim an atomic cross-table committed batch. Result windows, query ID, scan bytes,
snapshot IDs, durability and limitations accompany rows. No upstream polling transcript is sent to the model.

Live testing caught a model interpreting five collection checks as five days. Column names now explicitly say
`collection_checks` and `truncated_checks`; the returned interpretation and skill distinguish checks from days,
equal counts from identical membership, and earliest returned records from installation date.

## Recovery evidence and remaining limits

Live negative checks passed: disabled setup returned unavailable, an actual request against an unauthorized
workgroup was rejected, account-scoped scan counts were refused rather than broadened, and an allowed trend
query then succeeded. These checks used separate configuration copies and did not change the active profile.

The lab now runs the packaged standard deployment. Terraform manages the role/workgroup, and a replacement
instance installed both pinned runtimes and restored chat/profile state. All four reports passed again through
the desk socket (1.4–1.9 KB responses, approximately 12–13 seconds). An injected polling delay exercised the
timeout cleanup path and issued a real cancellation request; the small query had already succeeded, so an
in-flight `CANCELLED` terminal state is not proven. The workgroup enforces a 100 MiB per-query scan cap.

Scan-limit exhaustion, long-running credential expiry and a controlled concurrent-collection race remain
untested. Authenticated document providers are not certified by public MCP testing. Replacement of an existing
lab is not evidence of creating the entire stack from zero. See [release validation](RELEASE-VALIDATION.md).
