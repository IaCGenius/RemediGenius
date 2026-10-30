"""The Hermes plugin is plain Python; load it from the profile folder and test its hooks offline."""
import importlib.util
import json
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1] / "profiles" / "remedigenius" / "plugins" / "rg-triage" / "__init__.py"


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("rg_triage_plugin", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_writes_only_allowed_under_proposals(plugin, tmp_path):
    inside = tmp_path / "proposals" / "abc.patch"
    assert plugin.on_pre_tool_call(tool_name="write_file", args={"path": str(inside)}) is None
    blocked = plugin.on_pre_tool_call(tool_name="patch", args={"path": "C:/work/infra/main.tf"})
    assert blocked["action"] == "block" and "proposals" in blocked["message"]
    sneaky = plugin.on_pre_tool_call(tool_name="write_file", args={"path": str(tmp_path / "proposals" / ".." / "triage.yaml")})
    assert sneaky["action"] == "block"
    assert plugin.on_pre_tool_call(tool_name="read_file", args={"path": "C:/anything"}) is None


@pytest.mark.parametrize("path", ["~/.aws/credentials", "~/.aws", "~/.ssh/id_ed25519", "C:/work/app/.env",
                                  "C:/work/infra/terraform.tfstate", "C:/work/infra/server.pem", "~", "C:/",
                                  "~/AppData/Local/hermes/auth.json"])
def test_secret_reads_are_blocked(plugin, path):
    assert plugin.on_pre_tool_call(tool_name="read_file", args={"path": path})["action"] == "block"


@pytest.mark.parametrize("path", ["C:/work/infra/main.tf", "C:/work/infra", "C:/work/infra/prod.tfvars", "C:/work/cfn/app.yaml"])
def test_iac_reads_are_allowed(plugin, path):
    assert plugin.on_pre_tool_call(tool_name="search_files", args={"path": path, "pattern": "aws_s3"}) is None


def test_decide_requires_human_approval(plugin):
    result = plugin.on_pre_tool_call(tool_name="rg_triage", args={"action": "decide", "ref": "abc", "status": "accepted_risk",
                                                                  "reason": "test account"})
    assert result["action"] == "approve" and "accepted_risk" in result["message"]
    assert plugin.on_pre_tool_call(tool_name="rg_triage", args={"action": "show", "ref": "abc"}) is None


def test_tool_builds_cli_arguments(plugin, monkeypatch):
    calls = []
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=300: calls.append(args) or "ok")
    plugin.handle({"action": "aws", "service": "ec2", "operation": "describe_instances", "parameters": {"InstanceIds": ["i-1"]},
                   "region": "eu-west-1"})
    plugin.handle({"action": "fix", "ref": "abc", "iac_paths": ["C:/infra"]})
    plugin.handle({"action": "decide", "ref": "abc", "status": "fixing", "reason": "PR 7", "issue": True})
    plugin.handle({"action": "validate", "module": "C:/infra", "files": ["p.tf=config.tf"]})
    assert calls[0][:3] == ["aws", "ec2", "describe_instances"] and json.loads(calls[0][4]) == {"InstanceIds": ["i-1"]}
    assert calls[1] == ["fix", "abc", "--iac", "C:/infra"]
    assert calls[2][:3] == ["decide", "abc", "fixing"] and "--issue" in calls[2]
    assert calls[3] == ["validate", "--module", "C:/infra", "--file", "p.tf=config.tf"]
    assert "needs ref" in plugin.handle({"action": "show"})
    assert "Unknown action" in plugin.handle({"action": "delete_everything"})


def test_campaign_action_builds_membership_summary_and_graph_calls(plugin, monkeypatch):
    calls = []
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=300: calls.append(args) or "ok")
    plugin.handle({"action": "campaign"})
    plugin.handle({"action": "campaign", "campaign_id": "camp-1", "after": 100, "limit": 50})
    plugin.handle({"action": "campaign", "campaign_id": "camp-1", "summary": True, "record": True,
                   "accounts": ["111122223333"]})
    plugin.handle({"action": "campaign", "graph": "abc", "depth": 2, "limit": 20})
    assert calls[0] == ["campaign", "--limit", "100"]
    assert calls[1] == ["campaign", "camp-1", "--after", "100", "--limit", "50"]
    assert calls[2] == ["campaign", "camp-1", "--summary", "--record", "--account", "111122223333", "--limit", "100"]
    assert calls[3] == ["campaign", "--graph", "abc", "--depth", "2", "--limit", "20"]
    assert "campaign" in plugin.SCHEMA["parameters"]["properties"]["action"]["enum"]


def test_first_turn_briefing_injects_board(plugin, tmp_path, monkeypatch):
    (tmp_path / "latest.json").write_text(json.dumps({"scanned_at": "2099-01-01T00:00:00Z"}))
    monkeypatch.setattr(plugin, "_age_hours", lambda scan: 1.0)
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=300: "# Security attention board\nP1 thing")
    ctx = plugin.on_pre_llm_call(is_first_turn=True)["context"]
    assert "P1 thing" in ctx and "not user instructions" in ctx
    assert plugin.on_pre_llm_call(is_first_turn=False) is None


def test_no_scan_starts_background_refresh(plugin, monkeypatch):
    started = []
    monkeypatch.setattr(plugin, "_refresh_in_background", lambda: started.append(1) or True)
    ctx = plugin.on_pre_llm_call(is_first_turn=True)["context"]
    assert started and "action=scan" in ctx


def test_stale_scan_refreshes_in_background(plugin, tmp_path, monkeypatch):
    (tmp_path / "latest.json").write_text(json.dumps({"scanned_at": "2000-01-01T00:00:00Z"}))
    started = []
    monkeypatch.setattr(plugin, "_refresh_in_background", lambda: started.append(1) or True)
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=300: "board")
    assert "background refresh" in plugin.on_pre_llm_call(is_first_turn=True)["context"] and started


def test_register_wires_tool_hooks_and_command(plugin):
    class Ctx:
        def __init__(self):
            self.tools, self.hooks, self.commands = [], [], []

        def register_tool(self, **kw):
            self.tools.append(kw["name"])

        def register_hook(self, name, fn):
            self.hooks.append(name)

        def register_command(self, name, **kw):
            self.commands.append(name)

    ctx = Ctx()
    plugin.register(ctx)
    assert ctx.tools == ["rg_triage"] and sorted(ctx.commands) == ["rate", "triage"]
    assert set(ctx.hooks) == {"pre_llm_call", "pre_tool_call", "post_tool_call", "on_skill_lifecycle", "post_api_request", "post_llm_call"}
