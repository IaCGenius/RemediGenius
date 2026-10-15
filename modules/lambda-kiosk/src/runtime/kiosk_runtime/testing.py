"""Helpers for a function's tests (they run in the gate's sandbox and in `kiosk test`).

    from kiosk_runtime.testing import run, run_with_ctx
    import handler

    def test_ok():
        env = run(handler.handle, {"who": "ann"})
        assert env["status"] == "SUCCEEDED"

`run` returns exactly the envelope Lambda would return. Outputs go to memory, not S3:
`env, ctx = run_with_ctx(...)`, then `ctx.writer.files` holds key -> bytes.
No network in the sandbox: stub AWS calls with botocore.stub.Stubber.
"""
import json
import time

from .ctx import Ctx, MemoryWriter
from .entry import execute


def make_ctx(remaining_s=60, run_id="test", agent="test", function="fn", version="0.0.0"):
    writer = MemoryWriter(prefix=f"outputs/{agent}/{function}/{run_id}/")
    return Ctx(writer, time.time() + remaining_s, run_id, agent, function, version)


def run_with_ctx(handle, unit, **kw):
    ctx = make_ctx(**kw)
    return execute(handle, unit, ctx), ctx


def run(handle, unit, **kw):
    return run_with_ctx(handle, unit, **kw)[0]


def output_json(ctx, name):
    """The JSON a function wrote with ctx.write_json(name, ...)."""
    return json.loads(ctx.writer.files[ctx.writer.prefix + name])
