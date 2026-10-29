# Recovery and storage health

This runbook covers the v0.5.0 durable store. Facts live in S3 raw objects and Iceberg tables; the local SQLite cache
is rebuildable. The authority and commit rules are in [STORAGE.md](STORAGE.md), the table schemas in
[SCHEMA.md](SCHEMA.md).

## One active desk per storage namespace

Exactly one desk process may own a cache and commit loop for a namespace. The desk takes an OS file lock
(`desk.sqlite3.lock`) at startup; a second process fails with the owner PID instead of writing. Stop the old desk
before replacing an instance. There is no distributed leader election and no active-active mode.

## Normal restart (disk intact)

1. Open the cache and the Iceberg catalog.
2. Compare the cache watermark with the current-state tables.
3. Rebuild the views from the current tables if Iceberg is ahead; drain the outbox.
4. Resume unfinished collection scopes; completed scopes are skipped.

No action is needed. The boot log prints `recovery: {...}` with the state and counts.

## Replacement Spot instance (empty disk)

1. The host restores the Hermes home, the small configuration home (`triage.yaml`) and the GitHub configuration.
2. The desk adopts the configured installation ID and namespace, verifies that the Glue database and tables belong to
   it, and starts a new recovery epoch.
3. It rebuilds current views from `current_*` tables, then replays events newer than those tables' watermark when the
   event tables are available.
4. It re-runs scans that were not committed. Uncommitted observations are never presented as facts.

A missing catalog, wrong installation, schema mismatch or unreachable storage leaves `state: blocked` with a reason.
It never looks like a healthy empty installation.

## S3 or Glue outage

- **During a scan:** raw pages wait in the bounded local buffer (`storage.buffer_limit_mb`, default 256 MB). The board
  and `doctor` show the backlog and `state: degraded`. At the limit, collection pauses rather than dropping evidence.
- **During a decision:** the decision is written to the local outbox and acknowledged as *saved locally, not yet
  durable*. It is retried; do not treat it as durable until the watermark advances.
- **During maintenance:** commits continue; maintenance reports the failure and leaves snapshots alone.
- **After recovery:** `rgtriage doctor` should show `state: healthy`, a recent commit watermark, an empty outbox and
  no buffered raw objects. `rgdesk maintain --dry-run` previews maintenance; `rgdesk maintain` runs it.

The only accepted loss window is data that never reached S3/Iceberg: an uncommitted scan (re-collected) and a decision
explicitly reported as not yet durable.

## GitHub operations across a restart

Every operation has a committed intent before GitHub is called and a result afterwards. On restart, intents without a
result are reconciled read-only across open, merged and closed pull requests using the original operation, branch and
proposal identity. A merged pull request is recorded as merged; recovery never creates an automatic `-r2` follow-up.
A replacement needs a new approved operation. `doctor` shows unresolved operations.

## Table maintenance

`rgdesk maintain` (or the desk's scheduled loop) compacts small files, expires snapshots while retaining
`min_snapshots` and `snapshot_retention_days`, and deletes only `.parquet` files that no remaining snapshot references
and that are older than `orphan_retention_hours`. It runs in-process; no Athena job or Spark cluster is required.
`--dry-run` reports what would happen.

## Validation evidence

`tests/test_storage_live.py` exercises the local profile on disk: committed scan and decision survive deleting the
cache; an uncommitted scan is reported for re-collection; a commit without acknowledgement is not duplicated;
maintenance during commits keeps rows; an unreachable store is `blocked`; health carries every contract field. The
optional AWS-profile run is skipped unless `RGTRIAGE_AWS_STORAGE_TEST=1` and a disposable Glue database and warehouse
are configured. A local-profile pass is not a claim about AWS durability or cost.

## Fresh-install detection

If the desk finds a v0.4 `latest.json` or `decisions.json` on a fresh cache, it stops with instructions to move or
delete the old desk state. It does not import it. Keep the v0.4 tag until you have exported what you need; see
[UPGRADING.md](UPGRADING.md).