"""Tests never reach real AWS: no credentials from the machine, and account discovery is off unless a test calls it."""
import pytest

from rgtriage import accounts


@pytest.fixture(autouse=True)
def offline_aws(monkeypatch, tmp_path):
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-aws-credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setattr(accounts, "discover", lambda profile, previous=None, probe=None: {
        "mode": "standalone", "admin": {}, "full_read": [], "findings_only": [], "not_covered": [], "notes": []})
