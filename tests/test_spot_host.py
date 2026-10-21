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
    flags = {}

    def merge(members, exists):
        request = {"exists": exists, "initial": initial, "members": members, "header": "# h\n",
                   "main": {"account_id": "999999999999", "flags": flags}}
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
    flags["delegated_admin"] = True  # turned on in Terraform after first boot
    assert merge([member], True) is True and yaml.safe_load(profile.read_text())["accounts"][0]["delegated_admin"] is True
    edited = yaml.safe_load(profile.read_text())
    edited["accounts"][0]["delegated_admin"] = False  # operator turned it off: stays off
    profile.write_text(yaml.safe_dump(edited))
    assert merge([member], True) is False


def test_org_wide_member_role_is_limited_to_the_organization():
    iam = (ROOT / "deploy/aws-single/iam.tf").read_text()
    assert 'Resource = "arn:aws:iam::*:role/${var.member_role_name}"' in iam
    assert '"aws:ResourceOrgID" = var.organization_id' in iam
