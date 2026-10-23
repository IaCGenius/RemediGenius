"""Kanban cards: exact AWS CLI from a live read, fallbacks without one, and nothing a worker agent could pick up."""
import importlib.util
import json
from pathlib import Path

from rgtriage import cards, collect, prioritize, store
from test_rgtriage import ACCOUNT, PROFILE, asff, guardduty, home  # noqa: F401  (home is a fixture)

ROOT = Path(__file__).resolve().parents[1]


def _findings(*raw):
    findings, _ = prioritize.prioritize([collect.normalize_asff(r) if "Compliance" in r else collect.normalize_guardduty(r)
                                         for r in raw], PROFILE)
    return {"findings": findings, "issues": prioritize.build_issues(findings)}


def _sg(control, sg):
    return asff(control, severity="CRITICAL", rid=f"arn:aws:ec2:us-east-1:{ACCOUNT}:security-group/{sg}", rtype="AwsEc2SecurityGroup")


def test_security_group_card_revokes_the_exact_open_rules():
    scan = _findings(_sg("EC2.19", "sg-0aaa"), _sg("EC2.19", "sg-0bbb"))
    rules = {"sg-0aaa": [{"SecurityGroupRuleId": "sgr-1", "IsEgress": False, "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                          "CidrIpv4": "0.0.0.0/0"},
                         {"SecurityGroupRuleId": "sgr-2", "IsEgress": False, "IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
                          "CidrIpv4": "10.0.0.0/8"}],
             "sg-0bbb": [{"SecurityGroupRuleId": "sgr-9", "IsEgress": False, "IpProtocol": "-1", "CidrIpv6": "::/0"}]}
    calls = []

    def read(f, service, op, params):
        calls.append((service, op))
        return {"SecurityGroupRules": rules[params["Filters"][0]["Values"][0]]}

    found = cards.members(scan, [scan["findings"][0]["key"]], store.find)
    card = cards.build(found, read)
    assert {f["resource"]["name"] for f in found} == {"sg-0aaa", "sg-0bbb"}  # the same issue on both groups
    assert "--group-id sg-0aaa --security-group-rule-ids sgr-1" in card["body"]
    assert "sgr-2" not in card["body"].split("Fix in code")[0].split("```bash")[1]  # the private rule stays
    assert "--group-id sg-0bbb --security-group-rule-ids sgr-9" in card["body"] and "all traffic from ::/0" in card["body"]
    assert "Write a Terraform fix for refs" in card["body"] and "Prove it is fixed" in card["body"]
    assert card["title"].startswith("[P") and card["key"].startswith("rg:") and card["priority"] in (1, 2, 3, 4)
    assert all(op == "describe_security_group_rules" for _, op in calls)


def test_without_a_live_read_the_card_still_has_runnable_commands():
    scan = _findings(_sg("EC2.13", "sg-0ccc"), asff("S3.8", rid="arn:aws:s3:::payments-data"))
    body = cards.build(cards.members(scan, [f["key"] for f in scan["findings"]], store.find), lambda *a: None)["body"]
    assert "revoke-security-group-ingress --region us-east-1 --group-id sg-0ccc --protocol tcp --port 22 --cidr 0.0.0.0/0" in body
    assert "s3api put-public-access-block --bucket payments-data" in body and "get-public-access-block --bucket payments-data" in body


def test_threat_and_root_cards_carry_no_fix_command():
    scan = _findings(guardduty())
    card = cards.build(cards.members(scan, [scan["findings"][0]["key"]], store.find), lambda *a: None)
    assert "a threat finding. Investigate" in card["body"] and "```bash" not in card["body"].split("Fix in code")[0]


def test_card_command_and_socket(home, capsys):  # noqa: F811
    from rgtriage import cli, server
    from test_rgtriage import _scan
    scan = _scan([collect.normalize_asff(asff("S3.8"))])
    cli.main(["card", scan["findings"][0]["key"], "--offline"])
    card = json.loads(capsys.readouterr().out)
    assert card["refs"] == [scan["findings"][0]["key"]] and "put-public-access-block" in card["body"]
    assert "card" in server.ALLOWED


def _plugin(tmp_path, monkeypatch, card, comments):
    spec = importlib.util.spec_from_file_location("rg_plugin", ROOT / "profiles/remedigenius/plugins/rg-triage/__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    monkeypatch.setenv("RGTRIAGE_PROPOSALS", str(tmp_path / "proposals"))
    fixes = {"records": []}
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=0: json.dumps(card) if args[0] == "card"
                        else json.dumps(fixes["records"]) if args[0] == "fixes" else "ok")
    calls = []

    def kanban(args, board=None, body=None):
        calls.append((args, board, body))
        if args[0] == "create":
            return 0, json.dumps({"id": "t_1", "title": args[-1]})
        comments.append(args[-1])
        return 0, "Comment added"
    monkeypatch.setattr(plugin, "_kanban", kanban)
    return plugin, calls, fixes


def test_plugin_files_triage_cards_without_assignee_and_tracks_fixes(tmp_path, monkeypatch):
    card = {"title": "[P1] S3.8 - bucket - ref abc123abc123", "priority": 4, "key": "rg:S3.8", "refs": ["abc123abc123"], "body": "b\n"}
    comments = []
    plugin, calls, fixes = _plugin(tmp_path, monkeypatch, card, comments)
    out = plugin.handle({"action": "card", "ref": "abc123abc123", "board": "security"})
    args, board, body = calls[0]
    assert args[0] == "create" and "--triage" in args and "--assignee" not in args and board == "security" and body == "b\n"
    assert "Card created: t_1" in out and "no agent works on it" in out
    fixes["records"] = [{"key": "abc123abc123", "state": "pr", "pr": "https://example/pr/1", "owner": "Platform"}]
    plugin.handle({"action": "decide", "ref": "abc123abc123", "status": "fixing", "reason": "user said so"})
    assert comments == ["Fix status: pr · owner Platform · PR https://example/pr/1"]
    plugin.handle({"action": "digest"})
    assert len(comments) == 1  # unchanged state: no second comment
    fixes["records"][0].update(state="verified", last_check={"at": "2026-10-23T00:00:00Z", "passed": True})
    assert "verified fixed: move this card to Done" in plugin.handle({"action": "cards"})


def test_profile_never_lets_hermes_dispatch_agents_on_the_board():
    import yaml
    config = yaml.safe_load((ROOT / "profiles/remedigenius/config.yaml").read_text(encoding="utf-8"))
    assert config["kanban"]["dispatch_in_gateway"] is False and config["kanban"]["auto_decompose"] is False
    assert all("kanban" not in toolsets for toolsets in config["platform_toolsets"].values())  # only the desk files cards
    host = (ROOT / "deploy/aws-single/host.py").read_text(encoding="utf-8")
    workstation = (ROOT / "tools/workstation.py").read_text(encoding="utf-8")
    assert "kanban.dispatch_in_gateway" in host and "kanban.dispatch_in_gateway" in workstation
