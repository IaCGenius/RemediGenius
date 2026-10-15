"""Kiosk sandbox: runs a bundle's tests and nothing else.

Runs in a subnet with no route out, with a role that has no AWS rights. On top of that, AWS
credentials are replaced with dummies and every AWS endpoint points at a closed local port, so a
test that forgets to stub an AWS call fails at once instead of hanging.
Input: {"bundle_b64": "...", "agent": "...", "name": "...", "version": "..."}.
"""
import base64
import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

from kiosk_runtime import rules

DUMMY_ENV = {
    "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "us-east-1", "AWS_REGION": "us-east-1", "AWS_ENDPOINT_URL": "http://127.0.0.1:9",
    "AWS_MAX_ATTEMPTS": "1", "KIOSK_BUCKET": "sandbox-bucket",
}


def main(event, context):
    data = base64.b64decode(event["bundle_b64"])
    files = rules.read_zip(data, 4 * 1024 * 1024)
    work = tempfile.mkdtemp(dir="/tmp")
    saved_env, saved_path, saved_cwd = dict(os.environ), list(sys.path), os.getcwd()
    before = set(sys.modules)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in files:
                z.extract(name, work)
        os.environ.update(DUMMY_ENV)
        os.environ.update(KIOSK_AGENT=event.get("agent", ""), KIOSK_FUNCTION=event.get("name", ""),
                          KIOSK_VERSION=event.get("version", ""))
        sys.path.insert(0, work)
        os.chdir(work)
        import pytest
        out, junit, t0 = io.StringIO(), os.path.join(work, ".junit.xml"), time.time()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = pytest.main(["-q", "-p", "no:cacheprovider", "--junitxml", junit, "tests"])
        counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        if os.path.exists(junit):
            root = ET.parse(junit).getroot()
            for suite in ([root] if root.tag == "testsuite" else root.findall("testsuite")):
                for k in counts:
                    counts[k] += int(suite.get(k, 0))
        failed = counts["failures"]
        passed = counts["tests"] - failed - counts["errors"] - counts["skipped"]
        return {"exit_code": int(code), "passed": passed, "failed": failed, "errors": counts["errors"],
                "skipped": counts["skipped"], "duration_s": round(time.time() - t0, 2),
                "tail": out.getvalue()[-3500:]}
    finally:
        # warm containers are reused: leave nothing of this bundle behind
        os.chdir(saved_cwd)
        sys.path[:] = saved_path
        os.environ.clear()
        os.environ.update(saved_env)
        for mod in set(sys.modules) - before:
            f = getattr(sys.modules.get(mod), "__file__", "") or ""
            if f.startswith(work) or mod in ("handler",) or mod.startswith(("tests", "test_", "conftest")):
                sys.modules.pop(mod, None)
        shutil.rmtree(work, ignore_errors=True)
