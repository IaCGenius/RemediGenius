# Healing: fix what you can, stop where the limits say

## The loop

1. Read the evidence first: the refusal `code` and `problems[].fix`, the sandbox `tail`, the canary
   `envelope`, `kiosk logs NAME`, the run receipt. Quote the line that matters in your notes.
2. Reproduce it locally with a test (`kiosk test`). A failure you cannot reproduce locally is usually a
   network call (the sandbox has none), a time-dependent test, or a size or limit problem.
3. Change one thing, re-run `kiosk test`, then resubmit with a new version if the old one passed.
4. If the same fix fails twice, do not try it a third time. Change approach or escalate.

## Limits (the kiosk counts them; you cannot raise them)

| Limit | Per day (UTC) |
|---|---|
| submissions of one version | 3 |
| submissions in total | 20 |
| promotions | 10 |
| runs | 200 |

Local `kiosk test` runs are free and unlimited: use them instead of submissions.

## Stop and hand over to the owner when

- any `CAP_*` refusal, `FROZEN`, or `PLATFORM_ERROR`;
- a refusal needs something you are not allowed (`CLASS_NOT_ALLOWED`, `COMPUTE_NOT_ENABLED`, higher limits);
- two different fixes for the same failure did not work.

Hand-over note (keep it short): function and version; what you were trying to do; the last refusal or error
(code, one line of evidence); what you tried; what you would try next; what you need from the owner.

## Never

- Bump a version only to get around a submission cap.
- Delete or weaken tests to get through the gate.
- Promote past a failed canary, or try to call Lambda, IAM or S3 write APIs directly.
- Put secrets, credentials or client data in code, tests, env, logs or memory.
- Print the contents of `/opt/data/kiosk/*/credentials`.
