"""Lambda entry point for every kiosk function: Handler = kiosk_runtime.entry.main.

Event shape: {"kiosk": {"run_id": "...", "unit_index": 0}, "unit": {...}}. A bare event is treated as the unit.
Always returns an envelope; a crash in `handle` becomes status FAILED with the error, never an
unhandled exception (so one bad unit never hides the others in a fan-out).
"""
import importlib
import json
import time

from . import STATUSES
from .ctx import Ctx, redact

SUMMARY_MAX = 4096
_handler = None


def execute(handle, unit, ctx):
    started = time.time()
    try:
        out = handle(unit, ctx)
        if not isinstance(out, dict) or out.get("status") not in STATUSES:
            env = {"status": "FAILED", "summary": {},
                   "error": "handle() must return a dict with status SUCCEEDED, PARTIAL or FAILED"}
        else:
            env = {"status": out["status"], "summary": out.get("summary", {})}
            if out.get("reason"):
                env["reason"] = redact(out["reason"])[:500]
            try:
                size = len(json.dumps(env["summary"], default=str))
            except (TypeError, ValueError):
                size, env["summary"] = 0, {"note": "summary was not JSON-serialisable"}
            if size > SUMMARY_MAX:
                env["summary"] = {"truncated": True, "note": "summary over 4 KB; write details with ctx.write_json"}
    except Exception as e:  # noqa: BLE001 - every failure becomes an envelope
        ctx.log("handle failed", error=type(e).__name__, detail=str(e)[:500])
        env = {"status": "FAILED", "summary": {}, "error": redact(f"{type(e).__name__}: {e}")[:500]}
    env.update(outputs=list(ctx.outputs), duration_ms=int((time.time() - started) * 1000),
               run_id=ctx.run_id, version=ctx.version)
    return env


def main(event, context):
    global _handler
    if _handler is None:
        _handler = importlib.import_module("handler")
    event = event if isinstance(event, dict) else {"value": event}
    k = event.get("kiosk") or {}
    run_id = k.get("run_id", "adhoc")
    index = k.get("unit_index", 0)
    index = index if isinstance(index, int) and not isinstance(index, bool) and index >= 0 else 0
    unit = event["unit"] if "unit" in event else event
    return execute(_handler.handle, unit, Ctx.from_lambda(context, run_id, index))
