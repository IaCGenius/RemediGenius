"""Durable checkpoints (folder backend; the S3 backend shares the same logic)."""
import json
import sqlite3

import pytest

from rgtriage import durable


@pytest.fixture(autouse=True)
def lineage(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_LINEAGE", str(tmp_path / "lineage"))


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "hermes"
    (h / "profiles/remedigenius").mkdir(parents=True)
    (h / "config.yaml").write_text("model: x\n")
    (h / "profiles/remedigenius/SOUL.md").write_text("desk")
    (h / "cache").mkdir()
    (h / "cache/big.bin").write_bytes(b"0" * 1000)
    db = sqlite3.connect(h / "state.db")
    db.execute("create table m(t)")
    db.execute("insert into m values ('hello')")
    db.commit()
    db.close()
    return h


def test_roundtrip_restores_into_empty_home(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    saved = durable.checkpoint(home, "hermes", store)
    assert saved["status"] == "SAVED" and saved["files"] == 3  # cache excluded; lineage kept outside the home
    target = tmp_path / "new-host"
    restored = durable.restore(target, "hermes", store)
    assert restored["status"] == "RESTORED"
    assert (target / "profiles/remedigenius/SOUL.md").read_text() == "desk"
    assert sqlite3.connect(target / "state.db").execute("select t from m").fetchone() == ("hello",)
    assert not (target / "cache").exists()


def test_unchanged_home_is_not_uploaded_again(home, tmp_path):
    store = durable.backend(f"file://{tmp_path / 'durable'}")
    durable.checkpoint(home, "hermes", store)
    assert durable.checkpoint(home, "hermes", store)["status"] == "UNCHANGED"
    (home / "config.yaml").write_text("model: y\n")
    assert durable.checkpoint(home, "hermes", store)["status"] == "SAVED"
    assert len(store.list("hermes/snapshots")) == 2


def test_home_with_only_empty_folders_is_restored(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    durable.checkpoint(home, "hermes", store)
    target = tmp_path / "fresh"
    (target / "proposals").mkdir(parents=True)  # setup creates folders before the restore runs
    (target / ".lineage").mkdir()
    (target / ".lineage/hermes").write_text("x")  # bookkeeping from restoring another home first
    assert durable.restore(target, "hermes", store)["status"] == "RESTORED"


def test_live_state_is_never_overwritten(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    durable.checkpoint(home, "hermes", store)
    (home / "config.yaml").write_text("newer live edit\n")
    assert durable.restore(home, "hermes", store)["status"] == "SKIPPED_NOT_EMPTY"
    assert (home / "config.yaml").read_text() == "newer live edit\n"


def test_tampered_checkpoint_is_rejected(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    durable.checkpoint(home, "hermes", store)
    manifest = json.loads(store.get("hermes/latest.json"))
    store.put(manifest["key"], b"not the archive")
    with pytest.raises(ValueError):
        durable.restore(tmp_path / "empty", "hermes", store)


def test_missing_checkpoint_and_retention(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    assert durable.restore(tmp_path / "x", "desk", store)["status"] == "NO_CHECKPOINT"
    for i in range(durable.KEEP + 3):
        (home / "config.yaml").write_text(f"v{i}\n")
        durable.checkpoint(home, "hermes", store)
    assert len(store.list("hermes/snapshots")) == durable.KEEP
    latest = json.loads(store.get("hermes/latest.json"))
    assert store.get(latest["key"]) is not None


def test_folder_backend_refuses_keys_outside_root(tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    with pytest.raises(ValueError):
        store.put("../escape", b"x")


def test_parse_homes():
    assert durable.parse_homes(["hermes=/data/hermes", "desk=/data/rgtriage"]) == {"hermes": "/data/hermes", "desk": "/data/rgtriage"}
    with pytest.raises(ValueError):
        durable.parse_homes(["no-equals"])


def test_fresh_home_cannot_replace_existing_state(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    durable.checkpoint(home, "hermes", store)
    good = json.loads(store.get("hermes/latest.json"))["key"]
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (tmp_path / "lineage/hermes").unlink()  # a new machine: no lineage, restore never ran
    (fresh / "config.yaml").write_text("brand new, restore never ran\n")
    assert durable.checkpoint(fresh, "hermes", store)["status"] == "DIVERGED"
    assert json.loads(store.get("hermes/latest.json"))["key"] == good
    assert durable.checkpoint(fresh, "hermes", store, force=True)["status"] == "SAVED"


def test_restored_home_continues_the_lineage(home, tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    durable.checkpoint(home, "hermes", store)
    target = tmp_path / "restored"
    durable.restore(target, "hermes", store)
    (target / "config.yaml").write_text("changed after restore\n")
    assert durable.checkpoint(target, "hermes", store)["status"] == "SAVED"


def test_read_only_home_can_be_checkpointed(home, tmp_path):
    import os, stat
    store = durable.backend(str(tmp_path / "durable"))
    for path in [home, *home.rglob("*")]:
        path.chmod(stat.S_IREAD | (stat.S_IEXEC if path.is_dir() else 0))
    try:
        assert durable.checkpoint(home, "hermes", store)["status"] == "SAVED"
    finally:
        for path in [home, *home.rglob("*")]:
            os.chmod(path, 0o700 if path.is_dir() else 0o600)


def test_locked_database_never_produces_a_checkpoint_without_it(home, tmp_path, monkeypatch):
    store = durable.backend(str(tmp_path / "durable"))
    durable.checkpoint(home, "hermes", store)
    good = json.loads(store.get("hermes/latest.json"))["key"]
    (home / "config.yaml").write_text("changed while the database is busy\n")
    monkeypatch.setattr(durable, "DB_ATTEMPTS", 2)
    monkeypatch.setattr(durable.time, "sleep", lambda s: None)
    real = durable.sqlite3.connect

    def busy(target, *a, **k):
        if str(target).startswith("file:"):
            raise sqlite3.OperationalError("database is locked")
        return real(target, *a, **k)
    monkeypatch.setattr(durable.sqlite3, "connect", busy)
    result = durable.checkpoint(home, "hermes", store)
    assert result["status"] == "INCOMPLETE" and "state.db" in result["failed"][0]
    assert json.loads(store.get("hermes/latest.json"))["key"] == good  # the complete checkpoint stays latest


def test_wal_contents_are_included(tmp_path):
    store = durable.backend(str(tmp_path / "durable"))
    home = tmp_path / "h"
    home.mkdir()
    writer = sqlite3.connect(home / "state.db")
    writer.execute("pragma journal_mode=wal")
    writer.execute("pragma wal_autocheckpoint=0")
    writer.execute("create table sessions(id)")
    writer.execute("insert into sessions values ('only-in-wal')")
    writer.commit()  # still open: the row lives in state.db-wal, not the main file
    assert durable.checkpoint(home, "hermes", store)["status"] == "SAVED"
    writer.close()
    target = tmp_path / "restored"
    durable.restore(target, "hermes", store)
    assert sqlite3.connect(target / "state.db").execute("select id from sessions").fetchall() == [("only-in-wal",)]


def test_wal_database_on_read_only_mount_without_shm(tmp_path, monkeypatch):
    """SQLite refuses to open a WAL database read-only when it cannot create -shm; the private copy path is used."""
    store = durable.backend(str(tmp_path / "durable"))
    home = tmp_path / "h"
    home.mkdir()
    writer = sqlite3.connect(home / "cron.db")
    writer.execute("pragma journal_mode=wal")
    writer.execute("create table runs(id)")
    writer.execute("insert into runs values ('kept')")
    writer.commit()
    writer.close()
    real = durable.sqlite3.connect

    def no_inplace(target, *a, **k):
        if str(target).startswith("file:"):
            raise sqlite3.OperationalError("unable to open database file")
        return real(target, *a, **k)
    monkeypatch.setattr(durable.sqlite3, "connect", no_inplace)
    assert durable.checkpoint(home, "hermes", store)["status"] == "SAVED"
    monkeypatch.setattr(durable.sqlite3, "connect", real)
    target = tmp_path / "restored"
    durable.restore(target, "hermes", store)
    assert sqlite3.connect(target / "cron.db").execute("select id from runs").fetchall() == [("kept",)]
