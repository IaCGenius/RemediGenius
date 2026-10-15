---
name: debugging-lambda-timeouts
description: "Diagnose a kiosk function that times out or nears its timeout: read its logs and receipts, find the slow step, then split work, add deadline checks or size memory. Use when a run or canary reports a timeout or PARTIAL with reason deadline."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  upstream: aws/agent-toolkit-for-aws@2cb0fa1c2e668e1bb075028800b6b27efb95779e skills/specialized-skills/serverless-skills/debugging-lambda-timeouts
---

# debugging-lambda-timeouts (adapted for the kiosk)

Upstream's procedure, mapped to what you can see and change.

1. **Evidence.** `kiosk show <name>` (timeout_s, memory_mb, canary and run durations), `kiosk receipt <run_id>`
   (`duration_ms` per unit), `kiosk logs <name> --filter "Task timed out"` and `--filter REPORT` (Duration,
   Max Memory Used, Init Duration). You cannot read CloudWatch metrics or other functions.
2. **Classify** (upstream `references/upstream/references/lambda-timeout-debugging.md`): too little time for the
   work, slow downstream call, memory pressure (Max Memory Used close to memory_mb), cold start (Init Duration),
   or a loop without a deadline check.
3. **Fix in the kiosk's terms**, cheapest first:
   - add `ctx.should_stop()` checks and return PARTIAL with a resume point (lambda-kiosk `references/patterns.md`);
   - split units smaller (more units, run with `--concurrency`);
   - raise `memory_mb` (more memory also means more CPU) within the 1024 MB limit;
   - raise `timeout_s` within the 900 s limit.
   Every change is a new version: `kiosk test`, `kiosk submit`, `kiosk promote`.
4. **Report** the cause with the evidence line and the fix.

Upstream's CLI and Logs Insights commands need rights you do not have; use the `kiosk` equivalents above.
