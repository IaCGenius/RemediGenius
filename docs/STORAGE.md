# Storage: S3 raw objects and Iceberg facts (ADR 0001)

**Status:** accepted 2026-10-29 for the v0.5.0 core storage release (roadmap
[#20](https://github.com/IaCGenius/RemediGenius/issues/20), issues CE-01…CE-15 and CE-24).
**Contract version:** `remedigenius-ce-storage/1` (`rgtriage/contracts.py`).

A Spot instance is disposable. Before v0.5.0 the desk kept its facts in JSON files and checkpointed the whole
desk home to S3 every two minutes. That made a fact durable only if a checkpoint happened to run after it, and
made history an archive rather than data. v0.5.0 makes object storage the system of record.

## Decision

| Store | Holds | Authority |
| --- | --- | --- |
| S3 `raw/` | every collected AWS response, gzip JSON, keyed by SHA-256, write-once | system of record for evidence |
| Iceberg on S3 | OCSF finding tables; CE tables for scan runs, coverage, decisions, fix events, verification attempts, GitHub operations and signals; current-state tables | system of record for facts |
| Local SQLite | current views, in-progress collection pages, commit outbox | cache; rebuildable, never the only copy |
| Hermes home checkpoint | conversations, Kanban, skills, profile, GitHub configuration | unchanged from v0.4.0 |
| OKF bundle | reviewed organizational knowledge | unchanged from v0.4.0 |

This repository ships no external database, no Spark or always-on query service, no retained EBS volume and no
distributed scheduler. PyIceberg runs in the desk process, and history is read in-process with Arrow.
Athena is optional for operators.

## Who may write what

| Store | Writer | Reader |
| --- | --- | --- |
| raw objects | desk only | desk |
| Iceberg facts | desk only | desk |
| SQLite cache/outbox | desk only | desk |
| knowledge bundle | people, through the desk | desk and agent |
| Hermes home | Hermes, checkpointed by the desk | Hermes |

Hermes never writes S3 or Iceberg directly, and the agent's file and terminal surfaces cannot reach the desk's
storage configuration or credentials. A test asserts this matrix (`tests/test_contracts.py`), and the existing
process boundary is unchanged: the agent calls a fixed list of desk commands over a Unix socket.

## Identifiers

| Name | Meaning |
| --- | --- |
| `installation_id` | UUIDv7 created once per installation; survives rebuilds and is checked before a cache is trusted |
| `namespace` | operator-chosen storage namespace (default `remedigenius`); one active desk per namespace |
| `epoch` | UUIDv7 for one recovery epoch; a new epoch starts when the cache is rebuilt on empty disk |
| `sequence` | monotonically increasing integer per installation, assigned to each committed event |
| `event_id` | `evt_<32 hex>` for observed facts, deterministic from installation, scope, observed time and payload hash; UUIDv7 for human decisions and GitHub operations |
| `payload_hash` | SHA-256 of the canonical JSON payload |
| raw `sha256` | SHA-256 of the stored gzip bytes; the raw key is derived from it |
| `batch_id` | deterministic `batch_<32 hex>` from the sorted event IDs and their payload hashes; recorded in the Iceberg snapshot summary |
| `observed_at` / `ingested_at` | when AWS or the source says the event happened / when the desk received it |

`observed_at` and `ingested_at` are never collapsed. A proof observed on 15 June but ingested on 16 June is not
part of "what was known on 15 June". A source clock ahead of ingestion by more than five minutes is recorded and
flagged (`clock_skewed`), never silently reordered or clamped; ordering and point-in-time queries use
`ingested_at`.

The same event ID with different bytes is **quarantined** and excluded from trusted counts. It is never resolved
by "latest timestamp wins". Identical replay is a no-op.

## Event kinds and durability

| Kind | Durable when | Committed |
| --- | --- | --- |
| `observation`, `coverage`, `scan_run`, `signal`, `verification_attempt`, `fix_event` | its raw objects are confirmed in S3 **and** its Iceberg batch commits | one batch per completed scan run |
| `decision` | written to Iceberg | immediately, before the desk acknowledges it |
| `github_intent` | written to Iceberg | before GitHub is called |
| `github_result` | written to Iceberg | after the call |

If a decision cannot be committed, the desk answers `saved locally, not yet durable`, shows that on the board
and keeps retrying. If a GitHub intent cannot be committed, GitHub is not called.

## The write paths

**Scan.** The collector writes each response page to S3 under
`raw/<account>/<region>/<source>/<yyyy>/<mm>/<dd>/<sha256>.json.gz` using a conditional write, so the same bytes
are written once. Observations, coverage and progress are staged in SQLite. When the run completes, one Iceberg
batch commits every fact and its coverage; only after that does the complete-run pointer advance.

**Human decision.** The desk writes the decision event to Iceberg first. The acknowledgement is returned only
after the commit succeeds; otherwise the decision stays visibly pending in the outbox.

**GitHub publish.** The desk commits an intent (operation ID, finding, branch, proposal digest) before it calls
GitHub, then commits the result. An operation without a committed intent does not happen.

## Commit cadence

One commit per completed scan run, plus one per human decision and one per GitHub intent/result. There are no
per-page or per-finding commits. Batch IDs make retries idempotent: after an uncertain commit the desk checks
table history for the batch ID before retrying, and readers deduplicate by event ID so at-least-once delivery
cannot inflate counts.

## Recovery

**Disk intact.** Take the controller lock, open the cache, compare its watermark with Iceberg, drain the outbox
and resume in-progress runs.

**Empty disk.** Read the installation ID and namespace from configuration, verify the catalog and tables belong
to this installation, rebuild the cache from the current-state tables plus newer events, start a new recovery
epoch, re-run unfinished scans, and restore the Hermes home from its existing checkpoint.

**In-flight GitHub work.** Every intent without a committed result is reconciled read-only across open, merged
and closed pull requests using the original operation, branch and proposal identity. A merged PR never triggers
an automatic numbered follow-up; a replacement needs a new approved operation.

A missing catalog, the wrong installation, a schema mismatch or unreachable storage leaves an explicit recovery
state. It never becomes a healthy-looking empty installation.

## Failure policy

- **S3 or Glue outage:** durability pauses visibly. Collection continues up to the configured local buffer
  (`storage.buffer_limit_mb`, default 256 MB), then pauses rather than dropping data.
- **Upload succeeded, desk died:** the raw object is unreferenced but safe. A fact is never committed without
  its raw object.
- **Commit succeeded, acknowledgement lost:** the batch ID in the snapshot summary proves the commit; retry is
  a no-op.
- **Conflicting event ID reuse:** quarantined and excluded from trusted counts.
- **Clock skew:** recorded, flagged, never reordered.

## The only accepted loss window

1. Observations collected but not yet committed: the scope is re-collected on the next scan.
2. A human decision explicitly reported as not yet durable.

Everything acknowledged as committed survives losing the instance. No zero-loss claim is made for uncommitted
collection data.

## Storage profiles

| Profile | Where | Catalog | Use |
| --- | --- | --- | --- |
| `aws` | warehouse `s3://<bucket>/warehouse`; raw `s3://<bucket>/raw/` | AWS Glue database `<namespace>` | Spot |
| `local` | `<RGTRIAGE_HOME>/warehouse`; raw under the durable folder | PyIceberg SQL catalog `<RGTRIAGE_HOME>/catalog.db` | Docker workstation |

`storage.profile: auto` (the default) chooses AWS when `storage.warehouse_uri` is an `s3://` URI and the local
profile otherwise. Both profiles are authoritative for their installation; the local profile is not a test-only
toy. The deployment writes the profile; it is never remembered from chat.

## Table maintenance

Compaction of small files, snapshot expiry and orphan cleanup run from the desk on a schedule
(`storage.maintenance.interval_hours`, default 24). Expiry always retains at least
`min_snapshots` (default 5) and `snapshot_retention_days` (default 14), long enough to cover batch
reconciliation and time travel. Maintenance may run during commits; it may not remove a snapshot still needed to
answer an uncertain batch.

Both profiles run the same in-process maintenance, so no Athena job, Spark cluster or always-on service is required:

- **Compaction** rewrites the current data files when more than one is smaller than
  `target_file_size_mb` (default 128), bounded by `max_compact_rows` (default 200,000 rows). Larger tables report
  that compaction was skipped rather than exhausting memory.
- **Snapshot expiry** uses PyIceberg's expiry with the retention above.
- **Orphan cleanup** deletes only `.parquet` files under the table's `data/` folder that no remaining snapshot
  references and that are older than `orphan_retention_hours` (default 72).

Cost is S3 GET/PUT and Glue API requests during maintenance; there is no hourly service. Athena remains optional
for operators who want SQL over the tables.

## Operator-visible health

`doctor` and `status` report installation and epoch, commit watermark and age, outbox size, not-yet-durable
decisions, raw upload backlog, last maintenance run, Hermes checkpoint age and unresolved GitHub operations. The
checkpoint timer interval is never presented as a data-loss bound.

## Rejected alternatives

- **SQLite or JSON as the system of record.** A replaced Spot instance loses it.
- **An external operational database.** Adds a service, credentials and failure mode the desk does not need.
- **Iceberg only as an optional export.** Facts would not be authoritative, and recovery would still replay
  archives.
- **Per-page or per-finding commits.** Too many small commits; maintenance would dominate.
- **Restoring SQLite from a checkpoint.** It can restore a cache that does not match the committed facts. The
  cache is rebuilt instead.

## Upgrading

v0.5.0 is a fresh-install release. It does not import the v0.4 JSON state. An existing desk home is detected and
the desk stops with instructions to move or delete it (`docs/UPGRADING.md`). The Hermes home and the OKF bundle
keep their current upgrade path.

## Implementation map

The contract is CE-01. The rest of the release fills it in; this table is updated as each issue lands.

| Issue | Module | State |
| --- | --- | --- |
| CE-01 data contract | `rgtriage/contracts.py`, `rgtriage/schemas/`, this document | done |
| CE-24 OCSF mapping and Iceberg schemas | `rgtriage/ocsf.py`, `rgtriage/schemas.py` | done |
| CE-05 SQLite cache, outbox, controller lock | `rgtriage/cache.py` | done |
| CE-06 raw responses to S3 | `rgtriage/rawstore.py` | done |
| CE-12 Iceberg profiles and maintenance | `rgtriage/iceberg_store.py` | done |
| CE-13 commit loop | `rgtriage/commit.py` | done |
| CE-02…CE-04 lifecycle fixes | `rgtriage/fixes.py` | planned |
| CE-07 resumable collection | `rgtriage/collect.py` | planned |
| CE-08 episodes and lifecycle | `rgtriage/lifecycle.py` | planned |
| CE-09 command cut-over | `rgtriage/repository.py` | planned |
| CE-10 current-state tables | `rgtriage/current.py` | planned |
| CE-11 rebuild and reconciliation | `rgtriage/recovery.py` | planned |
| CE-14 scoped history queries | `rgtriage/queries.py` | planned |
| CE-15 crash/outage proof and health | `rgtriage/health.py`, `tests/test_storage_live.py` | planned |

See also: [ARCHITECTURE.md](ARCHITECTURE.md) · [SCHEMA.md](SCHEMA.md) · [DATA-FLOW.md](DATA-FLOW.md) ·
[LIMITS.md](LIMITS.md) · [IAM.md](IAM.md) · [UPGRADING.md](UPGRADING.md).