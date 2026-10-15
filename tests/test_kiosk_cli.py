"""kiosk.py offline: scaffolding from kits, naming, bundle file selection (no AWS)."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "profiles/builder/skills/kiosk/lambda-kiosk/scripts/kiosk.py"
spec = importlib.util.spec_from_file_location("kiosk", SCRIPT)
kiosk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kiosk)


@pytest.mark.parametrize("kit", ["hello", "processor", "python-blank"])
def test_new_scaffolds_every_kit(tmp_path, kit):
    class A: name, kit_, dir = "demo-fn", kit, str(tmp_path / "f")
    a = A(); a.kit = kit
    kiosk.cmd_new(a)
    m = json.loads((tmp_path / "f" / "manifest.json").read_text())
    assert m["name"] == "demo-fn" and m["kit"] == kit and m["version"] == "0.1.0"
    assert "{{name}}" not in "".join(p.read_text() for p in (tmp_path / "f").rglob("*") if p.is_file())


def test_read_dir_skips_caches(tmp_path):
    (tmp_path / "handler.py").write_text("x")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "h.pyc").write_bytes(b"x")
    (tmp_path / ".junit.xml").write_text("x")
    assert list(kiosk.read_dir(tmp_path)) == ["handler.py"]


def test_snake_case_matches_boto3():
    assert kiosk.snake("DescribeSecurityGroups") == "describe_security_groups"
    assert kiosk.snake("GetBucketACL") == "get_bucket_acl"
    assert kiosk.snake("ListMFADevices") == "list_mfa_devices"
