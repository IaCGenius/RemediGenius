# The function contract

## handler.py

```python
def handle(unit, ctx):
    ...
    return {"status": "SUCCEEDED", "summary": {"count": 3}}
```

- `unit`: one JSON work order (the `--item`, one element of `--items`, or `canary_input`). May be `None` or
  missing keys: validate it and return FAILED with a `reason` instead of crashing.
- Return a dict with `status` = `SUCCEEDED` (all done), `PARTIAL` (some done; say why in `reason`) or
  `FAILED` (nothing useful; say why). Anything else becomes FAILED.
- `summary`: small JSON (under 4 KB). Put real data in outputs.
- A crash (exception) is caught and becomes FAILED with the error text. Still: handle expected errors yourself.

## ctx

| Method | Does |
|---|---|
| `ctx.write_json(name, obj)` / `ctx.write_text(name, text)` | write `outputs/<agent>/<function>/<run_id>/<unit_index>/<name>` (class `processor` only; each unit of a run has its own folder, the canary is unit 0); returns the key |
| `ctx.read_json(key)` | read an earlier output of yours (`outputs/<agent>/...`) |
| `ctx.remaining_s()` / `ctx.should_stop(margin_s=30)` | time left; stop and return PARTIAL before the timeout |
| `ctx.log(msg, **fields)` | JSON log line; secrets are redacted; read with `kiosk logs` |
| `ctx.aws(service)` | boto3 client with adaptive retries; rights come only from the function's class |
| `ctx.run_id`, `ctx.unit_index`, `ctx.version`, `ctx.function`, `ctx.agent` | where you are |

## manifest.json

| Field | Rule |
|---|---|
| `name` | 3–40 chars, lowercase, digits, dashes; same as the folder you submit |
| `version` | MAJOR.MINOR.PATCH; immutable once it passed the gate |
| `description` | one sentence (search finds functions by it) |
| `kit` | the kit you started from |
| `class` | `isolated` (no AWS access) or `processor` (own outputs prefix) |
| `compute` | `lambda` |
| `memory_mb` / `timeout_s` / `concurrency` | integers within the kiosk limits (1024 MB, 900 s, 5) |
| `canary_input` | a small, real unit; the canary must return SUCCEEDED with it |
| `env` | optional, up to 10 string values; no AWS_/KIOSK_ keys; never secrets |
| `tags` | optional, free-form (e.g. `{"mission": "A1"}`) |

## Bundle rules (checked by `kiosk test` and the gate)

- Files: `.py`, `.json`, `.md`, `.txt` only; `handler.py` at the root; tests in `tests/test_*.py`.
- Only the standard library, `boto3`/`botocore` (pinned in the runtime layer) and `kiosk_runtime`.
  No other packages.
- Forbidden: `subprocess`, `socket`, `ctypes`, `multiprocessing`, `eval`, `exec`, `compile`, `__import__`,
  `os.system`, `os.popen`, `os.exec*`, `os.spawn*`.
- At least one test; a new version may not have fewer tests than the last passing one.
- Max 1 MB zipped.

## Where it runs

Python 3.13 on Lambda (x86_64), handler `kiosk_runtime.entry.main`, your code in `/var/task`.
Your local `kiosk test` uses the very same runtime and test layers, downloaded from the kiosk.
