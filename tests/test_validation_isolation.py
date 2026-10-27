"""Validation must never run next to the GitHub App key, and what the agent names (files, destinations, modules) is untrusted.

Covers the confirmed finding where `rgtriage validate` copied an arbitrary source file to an absolute destination (so a synthetic key
could be copied into the agent-readable desk folder), the path rules, and the validation service that keeps untrusted tools away from
the key. The OS-level boundary on the real host (separate user, file permissions, no instance-metadata access) is checked by
`tools/spot_release_test.py` on a Spot.
"""
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from rgtriage import cli, config, github, validators
from test_rgtriage import home  # noqa: F401  (fixture: RGTRIAGE_HOME in a temp folder)

KEY = "-----BEGIN PRIVATE KEY-----\nSYNTHETIC-BROKER-KEY\n-----END PRIVATE KEY-----\n"
TF = 'locals {\n  a = 1\n}\n'


@pytest.fixture
def world(home, monkeypatch, tmp_path):  # noqa: F811
    """A desk folder, a GitHub key folder holding a synthetic key, an approved IaC module and a proposals folder."""
    gh_home, module, props = tmp_path / "gh", tmp_path / "iac" / "mod", tmp_path / "proposals"
    for folder in (gh_home, module, props):
        folder.mkdir(parents=True)
    (gh_home / "app.pem").write_text(KEY)
    (module / "main.tf").write_text(TF)
    (props / "ok.tf").write_text(TF.replace("a = 1", "b = 2"))
    monkeypatch.setenv("RGGITHUB_HOME", str(gh_home))
    monkeypatch.setenv("RGTRIAGE_IAC_ROOTS", str(tmp_path / "iac"))
    monkeypatch.setenv("RGTRIAGE_PROPOSALS", str(props))
    monkeypatch.delenv("RGVALIDATE_SOCKET", raising=False)
    captured = {}
    monkeypatch.setattr(validators, "check_module", lambda files: captured.update(files=files) or (True, ["Result: VALID"]))
    return {"home": home, "gh": gh_home, "module": module, "props": props, "captured": captured, "tmp": tmp_path}


def run_validate(world, *file_specs, module=None):
    argv = ["validate", "--module", str(module or world["module"])]
    for spec in file_specs:
        argv += ["--file", spec]
    try:
        cli.main(argv)
    except SystemExit as exit_info:  # a refusal exits with its message; success returns normally
        return str(exit_info.code) if exit_info.code not in (None, 0) else ""
    return ""


def tree_snapshot(*folders):
    return sorted(str(p) for f in folders for p in Path(f).rglob("*"))


# ---------------------------------------------------------------- the confirmed exploit and its variants

def test_the_key_cannot_be_copied_through_validate_even_with_an_absolute_destination(world):
    stolen = world["home"] / "stolen.pem"
    before = tree_snapshot(world["home"], world["gh"], world["module"], world["props"])
    # 1. the key as the source (it is not in the proposals folder)
    assert "DENIED" in run_validate(world, f"{world['gh'] / 'app.pem'}={stolen}")
    # 2. the key copied into the proposals folder first, then an absolute destination
    (world["props"] / "k.pem").write_text(KEY)
    before = tree_snapshot(world["home"], world["gh"], world["module"], world["props"])
    assert "not a safe relative path" in run_validate(world, f"{world['props'] / 'k.pem'}={stolen}")
    assert not stolen.exists()
    assert tree_snapshot(world["home"], world["gh"], world["module"], world["props"]) == before  # rejected requests changed nothing


@pytest.mark.parametrize("destination", ["../escape.tf", "a/../../escape.tf", "/etc/cron.d/x", "C:/Windows/x.tf", "C:\\x.tf", "..\\x.tf", "a//b.tf",
                                         "./x.tf", "a/./b.tf", "", "bad\x00name.tf"])
def test_destinations_must_stay_inside_the_scratch_copy(world, destination):
    message = run_validate(world, f"{world['props'] / 'ok.tf'}={destination}") if destination else ""
    if destination:
        assert "DENIED" in message and "safe relative path" in message
    assert not (world["tmp"] / "escape.tf").exists()


def test_the_module_must_be_inside_an_approved_iac_folder(world):
    assert "approved IaC folder" in run_validate(world, f"{world['props'] / 'ok.tf'}=a.tf", module=world["gh"])
    assert "approved IaC folder" in run_validate(world, f"{world['props'] / 'ok.tf'}=a.tf", module=world["tmp"])
    assert world["captured"] == {}  # nothing was sent for validation


def test_proposed_files_must_come_from_the_proposals_folder(world):
    outside = world["tmp"] / "elsewhere.tf"
    outside.write_text(TF)
    assert "proposals folder" in run_validate(world, f"{outside}=a.tf")
    assert "proposals folder" in run_validate(world, f"{world['module'] / 'main.tf'}=a.tf")
    assert world["captured"] == {}


def test_a_symlink_cannot_smuggle_the_key_in(world):
    link_in_props, link_in_module = world["props"] / "link.tf", world["module"] / "leak.tf"
    try:
        link_in_props.symlink_to(world["gh"] / "app.pem")
        link_in_module.symlink_to(world["gh"] / "app.pem")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    assert "not found" in run_validate(world, f"{link_in_props}=a.tf")  # a symlinked source is refused
    run_validate(world, f"{world['props'] / 'ok.tf'}=b.tf")
    assert "leak.tf" not in world["captured"]["files"]  # a symlink inside the module is never followed
    assert all(b"SYNTHETIC" not in data for data in world["captured"]["files"].values())


