---
name: lambda-kiosk
description: "Build, test, deploy, promote, run and reuse AWS Lambda functions through the lambda kiosk, with the full lifecycle in one `kiosk` command. Use whenever a task needs compute: a new function, a change to one, running one over inputs, or fixing one that fails."
license: proprietary
metadata:
  owner: remedigenius
  version: 0.1.0
---

# lambda-kiosk

You get compute by vending small Lambda functions from the kiosk. You write the code and tests; the
kiosk's **gate** checks, tests (in an offline sandbox), signs and deploys them; you promote and run
them. You never call Lambda, IAM or S3 write APIs yourself: your role cannot, and must not try.

The command (alias it once per shell):
```bash
K="python3 /opt/data/profiles/builder/skills/kiosk/lambda-kiosk/scripts/kiosk.py"
```
`kiosk.py` finds the pinned boto3/botocore by itself. Never install SDKs or create virtualenvs for it.
If your shell blocks the alias, call the full command each time.

## The lifecycle (follow it in order)

1. **Reuse first.** `$K search <words>`, then `$K show <name>`. If a live function does the job, run it
   (step 7). Build only when nothing fits.
2. **Scaffold.** `$K new <name> --kit hello|processor|python-blank`. It lands in `/opt/data/work/kiosk/<name>/`.
   Pick `processor` when you need to write output files; `hello`/`python-blank` (class `isolated`) when you
   only compute and return a summary.
3. **Write the code.** `handler.py` defines `handle(unit, ctx)` and returns
   `{"status": "SUCCEEDED"|"PARTIAL"|"FAILED", "summary": {...small...}, "reason": "..."}`. Read
   `references/contract.md`. Need an AWS API? Look it up offline at the pinned SDK version:
   `$K sdk <service>` and `$K sdk <service> <Operation> --depth 2`. (Classes in this kiosk have no AWS
   access beyond their own outputs; reading AWS accounts arrives with the `reader` class later.)
4. **Write the tests** in `tests/test_*.py` with `kiosk_runtime.testing.run(handler.handle, unit)`. Cover the
   happy path, bad input and the deadline (`remaining_s=1`). No network: stub AWS with `botocore.stub.Stubber`.
5. **Test locally until PASS.** `$K test /opt/data/work/kiosk/<name>`: the gate's static checks plus your
   tests, with the same pinned layers the gate uses. Fix and repeat. This costs nothing; submissions are capped.
6. **Submit.** `$K submit /opt/data/work/kiosk/<name>`. Verdict `PASS` = deployed, alias `dev`.
   Verdict `FAIL` = read `code`, `problems[].fix`, or `tail`, fix, run `$K test` again, then resubmit.
   A version that passed is immutable: bump `version` in `manifest.json` for any change.
7. **Promote.** `$K promote <name> <version>`: the kiosk runs your `canary_input` on alias `canary`; if it
   returns SUCCEEDED, the version goes `live` (policy auto). If the canary fails, live stays on the old version.
8. **Run.** `$K run <name> --item '{"...": ...}'` or `--items units.json [--concurrency N]`. Read the
   receipt (status per unit, outputs). `$K outputs <name> <run_id> --cat` prints what it wrote.
9. **Report** in plain words: name, version, gate result (tests passed), canary result, run status, output
   keys. Status words only: PASS/FAIL for checks, SUCCEEDED/PARTIAL/FAILED for runs.

## When something fails: heal within the limits

Read `references/healing.md`. In short:
- Fix from the evidence: `problems[].fix`, the test `tail`, `$K logs <name>`. Never guess twice the same way.
- **Limits are enforced by the kiosk, not by you:** 3 submissions per version per day, 20 per day in total,
  10 promotions, 200 runs. A refusal with code `CAP_*` means **stop**: write what failed, what you tried and
  what you would try next, and hand it to the owner. Never bump a version just to get around a cap.
- `PLATFORM_ERROR` (exit code 2) is the kiosk's fault, not yours: stop and report; the admin is alerted.
- `FROZEN` means the admin froze the kiosk: stop.
- A live version whose first runs fail is rolled back automatically. Say so in your report.

## References
- `references/contract.md`: `handle(unit, ctx)`, the envelope, ctx methods, manifest fields, classes.
- `references/refusals.md`: every gate refusal code and how to fix it.
- `references/healing.md`: retry limits, escalation, what never to do.
- `references/patterns.md`: fan-out, splitting work, deadlines and checkpoints, idempotent outputs.
- Sibling skills for Lambda knowledge: `aws-serverless`, `aws-sdk-python-usage`, `debugging-lambda-timeouts`,
  `securing-serverless-functions` (their advice on deploy tools such as SAM/CDK does not apply: the kiosk deploys).
