# Patterns

**One unit, one job.** A unit is a small work order (a record batch, a region, a date). The run state
machine fans units out in parallel (`--concurrency`, capped by the manifest and the kiosk). One failing
unit never stops the others; the receipt shows each.

**Split before you scale up.** A function near its timeout or memory limit is a design smell: split the
input into more units (by id range, by region, by date) rather than asking for more memory or time.
The kiosk caps memory at 1024 MB and time at 900 s.

**Deadlines.** Check `ctx.should_stop()` in loops. When it is true, write what you have
(`ctx.write_json("partial.json", ...)`) and return `PARTIAL` with `reason: "deadline"` and where to
resume (e.g. `summary.next_offset`). The caller runs a follow-up unit with that offset.

**Idempotent outputs.** Name outputs by content (`result.json`, `region-us-east-1.json`), not by time.
A re-run of the same unit then overwrites, never duplicates.

**Small summaries.** The summary travels through Step Functions (limit 256 KB for the whole run):
counts and keys only. Data goes to outputs.

**Inputs by reference.** A unit over 64 KB is refused. Write large inputs as outputs of a previous run
and pass the key; read it with `ctx.read_json(key)`.

**AWS calls (when a class allows them).** Use `ctx.aws(service)` (adaptive retries). Use paginators
(`client.get_paginator(op)`; `kiosk sdk <service>` marks paginated operations with `*`). Catch
`botocore.exceptions.ClientError` and read `e.response["Error"]["Code"]`. Test with `botocore.stub.Stubber`.

**Cold starts.** Do imports and client creation inside `handle` or lazily; do no work at import time
(the sandbox treats import-time crashes as SANDBOX_ERROR).
