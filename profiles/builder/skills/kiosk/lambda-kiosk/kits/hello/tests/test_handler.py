from kiosk_runtime.testing import run

import handler


def test_greets_by_name():
    env = run(handler.handle, {"who": "ann"})
    assert env["status"] == "SUCCEEDED"
    assert env["summary"]["greeting"] == "hello ann"


def test_default_and_empty_unit():
    assert run(handler.handle, {})["summary"]["greeting"] == "hello world"
    assert run(handler.handle, None)["status"] == "SUCCEEDED"