def test_normal_proposal_validation_still_works_and_sends_only_module_and_proposal(world):
    assert run_validate(world, f"{world['props'] / 'ok.tf'}=extra.tf") == ""
    files = world["captured"]["files"]
    assert set(files) == {"main.tf", "extra.tf"} and files["extra.tf"].decode().replace(chr(13) + chr(10), chr(10)) == TF.replace("a = 1", "b = 2")


def test_module_snapshots_leave_out_secrets_state_and_links(tmp_path):
    for name, text in {"main.tf": TF, "prod.tfvars": "pw = 1", "terraform.tfstate": "{}", ".env": "X=1", "key.pem": KEY,
                       ".terraform/providers/x": "bin", "sub/ok.tf": TF}.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    assert set(validators.snapshot_dir(tmp_path)) == {"main.tf", "sub/ok.tf"}


def test_fix_never_scans_the_github_key_folder(world):
    from rgtriage import iac
    assert iac.is_credential_path(world["gh"]) and iac.is_credential_path(world["gh"] / "app.pem") and iac.is_credential_path(world["gh"].parent)
    assert not iac.is_credential_path(world["module"])


# ---------------------------------------------------------------- safe paths and archives

@pytest.mark.parametrize("bad", ["", "/abs", "a/../b", "..", "a//b", "a/./b", "C:/x", "c:\\x", "a\x00b", "a\nb"])
def test_safe_relative_rejects_escapes(bad):
    with pytest.raises(ValueError):
        validators.safe_relative(bad)


def test_safe_join_refuses_symlink_components_and_escapes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert validators.safe_join(root, "a/b.tf") == root.resolve() / "a" / "b.tf"
    try:
        (root / "dir").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    with pytest.raises(ValueError, match="symbolic link"):
        validators.safe_join(root, "dir/x.tf")


def test_archives_with_links_devices_or_odd_names_are_rejected(tmp_path):
    import io
    import tarfile
    for kind in ("symlink", "dir", "escape"):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo("a.tf" if kind != "escape" else "../../x.tf")
            if kind == "symlink":
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
            else:
                info.size = 1
            tar.addfile(info, io.BytesIO(b"x") if kind == "escape" else None)
        with pytest.raises(ValueError):
            validators.unpack(buffer.getvalue(), tmp_path / kind)
    files = {"a/b.tf": b"x", "c.yaml": b"y"}
    out = tmp_path / "ok"
    assert sorted(validators.unpack(validators.pack(files), out)) == ["a/b.tf", "c.yaml"] and (out / "a" / "b.tf").read_bytes() == b"x"


# ---------------------------------------------------------------- the validation service

def test_the_service_validates_a_tree_and_rejects_hostile_requests(tmp_path):
    reply = validators.handle_request({"kind": "tree", "changed": ["q.json", "bad.json"]},
                                      validators.pack({"q.json": b"{}", "bad.json": b"{"}), scratch_root=str(tmp_path))
    assert {r["check"]: r["result"] for r in reply["results"]} == {"json q.json": "pass", "json bad.json": "fail"}
    assert validators.handle_request({"kind": "nope"}, b"")["error"]
    assert "rejected" in validators.handle_request({"kind": "tree", "changed": ["../x"]}, validators.pack({"a.json": b"{}"}), str(tmp_path))["error"]
    assert "rejected" in validators.handle_request({"kind": "tree", "changed": []}, b"not an archive", str(tmp_path))["error"]
    assert not list(tmp_path.iterdir())  # throwaway folders are removed


def test_with_a_service_configured_a_missing_service_fails_closed_never_runs_locally(monkeypatch, tmp_path):
    monkeypatch.setenv("RGVALIDATE_SOCKET", str(tmp_path / "no-such.sock"))
    monkeypatch.setattr(validators, "validate_tree", lambda *a, **k: pytest.fail("ran the tools in the caller"))
    monkeypatch.setattr(validators, "terraform_module", lambda *a, **k: pytest.fail("ran terraform in the caller"))
    rows = validators.check_tree({"a.tf": b"x"}, ["a.tf"])
    assert rows[0]["result"] == "fail" and "validation service is unavailable" in rows[0]["detail"] and "nothing was validated" in rows[0]["detail"]
    ok, lines = validators.check_module({"main.tf": b"x"})
    assert not ok and "validation did not run" in lines[0]


def test_publish_refuses_to_run_validators_next_to_the_key(monkeypatch, tmp_path):
    monkeypatch.delenv("RGVALIDATE_SOCKET", raising=False)
    assert not validators.isolated()
    source = (Path(__file__).resolve().parents[1] / "rgtriage" / "github.py").read_text(encoding="utf-8")
    assert "validation isolation is not configured" in source and "_validators.isolated()" in source


@pytest.mark.skipif(not hasattr(validators, "Server") or sys.platform == "win32", reason="needs Unix sockets")
def test_a_real_service_round_trip_over_a_unix_socket(tmp_path, monkeypatch):
    path = tmp_path / "v.sock"
    thread = threading.Thread(target=validators.serve, args=(str(path), str(tmp_path / "scratch")), daemon=True)
    (tmp_path / "scratch").mkdir()
    thread.start()
    for _ in range(50):
        if path.exists():
            break
        time.sleep(0.1)
    monkeypatch.setenv("RGVALIDATE_SOCKET", str(path))
    rows = validators.check_tree({"a.json": b"{}", "b.json": b"{"}, ["a.json", "b.json"])
    assert {r["check"]: r["result"] for r in rows} == {"json a.json": "pass", "json b.json": "fail"}
    with socket.socket(socket.AF_UNIX) as conn:  # a bad request gets a clean refusal
        conn.connect(str(path))
        conn.sendall(b"not json\n")
        assert b"bad request" in conn.recv(4096)
