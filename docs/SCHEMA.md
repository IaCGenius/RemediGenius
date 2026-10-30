# Findings and table schemas (v0.5.0)

**OCSF version:** 1.9.0 (released 2026-08-03, pinned). **CE table schema version:** 1.
**Implementation:** `rgtriage/ocsf.py`, `rgtriage/schemas.py`, `rgtriage/schemas/ocsf-1.9.0-findings.json`.

The raw response in S3 remains the authoritative bytes. Every fact row links to it by `raw_sha256`; a row without a
raw object is not committed (`docs/STORAGE.md`).

## What AWS reported: OCSF

Findings use OCSF category **2 (Findings)**. The reviewed mapping is:

| Source | OCSF class | Class UID | Why |
| --- | --- | --- | --- |
| Inspector | Vulnerability Finding | 2002 | packages, CVEs, exploit and fix signals |
| GuardDuty | Detection Finding | 2004 | threat detections and attack sequences |
| IAM Access Analyzer | Detection Finding | 2004 | external/internal access detections |
| AWS Config rules | Compliance Finding | 2003 | rule evaluations |
| Security Hub control checks | Compliance Finding | 2003 | controls failing a standard |
| Security Hub threat findings | Detection Finding | 2004 | category `threat` |
| Security Hub vulnerability findings | Vulnerability Finding | 2002 | category `vulnerability` |
| Security Hub v2 exposure findings | AWS's own OCSF record | as AWS wrote it | stored without lossy re-mapping |
| Unknown source | base Finding | 2001 | fallback with a reported mapping error, never a guess |
| CloudWatch alarms, AWS Health | CE `signals` table | — | not findings |

Mapping changes require a reviewed change and a reason in the commit or issue. The mapping table is code
(`SOURCE_CLASS` in `rgtriage/ocsf.py`), not configuration.

### CE extension and residual source fields

OCSF does not define CE's priority, reasons, finding key, raw reference or coverage. They live in
`unmapped.ce`. Source fields CE does not map are retained in `unmapped.fields`, with the full original always in
the raw object; `unmapped.source_keys` lists what came in.

| CE extension field | Meaning |
| --- | --- |
| `finding_key` | CE's stable finding reference |
| `source` | collector name |
| `priority`, `reasons`, `issue_key` | the desk's ranking, with its written reasons |
| `scope` | account, region, source, filter hash |
| `raw_sha256`, `raw_key` | the raw object this row came from |
| `observed_at`, `ingested_at` | source time vs receipt time |
| `coverage_status`, `truncated` | whether the read was complete |
| `mapping`, `mapping_error` | `native`, `passthrough` or `fallback`, and why |

Security Hub v2 exposure findings keep every field AWS returned. CE adds only `unmapped.ce`; if the original
record was not retained, mapping fails closed instead of re-mapping it lossily.

## CE tables

| Table | Holds | Partition columns |
| --- | --- | --- |
| `findings` | OCSF rows, one per observation | `account_id`, `region`, `class_uid`, `event_day` |
| `signals` | CloudWatch alarms and Health events | `account_id`, `source` |
| `scan_runs` | one row per completed scan: scope, counts, truncation | — |
| `coverage` | what was inspected and what was not | `account_id`, `source` |
| `decisions` | human decisions, committed before acknowledgement | — |
| `fix_events` | fix lifecycle changes derived from scans and proofs | — |
| `verification_attempts` | every proof attempt, including failures | — |
| `github_ops` | GitHub intents and results | — |
| `current_findings` | current board facts for fast rebuild | `account_id` |
| `current_fixes` | current fix records | — |
| `current_decisions` | current decisions | — |
| `current_operations` | open GitHub operations for recovery | — |
| `campaigns` | one row per campaign version: scope digest, member count, and the approval that froze them | — |
| `campaign_members` | complete membership per version; `ordinal` is the pagination cursor | `account_id` |
| `deployment_receipts` | PR, merge, build, deploy and verification receipts from existing CI/CD, with producer, payload digest and outcome | — |

`campaign_members` is the authoritative scope: the board preview is bounded on purpose, while decisions and approved
actions read the frozen membership digest. A target discovered after approval starts a new campaign version and needs a
new approval — it can never join an approved scope silently.

`account_id`, `region`, `class_uid` and `event_day` are top-level columns as well as fields inside the OCSF
record, so partitioning does not depend on nested access. `event_day` is the UTC observation day.

Current-state tables carry the `watermark` they reflect, not a commit timestamp guess. Rebuild reads them and
replays events newer than that watermark; it never assumes tables committed together.

## Schema version and evolution

- `ce.schema_version` is a table property and `TABLE_SCHEMA_VERSION` in code. Version 1 is the first release.
- Adding a column: new optional field, new field ID, version bump, tested read of an older table.
- Existing field IDs and names never change. Renames are new columns plus a projection.
- Only `int → long` and `float → double` promotions are allowed.
- A required column cannot be added in place; start a new table version or backfill before making it required.
- An OCSF version upgrade is an explicit migration with a new pinned version, a re-validation and a documented
  mapping diff. It is never implicit.

`rgtriage.schemas.create_tables(catalog, namespace)` creates missing tables and refuses an existing table whose
required columns or types differ (`SchemaMismatch`). It never overwrites a table.

## Validation

- Synthetic fixtures per source map to the documented class and pass
  `rgtriage/schemas/ocsf-1.9.0-findings.json` in the tests.
- Every mapped row links to its raw object by SHA-256; the raw object keeps the original source fields.
- Unknown or changed fields are kept in raw and `unmapped.fields`, and the mapping error is visible.
- The JSON Schema is a CE subset of OCSF 1.9.0, not a replacement for the full OCSF schema. Interoperability
  testing against other OCSF consumers is listed as a release-validation gap until it is run.

## Signals

CloudWatch alarms in ALARM and AWS Health events are not findings. They go to `signals` with their resource,
severity, status and a JSON `detail`; they do not appear in the OCSF `findings` table and cannot claim a finding's
closure.

See [STORAGE.md](STORAGE.md) for authority, commit and recovery rules, and [AWS-CAPABILITIES.md](AWS-CAPABILITIES.md)
for what each source can and cannot report.