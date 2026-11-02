---
name: rg-analytics
description: Answer historical security trends, source coverage across scans, and recorded verification outcomes using bounded Athena MCP aggregates. Use for counts over time or cross-scan analysis; retain desk history for individual findings and point-in-time proof.
license: Apache-2.0
---
# Security history analytics

For aggregate questions discover `rg_analytics`, then call it with `report=<report> days=<1..90>`.
The desk runs the existing AWS Data Processing MCP in an isolated runtime with a scoped analytics role.
Do not discover its full tool catalog, write SQL, request credentials or fetch raw observation pages to count them.

| Question | Report | Interpretation |
| --- | --- | --- |
| Historical finding volume | trend | Observations and distinct finding keys per event day; records ingested within the requested window |
| Collection blind spots | coverage | Source/status collection checks and truncated checks; checks are not days; use with trend before interpreting changes |
| Recorded verification outcomes | verification | Attempts by outcome, not unique fixes or a success rate without an agreed denominator |
| Finding counts alongside scan coverage | scan_coverage | Installation-wide completed scans with source-check/gap counts; no account/region filter |

Use the requested days, otherwise 30. Scope with `account` (12-digit ID) and `region` when supplied. Clearly
state installation-wide scope when omitted. `scan_coverage` does not accept account/region scope because its
finding counts are installation-wide; use scoped coverage instead. Never silently broaden a scoped question.

Require a SUCCEEDED report, then use its rows, columns, query ID, snapshots, scan bytes, truncation and durability.
An empty result means no recorded evidence in the window. A failed, denied, timed-out or disabled connection is
not zero findings. Explain the gap; do not repeatedly retry or pretend a page of history is a complete aggregate.
For trend questions normally obtain trend plus coverage, or just scan_coverage if it answers the question.
Return a compact table and a short interpretation; do not echo SQL, entire schemas or the polling transcript.

Repeated observations are not new issues or recurring failures. Distinct finding keys are not grouped issues.
Counts across days must not be summed into distinct totals. Changed coverage/scope can change counts without a
security change. Missing coverage is unknown, not healthy. No verification attempts means no recorded proof.
Equal daily distinct counts do not prove identical finding membership. The earliest returned record is not
proof of the installation date. Missing dates mean no returned records; do not invent why they are missing.
Do not claim remediation success, recurrence, time-to-fix or causality without corresponding lifecycle evidence.

Reports pin individual table snapshots, not a shared cross-table committed batch. For exact as-of questions,
individual finding timelines, raw-evidence references, or proof of closure, use the existing history/timeline
tools. Live configuration still uses `action=aws`; the current queue uses digest/list. Analytics does not replace
the desk's deterministic priorities or authorize changes. Consult reviewed OKF for business interpretation.
