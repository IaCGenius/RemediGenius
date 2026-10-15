"""Offline tests: rules, runtime contract, sandbox, gate logic (botocore Stubber, no AWS calls).

    cd infra/modules/lambda-kiosk && python -m pytest -q tests
"""
import base64
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE / "src" / "runtime"), str(HERE / "src" / "gate"), str(HERE / "src" / "sandbox")]
os.environ.update(KIOSK_BUCKET="kb", KIOSK_CONFIG_PARAM="/kiosk/t/config", KIOSK_FROZEN_PARAM="/kiosk/t/frozen",
                  KIOSK_SANDBOX_FN="sbx", KIOSK_SIGNING_PROFILE="p", AWS_DEFAULT_REGION="us-east-1",
                  AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x")

from kiosk_runtime import rules  # noqa: E402
from kiosk_runtime.testing import output_json, run, run_with_ctx  # noqa: E402

LIMITS = {"bundle_bytes": 1048576, "memory_mb": 1024, "timeout_s": 900, "concurrency": 5,
          "submissions_per_version_per_day": 3, "submissions_per_agent_per_day": 20,
          "promotions_per_agent_per_day": 10, "runs_per_agent_per_day": 200, "items_per_run": 100,
          "item_bytes": 65536}
MANIFEST = {"name": "word-stats", "version": "0.1.0", "description": "Counts words.", "kit": "processor",
            "class": "processor", "compute": "lambda", "memory_mb": 256, "timeout_s": 30, "concurrency": 2,
            "canary_input": {"text": "a b"}}
HANDLER = b"def handle(unit, ctx):\n    return {'status': 'SUCCEEDED', 'summary': {'n': len(unit.get('text','').split())}}\n"
TEST = (b"from kiosk_runtime.testing import run\nimport handler\n\n"
        b"def test_counts():\n    assert run(handler.handle, {'text': 'a b c'})['summary']['n'] == 3\n")


def bundle(**over):
    files = {"manifest.json": json.dumps({**MANIFEST, **over.pop("manifest", {})}).encode(),
             "handler.py": HANDLER, "tests/test_handler.py": TEST}
    files.update(over.pop("files", {}))
    for k in over.pop("drop", []):
        files.pop(k)
    return files


def check(files, prev=0):
    return rules.check_bundle(files, LIMITS, ["hello", "processor"], ["isolated", "processor"], prev)


# ------------------------------------------------------------------ rules
def test_good_bundle_passes():
    m, rep, probs = check(bundle())
    assert probs == [] and rep["test_count"] == 1 and m["name"] == "word-stats"


@pytest.mark.parametrize("over,code", [
    ({"manifest": {"memory_mb": 4096}}, "LIMIT_EXCEEDED"),
    ({"manifest": {"class": "reader"}}, "CLASS_NOT_ALLOWED"),
    ({"manifest": {"compute": "task"}}, "COMPUTE_NOT_ENABLED"),
    ({"manifest": {"version": "1.0"}}, "VERSION_INVALID"),
    ({"manifest": {"name": "Bad_Name"}}, "NAME_INVALID"),
    ({"manifest": {"env": {"AWS_REGION": "x"}}}, "ENV_INVALID"),
    ({"manifest": {"env": {"K": "AKIA" + "ABCDEFGHIJKLMNOP"}}}, "SECRET_IN_ENV"),
    ({"files": {"handler.py": b"import subprocess\ndef handle(unit, ctx):\n    return {}\n"}}, "FORBIDDEN_IMPORT"),
    ({"files": {"handler.py": b"def handle(unit, ctx):\n    return eval('1')\n"}}, "FORBIDDEN_CALL"),
    ({"files": {"handler.py": b"import os\ndef handle(unit, ctx):\n    os.system('x')\n"}}, "FORBIDDEN_CALL"),
    ({"files": {"handler.py": b"def run(unit):\n    pass\n"}}, "HANDLE_FUNCTION_MISSING"),
    ({"files": {"lib.so": b"\x7fELF"}}, "FILE_TYPE_NOT_ALLOWED"),
    ({"drop": ["tests/test_handler.py"]}, "TESTS_MISSING"),
    ({"drop": ["manifest.json"]}, "MANIFEST_MISSING"),
    ({"files": {"handler.py": b"def handle(unit, ctx)\n"}}, "SYNTAX_ERROR"),
])
def test_rules_refuse(over, code):
    _, _, probs = check(bundle(**over))
    assert code in {p["code"] for p in probs}
    assert all(p["fix"] for p in probs)


def test_tests_cannot_shrink():
    _, _, probs = check(bundle(), prev=3)
    assert "TESTS_REDUCED" in {p["code"] for p in probs}


def test_zip_is_deterministic_and_safe():
    a, b = rules.make_zip(bundle()), rules.make_zip(dict(reversed(list(bundle().items()))))
    assert a == b and rules.read_zip(a, 10**6).keys() == bundle().keys()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.py", "x")
    with pytest.raises(ValueError):
        rules.read_zip(buf.getvalue(), 10**6)
    with pytest.raises(ValueError):
        rules.read_zip(a, 10)


# ------------------------------------------------------------------ runtime contract
def test_envelope_success_outputs_and_redaction(capsys):
    def handle(unit, ctx):
        ctx.log("key AKIA" + "ABCDEFGHIJKLMNOP seen")
        ctx.write_json("r.json", {"x": 1})
        return {"status": "SUCCEEDED", "summary": {"ok": True}}
    env, ctx = run_with_ctx(handle, {})
    assert env["status"] == "SUCCEEDED" and env["outputs"] == ["outputs/test/fn/test/r.json"]
    assert output_json(ctx, "r.json") == {"x": 1}
    assert "AKIA" not in capsys.readouterr().out


@pytest.mark.parametrize("ret,status", [(None, "FAILED"), ({"status": "DONE"}, "FAILED"),
                                        ({"status": "PARTIAL", "reason": "time"}, "PARTIAL")])
def test_envelope_status_contract(ret, status):
    assert run(lambda u, c: ret, {})["status"] == status


def test_crash_becomes_failed_envelope():
    env = run(lambda u, c: 1 / 0, {})
    assert env["status"] == "FAILED" and "ZeroDivisionError" in env["error"]


def test_big_summary_truncated_and_read_scope():
    assert run(lambda u, c: {"status": "SUCCEEDED", "summary": {"x": "y" * 5000}}, {})["summary"]["truncated"]
    _, ctx = run_with_ctx(lambda u, c: {"status": "SUCCEEDED"}, {})
    with pytest.raises(PermissionError):
        ctx.read_json("outputs/other-agent/x.json")



def test_units_of_one_run_get_their_own_output_prefix(monkeypatch):
    from kiosk_runtime import entry
    from kiosk_runtime.ctx import Ctx
    monkeypatch.setenv("KIOSK_AGENT", "builder")
    monkeypatch.setenv("KIOSK_FUNCTION", "word-stats")
    seen = []
    monkeypatch.setattr(entry, "_handler", type("H", (), {"handle": staticmethod(
        lambda u, c: seen.append(c.writer.prefix) or {"status": "SUCCEEDED"})}))
    lam = type("L", (), {"get_remaining_time_in_millis": lambda self: 60000})()
    for i in (0, 1, True, -2):
        entry.main({"kiosk": {"run_id": "r1", "unit_index": i}, "unit": {}}, lam)
    entry.main({"unit": {}}, lam)
    assert seen == ["outputs/builder/word-stats/r1/0/", "outputs/builder/word-stats/r1/1/",
                    "outputs/builder/word-stats/r1/0/", "outputs/builder/word-stats/r1/0/",
                    "outputs/builder/word-stats/adhoc/0/"]
    assert Ctx.from_lambda(lam, "r2", 3).unit_index == 3

# ------------------------------------------------------------------ sandbox (runs pytest in-process)
def test_sandbox_runs_bundle_tests(tmp_path, monkeypatch):
    import sandbox
    monkeypatch.setattr(sandbox.tempfile, "mkdtemp", lambda dir=None: str(tmp_path / "w"))
    (tmp_path / "w").mkdir()
    ok = sandbox.main({"bundle_b64": base64.b64encode(rules.make_zip(bundle())).decode()}, None)
    assert ok["passed"] == 1 and ok["failed"] == 0, ok["tail"]
    (tmp_path / "w").mkdir()
    bad = bundle(files={"tests/test_handler.py": TEST.replace(b"== 3", b"== 4")})
    out = sandbox.main({"bundle_b64": base64.b64encode(rules.make_zip(bad)).decode()}, None)
    assert out["failed"] == 1
    assert os.environ.get("AWS_ENDPOINT_URL") is None  # environment restored


# ------------------------------------------------------------------ gate (Stubber)
@pytest.fixture
def gate(monkeypatch):
    import gate as g
    from botocore.stub import Stubber
    import boto3
    g._cfg = {"name": "t", "function_prefix": "kiosk-t-fn-", "limits": LIMITS, "kits": ["processor"],
              "compute": ["lambda"], "agents": {"builder": {"classes": ["processor"], "policy": "auto"}}}
    s3, ssm = boto3.client("s3"), boto3.client("ssm")
    g._c.clear()
    g._c.update(s3=s3, ssm=ssm)
    st = {"s3": Stubber(s3), "ssm": Stubber(ssm)}
    for s in st.values():
        s.activate()
    yield g, st


def test_gate_refuses_frozen(gate):
    g, st = gate
    st["ssm"].add_response("get_parameter", {"Parameter": {"Value": "true"}}, {"Name": "/kiosk/t/frozen"})
    with pytest.raises(g.Refused) as e:
        g.validate({"bundle_key": "incoming/builder/word-stats/0.1.0/bundle.zip"})
    assert json.loads(str(e.value))["code"] == "FROZEN"


def test_gate_refuses_unknown_agent_and_bad_key(gate):
    g, _ = gate
    for key, code in (("incoming/mallory/x-y/0.1.0/bundle.zip", "AGENT_UNKNOWN"), ("elsewhere/x.zip", "BUNDLE_KEY_INVALID")):
        with pytest.raises(g.Refused) as e:
            g.validate({"bundle_key": key})
        assert json.loads(str(e.value))["code"] == code


def test_gate_counts_caps_per_version(gate):
    g, st = gate
    keys = [{"Key": f"events/d/builder/1_submit_word-stats_0.1.0.json"}] * 3 + [{"Key": "events/d/builder/2_run_x_1.0.0.json"}]
    st["s3"].add_response("list_objects_v2", {"Contents": keys, "IsTruncated": False})
    assert g.count_events("builder", "submit", "word-stats", "0.1.0") == 3


def test_refuse_action_parses_step_functions_cause(gate):
    g, st = gate
    st["s3"].add_response("get_object", {"Body": io.BytesIO(b'{"name":"word-stats","agent":"builder","function":"f","state":"new","versions":{},"aliases":{},"live_history":[],"runs":{"count":0,"failed":0}}')})
    st["s3"].add_response("put_object", {})
    st["s3"].add_response("put_object", {})
    cause = json.dumps({"errorType": "Refused", "errorMessage": json.dumps({"code": "TESTS_FAILED", "message": "m"})})
    v = g.refuse_action({"bundle_key": "incoming/builder/word-stats/0.1.0/bundle.zip",
                         "error": {"Error": "Refused", "Cause": cause}})
    assert v["verdict"] == "FAIL" and v["code"] == "TESTS_FAILED" and v["version"] == "0.1.0"
