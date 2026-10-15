from kiosk_runtime.testing import run

import handler


def test_returns_a_status():
    assert run(handler.handle, {})["status"] in ("SUCCEEDED", "PARTIAL", "FAILED")
