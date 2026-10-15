# Compute can be replaced; the workspace stays

Two supported storage modes have different promises:

| Mode | Durable authority | If the container is replaced | If its volume is lost |
|---|---|---|---|
| Local, no AWS required | SQLite and original files in a named Docker volume | Reuses the volume | Restore your own backup; no automatic remote copy |
| S3-backed | Immutable-by-application JSON records and original document objects in a dedicated S3 prefix | Rebuilds the local index from S3 | Start with a fresh cache and the same S3 settings |

S3 mode uploads each record before acknowledging a successful save. A failed remote write is an error, not a silently queued success. Knowledge publication follows the same rule. Original document bytes are uploaded before the source record is published. Recovery checks content hashes and restores document originals and extracted Markdown. Investigation exports and review views can be regenerated. Hermes sessions, model credentials, uncommitted agent work and Terraform state are **not** workspace records and are not backed up by this feature.

This is a single-operator, **single active writer per prefix** deployment. Do not run independent consoles or overlapping collectors against the same prefix. There is no distributed publication lock, background replication or multi-tenant access service. Stop the old writer before starting its replacement. Recovery completes before the console accepts requests; unavailable S3 or invalid records prevent startup. The first implementation lists the prefix and rebuilds the index; recovery is limited to 100,000 records and 256MB of record JSON; large organizations should measure startup time before adopting it.

## Docker first run

```sh
docker compose up --build -d
```

Open http://127.0.0.1:8765. Set `RGCE_PORT` to use another host port. The image runs as UID 10001, with a read-only root filesystem, a temporary `/tmp`, no Linux capabilities, and a persistent `/data` volume. The port is published on host loopback only. The app is single-user software, not a public web service. No AWS or model credentials are supplied by the default Compose configuration.

`docker compose down` stops/removes compute and retains the volume. **Do not add `--volumes` if you intend to keep local data.** A Docker volume is persistence on that workstation, not a backup against disk loss. The source Dockerfile and Compose files are included for review. Pi/DeepSeek contributed the initial packaging draft; maintainers reviewed and exercised it.

## S3 mode

Use a private encrypted bucket with public access blocked, TLS enforced, and preferably versioning enabled. Keep one dedicated workspace prefix. `modules/workspace-storage` creates a separate IAM role for an existing bucket: prefix-restricted list/read, conditional create, no delete. It does not create the bucket or enable its protection settings. The test root demonstrates the module; do not deploy the test fixtures as a customer installation.

Supply `RGCE_STORAGE_BUCKET`, `RGCE_STORAGE_PREFIX`, `AWS_DEFAULT_REGION`, and temporary credentials from that storage role (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`) in your current process environment, then:

```sh
docker compose -f compose.yaml -f compose.s3.yaml up --build -d
```

The S3 override uses its own cache volume. It never silently uploads the existing local workspace. Switching an already-bound cache to another bucket/prefix or removing S3 configuration is rejected. To migrate existing data, stop its console and other writers, keep S3 environment configuration unset for the source, and run `rgce --home LOCAL_HOME migrate-s3 --bucket BUCKET --prefix PREFIX --consent` using the restricted storage identity. This copies and verifies records and document originals, retains the source, and refuses a destination containing unrelated records. An interrupted copy can be retried against the same dedicated prefix. Then start S3 mode with a fresh cache. Untracked files and agent sessions are not migrated. Do not put credentials in Git, the image, shared shell scripts or a committed `.env` file. Docker administrators can inspect container environment variables; a container is not protection against a host administrator.

Temporary credentials expire. This Compose option does not refresh injected credentials automatically: obtain a new scoped session and recreate the container. Remote writes fail after expiry. For native Python on an AWS host, standard SDK credential-provider refresh with a dedicated instance/workload role is preferable. `RGCE_STORAGE_PROFILE` selects a dedicated SDK profile when running outside Docker. The storage identity is distinct from the cloud source-read identity and has no remediation rights.

S3 conditional creation protects against accidental overwrites by this role. Hashes detect modified content, not malicious deletion or edits by the bucket administrator. Use versioning, retention and independent backup policies as appropriate. There is no claim of WORM storage or authenticated enterprise approval.

## Agent boundary

Keep Hermes in its own runtime with selected investigation exports and model-provider credentials. It does not need the workspace storage role, source read role, host credentials or Docker socket. The CE console does not become an agent runtime simply because both use containers. Evidence going to a model still needs the user's selected-data/provider consent.

## Acceptance

`tests/live_storage.py --run` tests actual S3 writes and denied IAM operations, then rebuilds records, originals, knowledge variation, reassessment and exports in a fresh Docker tmpfs workspace. No old database is mounted into recovery. Unit tests separately exercise remote failure and corrupt-record behavior; they are not substitutes for the real S3 test.

References: [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html), [Docker Compose service configuration](https://docs.docker.com/reference/compose-file/services/).

## Give the investigation to your agent

In Connections, export the selected assessment and choose **Download investigation ZIP**. Extract it on your workstation, then give Hermes the extracted `START-HERE.md` and investigation skill. This works for local Docker and an SSM-forwarded AWS console; container paths do not need to exist on the workstation. The download verifies the export manifest and rejects modified files. It does not send anything to a model.

The release records the tested Docker image ID and dependency set. Building again from the Dockerfile can resolve newer patch/dependency versions; run acceptance again before treating a rebuild as equivalent to the tested image.

## Recovery failures and operating limits

Use one active writer per workspace prefix. If a durable write has an uncertain outcome, CE refuses subsequent writes: restart with the same S3 configuration so the index is reconstructed before retrying. A rejected local-to-S3 switch leaves the local workspace intact; use the explicit migration command.

Recovery deliberately stops on a missing/corrupt referenced original, invalid record, or unexpected key under `records/`. Do not add folder markers or notes there. Inspect the reported object using a separate administrator identity; restore the known-good version or remove an accidental non-record object after verifying it is not evidence. Do not delete evidence to make startup pass. Keep lifecycle expiry away from active records and originals.

The current recovery limits are 100,000 records, 32MB per record, 256MB total record JSON, and 5MB per original. Startup reads all records and referenced originals; this candidate is intended for bounded workspaces. These are recovery safety limits, not enforced storage quotas: provision separate workspaces before approaching them. There is no supported bypass or large-workspace archival tool yet. If a limit is exceeded, retain S3 and recover through a reviewed export/migration procedure before resuming; do not assume increasing a limit is safe.

Knowledge revisions follow their explicit base-version chain, not wall-clock order. Forked or incomplete chains require operator recovery instead of silently choosing guidance. Document receipts and Markdown views are regenerated after compute replacement.
