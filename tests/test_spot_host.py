"""Spot host bootstrap for RemediGenius Community Edition (deploy/aws-single/host.py), offline."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CFG = {"name": "remedigenius-ce", "region": "us-east-1", "bucket": "bucket-x", "scan_interval_hours": 4,
       "container_memory_mb": 4096, "image": "nousresearch/hermes-agent:stable@sha256:abc"}


@pytest.fixture
def host():
    spec = importlib.util.spec_from_file_location("spot_host", ROOT / "deploy/aws-single/host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ensure_user_creates_group_and_user_10000(host, monkeypatch):
    calls = []

    class Missing:
        returncode = 2

    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: Missing())
    monkeypatch.setattr(host, "run", lambda *args, **kw: calls.append(args))
    host.ensure_user()
    assert calls[0][:4] == ("groupadd", "--system", "--gid", "10000")
    assert "--gid" in calls[1] and calls[1][calls[1].index("--gid") + 1] == "10000"  # not an auto-allocated gid


def test_desk_service_is_hardened_checkpoints_to_s3_and_watches_spot(host):
    units = host.units(CFG)
    desk = units["remedigenius-desk.service"]
    for directive in ("User=10000", "Group=10000", "NoNewPrivileges=yes", "ProtectSystem=strict",
                      "ReadWritePaths=/data/rgtriage", "RuntimeDirectoryPreserve=yes", "PYTHONPATH=/opt/rgtriage/src"):
        assert directive in desk
    assert "serve --socket /run/rgtriage/rgtriage.sock --durable s3://bucket-x/state" in desk
    assert "RGTRIAGE_WIKI_DIR" not in desk and "rg-wiki" not in desk  # the WebUI and its wiki view are gone
    assert "ReadWritePaths=/data/rgtriage /data/rggithub /data/iac" in desk
    assert "--home hermes=/data/hermes --home desk=/data/rgtriage" in desk and "--spot" in desk
    assert "ExecStopPost=" in desk and "durable checkpoint" in desk  # final checkpoint on shutdown
    assert "OnUnitActiveSec=4h" in units["remedigenius-scan.timer"]


def test_hermes_container_has_no_aws_access_and_read_only_desk_state(host):
    hermes = host.units(CFG)["remedigenius-hermes.service"]
    assert "-v /data/rgtriage:/data/rgtriage:ro" in hermes
    assert "/run/rgtriage:/run/rgtriage" in hermes and "--memory 4096m" in hermes
    assert "AWS_ACCESS_KEY" not in hermes and "/data/rgtriage/proposals" not in hermes
    assert host.PROPOSALS == "/opt/data/proposals"  # Hermes only permits writes under its home


def test_seed_model_with_and_without_key(host):
    template = (ROOT / "profiles/remedigenius/config.yaml").read_text(encoding="utf-8")
    seeded = host.seed_model(template, ("deepseek-v4.1-flash", "https://example/v1"))
    assert '"deepseek-v4.1-flash"' in seeded and "__MODEL" not in seeded
    keyless = host.seed_model(template, None)
    assert "model:" not in keyless and "plugins:" in keyless and "rg-triage" in keyless


def test_sync_profile_writes_socket_mode_and_watch_script(host, tmp_path, monkeypatch):
    monkeypatch.setattr(host.os, "lchown", lambda *a: None, raising=False)
    profile = tmp_path / "profiles/remedigenius"
    (profile / "skills").mkdir(parents=True)
    host.sync_profile(ROOT, tmp_path)
    local = json.loads((profile / "plugins/rg-triage/local.json").read_text())
    assert local == {"socket": "/run/rgtriage/rgtriage.sock", "home": "/data/rgtriage", "proposals": "/opt/data/proposals"}
    assert (profile / "skills/rg-iac-fix/SKILL.md").exists()
    assert not (tmp_path / "rg-wiki").exists()  # no wiki view any more
    script = (profile / "scripts/rgtriage-watch.py").read_text()
    compile(script, "rgtriage-watch.py", "exec")
    assert '"watch"' in script and "/run/rgtriage/rgtriage.sock" in script


def test_terraform_has_no_retained_volume_and_grants_kms_automatically():
    main = (ROOT / "deploy/aws-single/main.tf").read_text()
    iam = (ROOT / "deploy/aws-single/iam.tf").read_text()
    assert "aws_ebs_volume" not in main and "delete_on_termination = true" in main
    assert 'default = "deepseek-v4.1-flash"' in main
    assert 'data "aws_secretsmanager_secret" "model"' in iam and "kms:Decrypt" in iam
    assert "SecurityAudit" not in iam.split('resource "aws_iam_role" "audit"')[0]  # instance role does not read AWS


def test_member_accounts_from_common_role_name_and_explicit_arns(host):
    cfg = {"member_account_ids": ["111111111111", "222222222222"], "member_role_name": "RemediGeniusReadOnly",
           "member_role_arns": ["arn:aws:iam::333333333333:role/CustomRead"]}
    members = {m["account_id"]: m["role_arn"] for m in host.member_accounts(cfg)}
    assert members == {"111111111111": "arn:aws:iam::111111111111:role/RemediGeniusReadOnly",
                       "222222222222": "arn:aws:iam::222222222222:role/RemediGeniusReadOnly",
                       "333333333333": "arn:aws:iam::333333333333:role/CustomRead"}


def test_merge_only_adds_new_member_accounts(host, tmp_path):
    import subprocess
    import sys
    import yaml
    profile = tmp_path / "triage.yaml"
    initial = {"name": "x", "accounts": [{"account_id": "999999999999", "criticality": "mission_critical"}]}

    def merge(members, exists):
        request = {"exists": exists, "initial": initial, "members": members, "header": "# h\n"}
        out = subprocess.run([sys.executable, "-c", host.MERGE, str(profile)], input=json.dumps(request),
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)["changed"]
    assert merge([], False) is True
    edited = yaml.safe_load(profile.read_text())
    edited["accounts"][0]["owner"] = "operator edit"
    profile.write_text(yaml.safe_dump(edited))
    member = {"name": "member-111111111111", "account_id": "111111111111", "role_arn": "arn:aws:iam::111111111111:role/R"}
    assert merge([member], True) is True
    assert merge([member], True) is False  # idempotent
    data = yaml.safe_load(profile.read_text())
    assert data["accounts"][0]["owner"] == "operator edit" and len(data["accounts"]) == 2


def test_org_wide_member_role_is_limited_to_the_organization():
    iam = (ROOT / "deploy/aws-single/iam.tf").read_text()
    assert 'Resource = "arn:aws:iam::*:role/${var.member_role_name}"' in iam
    # The instance role's own organization, resolved by IAM at request time: nothing to configure,
    # and no access at all when the account is not in an organization.
    assert '"aws:ResourceOrgID" = "$${aws:PrincipalOrgID}"' in iam


def test_the_webui_and_the_agents_api_server_are_gone(host):
    units = host.units(CFG)
    assert "remedigenius-webui.service" not in units and not hasattr(host, "WEBUI_IMAGE") and not hasattr(host, "WEBUI_CONTAINER")
    assert "8642" not in units["remedigenius-hermes.service"] and "8787" not in units["remedigenius-hermes.service"]
    assert not hasattr(host, "set_api_key") and not hasattr(host, "API_PORT")
    source = (ROOT / "deploy/aws-single/host.py").read_text(encoding="utf-8")
    assert "API_SERVER_ENABLED" not in source and "HERMES_WEBUI" not in source and "webui.env" not in source.split("def retire_webui")[0]
    assert 'variable "webui"' not in (ROOT / "deploy/aws-single/main.tf").read_text(encoding="utf-8")
    assert "nesquena" not in (ROOT / "NOTICE").read_text(encoding="utf-8")
    config = (ROOT / "profiles/remedigenius/config.yaml").read_text(encoding="utf-8")
    assert "api_server" not in config  # no toolset for a platform nothing starts
    assert "--webui" not in (ROOT / "tools/open-remedigenius.sh").read_text(encoding="utf-8") and "WebUI" not in (ROOT / "tools/open-remedigenius.ps1").read_text(encoding="utf-8")


def test_the_agent_container_still_gets_its_dashboard_and_no_api_server(host, tmp_path, monkeypatch):
    monkeypatch.setattr(host, "HERMES_HOME", tmp_path / "hermes")
    (tmp_path / "hermes").mkdir()
    monkeypatch.setattr(host.os, "chown", lambda *a, **k: None, raising=False)
    real_path = host.Path
    monkeypatch.setattr(host, "LOGIN", tmp_path / "hermes" / "login.json")
    run_dir = tmp_path / "run"

    def fake_path(*parts):
        text = str(parts[0]) if parts else ""
        return real_path(run_dir) if text == "/run/remedigenius" else real_path(*parts)
    monkeypatch.setattr(host, "Path", fake_path)
    host.hermes_env({"webui": True}, "model-key")      # the old setting is ignored: there is no WebUI to enable
    env = (run_dir / "hermes.env").read_text()
    assert "HERMES_DASHBOARD=1" in env and "HERMES_DASHBOARD_PORT=9120" in env and "MODEL_API_KEY=model-key" in env
    assert "API_SERVER" not in env and "WEBUI" not in env and not (run_dir / "webui.env").exists()
    assert not (tmp_path / "hermes" / ".remedigenius-api-key").exists()


def test_retiring_the_webui_cleans_a_host_that_ran_it_and_keeps_the_persons_data(host, tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    (home / "rg-wiki").mkdir(parents=True)
    (home / "rg-wiki" / "index.md").write_text("generated")
    (home / "webui").mkdir()
    (home / "webui" / "settings.json").write_text("{}")             # the WebUI's own folder: the person's data
    (home / ".remedigenius-api-key").write_text("secret")
    (home / "profiles" / "remedigenius").mkdir(parents=True)
    (home / ".env").write_text("KEEP=1\nAPI_SERVER_KEY=secret\n")
    (home / "profiles" / "remedigenius" / ".env").write_text("API_SERVER_KEY=secret\n")
    monkeypatch.setattr(host, "HERMES_HOME", home)
    monkeypatch.setattr(host.os, "chown", lambda *a, **k: None, raising=False)
    calls = []
    monkeypatch.setattr(host.subprocess, "run", lambda args, **k: calls.append(args))
    host.retire_webui()
    assert not (home / "rg-wiki").exists() and not (home / ".remedigenius-api-key").exists()
    assert (home / ".env").read_text() == "KEEP=1\n" and (home / "profiles" / "remedigenius" / ".env").read_text() == ""
    assert (home / "webui" / "settings.json").exists()
    flat = [" ".join(c) for c in calls]
    assert any("disable --now remedigenius-webui.service" in c for c in flat) and any("rm -f remedigenius-webui" in c for c in flat)
    host.retire_webui()                                             # running it again on a clean host is harmless


class _Out:
    def __init__(self, text="false\n", rc=0):
        self.stdout, self.returncode = text, rc


def _fake_hermes(state, sticks=True):
    """A stand-in for `docker exec ... hermes -p default config get/set`: values live in `state`."""
    log = []

    def in_container(*args, check=True, **kw):
        log.append(args)
        if args[:4] == ("hermes", "-p", "default", "config") and args[4] == "get":
            return _Out(f"{state.get(args[5], 'true')}\n")
        if args[:4] == ("hermes", "-p", "default", "config") and args[4] == "set" and sticks:
            state[args[5]] = args[6]
        return _Out()
    return in_container, log


def test_kanban_dispatcher_is_turned_off_after_the_last_restart_and_read_back(host, monkeypatch):
    state, restarts = {}, []
    fake, log = _fake_hermes(state)
    monkeypatch.setattr(host, "in_container", fake)
    monkeypatch.setattr(host, "run", lambda *a, **k: restarts.append(a))
    monkeypatch.setattr(host.time, "sleep", lambda s: None)
    host.ensure_kanban_off()
    assert state == {"kanban.dispatch_in_gateway": "false", "kanban.auto_decompose": "false"}
    assert restarts == [("docker", "restart", "remedigenius")]  # restarted once, because the gateway reads the setting at start


def test_kanban_already_off_changes_and_restarts_nothing(host, monkeypatch):
    state = {"kanban.dispatch_in_gateway": "false", "kanban.auto_decompose": "false"}
    fake, log = _fake_hermes(state)
    restarts = []
    monkeypatch.setattr(host, "in_container", fake)
    monkeypatch.setattr(host, "run", lambda *a, **k: restarts.append(a))
    host.ensure_kanban_off()
    assert restarts == [] and not [c for c in log if c[4] == "set"]


def test_a_dispatcher_setting_that_never_sticks_fails_the_boot(host, monkeypatch):
    fake, _ = _fake_hermes({}, sticks=False)
    monkeypatch.setattr(host, "in_container", fake)
    monkeypatch.setattr(host, "run", lambda *a, **k: None)
    monkeypatch.setattr(host.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="Kanban dispatcher"):
        host.ensure_kanban_off()


def test_the_pinned_host_packages_resolve_together(host):
    """A conflicting pin only shows up on a fresh Spot boot (it did once: cfn-lint needs a newer PyYAML), so ask pip now."""
    import subprocess
    import sys
    proc = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--quiet", "--disable-pip-version-check", *host.PACKAGES],
                          capture_output=True, text=True, timeout=300)
    text = proc.stdout + proc.stderr
    assert "ResolutionImpossible" not in text and "conflicting dependencies" not in text, text[-600:]
    if proc.returncode != 0:
        pytest.skip(f"pip could not reach the package index: {text[-200:]}")


def test_the_release_checks_never_write_or_delete_the_real_github_files():
    """A release check once overwrote and deleted a person's real GitHub App key on an instance they had connected (the checks used the real file
    names). Every write or delete of a GitHub file in the checks must name a probe file of its own, and checks that would act on a real connection
    must skip when one exists."""
    import re
    source = (ROOT / "tools/spot_release_test.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        if "/data/rggithub/" not in line:
            continue
        writes = re.search(r"(\brm\b|[^>]>[^>]| > |\bprintf\b|\bchown\b|\bchmod\b|\binstall\b|>>)", line)
        if writes and "/data/rggithub/" in line:
            names = re.findall(r"/data/rggithub/([A-Za-z0-9_.]+)", line)
            assert all(n.startswith("_probe") for n in names), line.strip()
    assert "app.pem" not in source.split("the untrusted-tools boundary")[1].split("ref=$($D list --limit 1")[0]
    assert "-e /data/rggithub/app.json" in source and "skipped on purpose" in source        # Connect GitHub is not started on a connected instance
