from kiosk_runtime.testing import output_json, run, run_with_ctx

import handler


def test_processes_and_writes_output():
    env, ctx = run_with_ctx(handler.handle, {"records": [{"id": "a", "value": 1}, {"id": "b", "value": 3}]})
    assert env["status"] == "SUCCEEDED"
    assert env["summary"] == {"processed": 2, "invalid": 0, "total": 4}
    assert output_json(ctx, "result.json")["total"] == 4


def test_invalid_records_make_partial():
    env = run(handler.handle, {"records": [{"id": "a", "value": 1}, {"id": "x"}]})
    assert env["status"] == "PARTIAL" and env["summary"]["invalid"] == 1


def test_bad_unit_fails_cleanly():
    assert run(handler.handle, {"records": "nope"})["status"] == "FAILED"


def test_deadline_returns_partial():
    env = run(handler.handle, {"records": [{"id": "a", "value": 1}]}, remaining_s=1)
    assert env["status"] == "PARTIAL"
