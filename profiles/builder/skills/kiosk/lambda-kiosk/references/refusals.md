# Gate refusals and how to fix them

A refusal is `{"verdict": "FAIL", "code": ..., "message": ..., "problems": [{code, file, message, fix}], "tail": ...}`.
Always run `kiosk test` before resubmitting: it runs the same checks for free.

| Code | Meaning | Fix |
|---|---|---|
| `STATIC_CHECKS` | one or more `problems` below | fix each, `kiosk test`, resubmit |
| `MANIFEST_MISSING`, `MANIFEST_INVALID_JSON`, `MANIFEST_FIELD_MISSING` | manifest absent or broken | copy the field layout from the kit |
| `NAME_INVALID`, `VERSION_INVALID`, `NAME_MISMATCH` | naming | lowercase-dash name; semver; submit from the function's folder |
| `KIT_UNKNOWN`, `CLASS_NOT_ALLOWED`, `COMPUTE_NOT_ENABLED` | not available to you | use a listed kit/class; `lambda` only. A new class needs the owner: stop and ask |
| `LIMIT_EXCEEDED` | memory, timeout or concurrency over the limit | lower it; split the work (patterns.md) |
| `ENV_INVALID`, `SECRET_IN_ENV` | bad env | fix keys; never put secrets in a function |
| `FILE_TYPE_NOT_ALLOWED`, `ENCODING` | binary or odd files | remove them; UTF-8 text only |
| `SYNTAX_ERROR` | Python does not parse | fix the line shown |
| `FORBIDDEN_IMPORT`, `FORBIDDEN_CALL` | process, socket or dynamic-code use | remove; there is no exception process |
| `HANDLER_MISSING`, `HANDLE_FUNCTION_MISSING` | no `handle(unit, ctx)` at the top of `handler.py` | add it |
| `TESTS_MISSING`, `TESTS_REDUCED` | no tests, or fewer than before | add tests; never delete tests to pass |
| `TESTS_FAILED` | tests failed in the sandbox | read `tail`; fix code or test; it passed locally? check for network calls (sandbox has none) or time-dependent tests |
| `SANDBOX_ERROR` | tests crashed the sandbox (timeout, memory, import-time work) | keep tests fast, offline, no work at import time |
| `VERSION_EXISTS` | that version already passed | bump `version` |
| `BUNDLE_INVALID`, `BUNDLE_KEY_INVALID` | not built by `kiosk submit` | always use `kiosk submit DIR` |
| `CAP_VERSION_SUBMISSIONS`, `CAP_AGENT_SUBMISSIONS`, `CAP_PROMOTIONS`, `CAP_RUNS` | daily limit reached | **stop**; report to the owner (healing.md) |
| `FROZEN` | the admin froze the kiosk | stop; report |
| `CANARY_FAILED` | canary did not return SUCCEEDED; live unchanged | `kiosk logs NAME`; reproduce with `canary_input` in a test; fix; new version |
| `CANARY_REQUIRED`, `NOT_GATED`, `ALIAS_NOT_SET`, `UNKNOWN_FUNCTION`, `RETIRED` | wrong order | follow the lifecycle in SKILL.md |
| `ITEMS_INVALID`, `ITEM_TOO_LARGE` | run input | 1–100 units, each under 64 KB; pass keys to outputs instead of data |
| `PLATFORM_ERROR` (exit 2) | the kiosk itself failed | stop; the admin was alerted |
