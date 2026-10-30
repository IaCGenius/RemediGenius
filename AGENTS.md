# Working in this repository

RemediGenius Community Edition (RemediGenius-CE): an AWS security triage desk built on the Hermes agent. The Python
package is `rgtriage`, the profile is `profiles/remedigenius`, the deployment is Terraform in `deploy/aws-single`, and
release tooling is in `tools/`. Read `docs/ARCHITECTURE.md` and `docs/DATA-FLOW.md` before changing storage behaviour,
and `docs/STORAGE.md` / `docs/SCHEMA.md` before touching table schemas.

These notes are the operational lessons from shipping v0.5.0 (durable S3/Iceberg storage). They describe how work here
actually fails, not how it is supposed to go.

## The workstation you are on

- Windows 11, `cmd.exe`, Python 3.12 on PATH as `python`; repository at `C:\work\remedigenius-community`.
- Docker Desktop with Linux containers is available; `tools/workstation.py` runs the desk locally.
- AWS credentials here are **high privilege**. Treat every call as production: read-only, except on a stack you created
  for a test and will destroy. Never stop, resize or destroy a stack you did not create — the maintainer keeps one.
- The maintainer merges pull requests. Never merge, approve or push to `main`, and never tag a release on your own.
- `.rgce/` is local-only and git-ignored: handoffs, the Spot settings file (account id, subnet, secret ARN), run logs,
  screenshots. Keep it that way; nothing private belongs in a tracked file.

## Commands

| Task | Command |
| --- | --- |
| Unit + local integration tests | `python -m pytest tests -q` (no live AWS; ~624 tests) |
| One test area | `python -m pytest tests/test_iceberg_store.py -q` |
| Synthetic board + IaC match, no AWS/model | `python tools/demo.py` |
| Terraform check | `terraform -chdir=deploy/aws-single validate` |
| Release assets | `python tools/package_release.py --release <version>` |
| Spot release validation | `python tools/spot_release_test.py v<version> --settings .rgce/spot-test-settings.json --local dist/v<version> --name <throwaway-stack>` |

Do not run pytest in parallel processes: the suite writes shared temp state and memory pressure on this box is real.

## Which tier are you in?

| Tier | What runs | Catches | Blind to |
| --- | --- | --- | --- |
| Unit | `pytest`, fakes | logic, contracts, schema shape | everything real |
| Local on-disk Iceberg (`tests/test_storage_live.py`) | real PyIceberg, SQL catalog, folder warehouse | commit/replay/rebuild/maintenance semantics | Glue, S3, containers, threads |
| Docker workstation (`tools/workstation.py`) | real agent + desk containers | wiring, sockets, plugins | instance role, SSM, host separation |
| AWS Spot (`tools/spot_release_test.py`) | Terraform from nothing, real Glue/S3/SSM/Chrome | deployability, IAM boundary, boot race, concurrency | cost/scale, other regions |

A green local suite is **necessary and never evidence of deployability**: v0.5.0 shipped 624 passing tests and still
failed six ways on its first real deployment.

## Rules learned the expensive way

1. **Never provision what Terraform provisioned.** PyIceberg tried `glue:CreateDatabase` on a database Terraform had
   created, and the role correctly denies it. Verify with a read (`GetDatabase`) and create only when it is missing.
   When a permission looks missing, first ask whether the call was necessary.
2. **Assert the value, not the absence of an error.** A harness check "passed" on a `null` snapshot because it only
   looked for an exception. Positive assertions (`"snapshot_id": [0-9]+`, `"outbox_events": 0`) turn a false pass into a
   caught defect. A validation bug is more dangerous than a product bug.
3. **Batch fixes between Spot cycles.** One apply/boot/check/destroy cycle is ~15 minutes. Read the actual exception,
   fix 3–4 related things, then spend the cycle. Guessing one fix per run is how a day disappears.
4. **Normalise SDK objects at the boundary.** boto3 payloads contain `datetime`, `Decimal` and page objects that are not
   JSON. Convert once (`contracts.jsonable`) at every store/write boundary, not at each call site.
5. **Iceberg schemas round-trip with renumbered field IDs.** Compare structurally (`schema_problems`) and build Arrow
   tables from the *loaded* table schema, otherwise appends fail with `Mismatch in fields`.
6. **Know which Iceberg file set you asked for.** `data_files()` is the current snapshot; `all_data_files()` is all
   history. `dynamic_partition_overwrite` adds files — replace with `overwrite(..., overwrite_filter=AlwaysTrue())`.
7. **PyArrow nested structs with maps need column-wise construction.** `Table.from_pylist` fails on OCSF resource
   structures; build per column.
8. **A SQLite connection is not shareable across threads** without `check_same_thread=False` plus a lock around every
   transaction and read. Single-threaded tests will never show it; collection workers will.
9. **Idempotency belongs in the design.** Batch ids and content hashes in snapshot summaries make a lost acknowledgement
   non-duplicating. Retrofitting that after the fact is far more expensive than adding it first.
10. **State the limits of what you proved.** `docs/RELEASE-VALIDATION.md` records what was not tested as carefully as
    what was; keep that honesty when you add a row.

## Platform differences that have already cost time

- **Windows paths:** `file:///C:/...` warehouse URIs break PyArrow (`WinError 123`). Use plain filesystem paths in local
  tests; `s3://` on AWS.
- **Line endings and locks:** the repository is LF (`* text=auto eol=lf`); the controller lock is `msvcrt` on Windows and
  `fcntl` elsewhere — exercise both paths when you touch it.
- **Archive determinism:** the spot and source zips are byte-stable per commit, but the source zip embeds the commit and
  the wheel carries pip timestamps, so a rebuild legitimately changes digests. Verify against the `SHA256SUMS` inside
  the release, never against a fresh local build.
- **Implementation versions are pinned for a reason:** OCSF 1.9.0, PyIceberg 0.12.0, PyArrow 19.0.1. Changing a pin is a
  release decision with a Spot run behind it, not a maintenance edit.

## Secrets and publication

- Keys only via Secrets Manager or environment; never in `tfvars`, logs, commits or chat. The model key and the GitHub
  App key follow this rule; the dashboard login is read into memory only.
- Redact 12-digit account ids, role names and bucket names from anything public. `tools/spot_release_test.py` already
  masks them — keep new tooling at the same standard.
- Release archives are allow-lists: source zip is exactly `git ls-files`, spot zip is `SPOT_PARTS` in
  `tools/package_release.py`, wheel is the package. Nothing private publishes unless it was committed first.
- Before publishing, scan the tracked tree and the built archives for credentials, account ids and local state, and
  report per control with the concrete result.

## Pointers

- `docs/TESTING.md` — how to run each tier, bake the image and gate a release, and the invariants they hold.
- `docs/RELEASE-VALIDATION.md` — what each release proved and did not prove.
- `docs/IAM.md` — instance role, scoped Glue grant, why the denies exist.
- `docs/RECOVERY.md`, `docs/UPGRADING.md` — fresh-install behaviour and the refused v0.4 state.
- `docs/LIMITS.md` — known bounds, including what the desk deliberately does not do.