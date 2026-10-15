"""Actual host-broker validation; no Docker, model calls or cloud adapters."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ce_host_broker", ROOT / "deploy/hermes/broker.py")
broker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(broker)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@pytest.fixture
def job(tmp_path):
    folder = tmp_path / ("a" * 32)
    inputs = folder / "input"
    inputs.mkdir(parents=True)
    files = {"query.json": json.dumps({"question": "Explain selected evidence"}), "evidence.md": "Synthetic selected evidence"}
    for name, value in files.items():
        (inputs / name).write_text(value, encoding="utf-8")
    payload = {"job_id": folder.name, "config_digest": "selected-config", "files": {name: digest(value) for name, value in files.items()}}
    (folder / "request.json").write_text(json.dumps(payload), encoding="utf-8")
    yield folder
    # The real validator marks snapshots read-only. Restore disposable test paths.
    for path in tmp_path.rglob("*"):
        if not path.is_symlink():
            os.chmod(path, 0o700 if path.is_dir() else 0o600)


def change_request(job, mutate):
    path = job / "request.json"
    payload = json.loads(path.read_text())
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def symlink(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"Host does not permit test symlinks: {error.__class__.__name__}")


def test_exact_selected_snapshot_accepted(job):
    broker.validate(job, "selected-config")


@pytest.mark.parametrize("target", ["query.json", "evidence.md"])
def test_snapshot_content_tampering_rejected(job, target):
    (job / "input" / target).write_text("Changed after consent", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        broker.validate(job, "selected-config")


def test_extra_unselected_file_rejected(job):
    (job / "input" / "unselected.md").write_text("Unselected context")
    with pytest.raises(ValueError, match="Unexpected snapshot files"):
        broker.validate(job)


def test_missing_selected_file_rejected(job):
    (job / "input" / "evidence.md").unlink()
    with pytest.raises(ValueError, match="Unexpected snapshot files"):
        broker.validate(job)


def test_changed_model_configuration_rejected(job):
    with pytest.raises(ValueError, match="configuration changed"):
        broker.validate(job, "different-provider-config")


def test_job_identity_mismatch_rejected(job):
    change_request(job, lambda payload: payload.update(job_id="b" * 32))
    with pytest.raises(ValueError, match="identity mismatch"):
        broker.validate(job)


@pytest.mark.parametrize("escape", ["../outside.md", "/outside.md", "nested/../../outside.md"])
def test_manifest_path_escape_rejected(job, escape):
    change_request(job, lambda payload: payload["files"].update({escape: digest("outside")}))
    with pytest.raises(ValueError, match="Unexpected snapshot files|path escape"):
        broker.validate(job)


def test_symlink_file_rejected(job, tmp_path):
    target = tmp_path / "outside.md"
    target.write_text("outside")
    symlink(job / "input" / "linked.md", target)
    with pytest.raises(ValueError, match="ordinary files"):
        broker.validate(job)


def test_symlink_input_directory_rejected(job, tmp_path):
    original = job / "input"
    moved = tmp_path / "moved"
    original.rename(moved)
    symlink(original, moved, directory=True)
    with pytest.raises(ValueError, match="Invalid input directory"):
        broker.validate(job)


def test_symlink_job_directory_rejected(job, tmp_path):
    linked = tmp_path / ("b" * 32)
    symlink(linked, job, directory=True)
    with pytest.raises(ValueError, match="Invalid job directory"):
        broker.validate(linked)


def test_symlink_request_rejected(job, tmp_path):
    original = job / "request.json"
    target = tmp_path / "request.json"
    original.rename(target)
    symlink(original, target)
    with pytest.raises(ValueError, match="Invalid request"):
        broker.validate(job)


def test_oversized_request_rejected(job):
    (job / "request.json").write_text(" " * 200001)
    with pytest.raises(ValueError, match="Invalid request"):
        broker.validate(job)


@pytest.mark.parametrize("sizes", [[1_048_577], [800_000, 800_000, 800_000]])
def test_input_byte_limits_rejected(job, sizes):
    for i, size in enumerate(sizes):
        (job / "input" / f"large-{i}.md").write_text("a" * size)
    with pytest.raises(ValueError, match="Input exceeds limit"):
        broker.validate(job)


def test_file_count_limit_rejected(job):
    for i in range(513):
        (job / "input" / f"file-{i}.md").write_text("a")
    with pytest.raises(ValueError, match="Input exceeds limit"):
        broker.validate(job)


@pytest.mark.parametrize("key,valid", [("synthetic=literal", True), ("bad\nINJECT=value", False), ("", False), ("bad\rkey", False), ("a" * 4097, False)])
def test_bootstrap_raw_secret_conversion(tmp_path, key, valid):
    """Execute the actual bootstrap helper against synthetic local inputs."""
    template = (ROOT / "deploy/aws-hermes/boot.sh.tftpl").read_text()
    source = template.split("python3 - <<'PYTHON'\n", 1)[1].split("\nPYTHON", 1)[0]
    settings = {"RGCE_MODEL_PROVIDER": "custom", "RGCE_MODEL_NAME": "selected-model", "RGCE_MODEL_BASE_URL": "https://provider.example/v1", "RGCE_MODEL_KEY_ENV": "OPENAI_API_KEY"}
    encoded = base64.b64encode(json.dumps(settings).encode()).decode()
    source = source.replace("${model_config_b64}", encoded).replace("Path('/run/rgce-hermes')", f"Path({str(tmp_path)!r})")
    (tmp_path / "key.json").write_text(json.dumps(key))
    if valid:
        exec(compile(source, "bootstrap-helper", "exec"), {})
        lines = (tmp_path / "model.env").read_text().splitlines()
        assert len(lines) == 5
        assert "OPENAI_API_KEY=" + key in lines
    else:
        with pytest.raises(SystemExit, match="single nonempty printable API key"):
            exec(compile(source, "bootstrap-helper", "exec"), {})
        assert not (tmp_path / "model.env").exists()
    assert not (tmp_path / "key.json").exists()
