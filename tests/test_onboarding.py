"""Account onboarding: organization, delegated administrator detection, read-role probes, coverage and next steps."""
from botocore.exceptions import ClientError

from rgtriage import accounts, collect, config, digest

discover = accounts.discover  # the real function; conftest stubs the module attribute for every other test

PRIMARY = "111111111111"
A, B, C = "222222222222", "333333333333", "444444444444"
ORG = "o-exampleorg1"


def denied(code="AccessDeniedException", op="ListAccounts"):
    return ClientError({"Error": {"Code": code, "Message": "no"}}, op)


class Pages:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **_):
        return iter(self.pages)


class Client:
    def __init__(self, env):
        self.env = env

    def get_caller_identity(self):
        return {"Account": PRIMARY, "Arn": f"arn:aws:sts::{PRIMARY}:assumed-role/desk-host/i-0abc"}

    def get_role(self, RoleName):
        return {"Role": {"Arn": f"arn:aws:iam::{PRIMARY}:role/aws-reserved/sso.amazonaws.com/{RoleName}"}}

    def describe_organization(self):
        if not self.env.get("org"):
            raise denied("AWSOrganizationsNotInUseException", "DescribeOrganization")
        return {"Organization": {"Id": ORG, "MasterAccountId": "999999999999"}}

    def get_paginator(self, op):
        assert op == "list_accounts"
        if self.env.get("list_accounts") is None:
            raise denied()
        return Pages([{"Accounts": [{"Id": i, "Name": n, "Status": "ACTIVE"} for i, n in self.env["list_accounts"].items()]}])


class Session:
    def __init__(self, env):
        self.env = env

    def client(self, name, **_):
        return Client(self.env)


def setup(monkeypatch, env, admin=None, readable=()):
    monkeypatch.setattr(accounts.aws, "session_for", lambda account, region=None: Session(env))
    monkeypatch.setattr(accounts, "_members", lambda session, service, region: (admin or {}).get(service, []))
    probed = []

    def probe(account_id, role_name, profile_name=None):
        probed.append(account_id)
        return (account_id, "ok", "", Session(env)) if account_id in readable else (account_id, "no_role", "AccessDenied", None)
    profile = config.normalize({"name": "t", "accounts": [{"name": "desk", "role_arn": f"arn:aws:iam::{PRIMARY}:role/desk-audit"}]})
    return profile, probe, probed


def test_delegated_admin_without_account_listing(monkeypatch):
    env = {"org": True, "list_accounts": None}
    admin = {"securityhub": [A, B, C], "guardduty": [A, B], "inspector": [A, B, C, PRIMARY]}
    profile, probe, probed = setup(monkeypatch, env, admin, readable={A})
    report = discover(profile, None, probe)
    assert report["mode"] == "organization" and report["organization_id"] == ORG
    assert report["account_list"] == "admin_members"
    assert sorted(probed) == [A, B, C]  # members named by the administrator views are probed; the desk's own account is not
    assert report["full_read"] == [PRIMARY, A] and report["findings_only"] == [B, C] and report["not_covered"] == []
    assert profile["accounts"][0]["delegated_admin"] is True  # detected, not configured
    added = profile["accounts"][1]
    assert added["account_id"] == A and added["role_arn"] == f"arn:aws:iam::{A}:role/RemediGeniusReadOnly" and added["discovered"]
    assert report["reader_arn"] == f"arn:aws:iam::{PRIMARY}:role/aws-reserved/sso.amazonaws.com/desk-host"  # path kept
    assert ("guardduty", A) in accounts.skip_pairs(report) and ("inspector", PRIMARY) not in accounts.skip_pairs(report)
    steps = "\n".join(accounts.next_steps(report))
    assert "create-stack-set" in steps and f"ParameterValue=arn:aws:iam::{PRIMARY}:role/aws-reserved/sso.amazonaws.com/desk-host" in steps and ORG in steps
    assert "cannot list the organization's accounts" in steps
    assert "not the Security Hub" not in steps


def test_member_account_without_admin_rights_lists_the_organization(monkeypatch):
    env = {"org": True, "list_accounts": {A: "Payments Prod", B: "Sandbox", PRIMARY: "Security"}}
    profile, probe, probed = setup(monkeypatch, env, readable={A})
    report = discover(profile, None, probe)
    assert sorted(probed) == [A, B]
    assert report["full_read"] == [PRIMARY, A] and report["not_covered"] == [B] and report["findings_only"] == []
    assert profile["accounts"][1]["name"] == "payments-prod"
    assert "delegated_admin" not in profile["accounts"][0]
    steps = "\n".join(accounts.next_steps(report))
    assert "not the Security Hub / GuardDuty / Inspector delegated administrator" in steps


def test_standalone_account_is_quiet(monkeypatch):
    profile, probe, probed = setup(monkeypatch, {"org": False})
    report = discover(profile, None, probe)
    assert report["mode"] == "standalone" and probed == []
    assert accounts.summary_lines(report) == []
    assert "not in an AWS Organization" in accounts.next_steps(report)[0]


def test_new_role_is_reported_once(monkeypatch):
    env = {"org": True, "list_accounts": {A: "a", B: "b"}}
    profile, probe, _ = setup(monkeypatch, env, readable={A, B})
    first = discover(profile, {"full_read": [A]}, probe)
    assert first["newly_readable"] == [B]
    profile, probe, _ = setup(monkeypatch, env, readable={A, B})
    assert discover(profile, first, probe)["newly_readable"] == []
    assert "Newly onboarded this scan" in "\n".join(accounts.summary_lines(first))


def test_configured_accounts_are_not_probed_and_discovery_can_be_disabled(monkeypatch):
    env = {"org": True, "list_accounts": {A: "a", B: "b"}}
    profile, probe, probed = setup(monkeypatch, env, readable={A, B})
    profile["accounts"].append({"name": "pinned", "account_id": A, "role_arn": "x", "regions": ["us-east-1"],
                                "criticality": "mission_critical"})
    discover(profile, None, probe)
    assert probed == [B]
    profile, probe, probed = setup(monkeypatch, env, readable={A, B})
    profile["organization"]["discover"] = False
    report = discover(profile, None, probe)
    assert probed == [] and report["not_covered"] == [A, B]


def test_collect_skips_reads_the_administrator_already_covers(monkeypatch):
    calls = []
    monkeypatch.setitem(collect.COLLECTORS, "guardduty", lambda s, account, region, opts: (calls.append(account["account_id"]) or [], {}))
    profile = config.normalize({"name": "t", "sources": ["guardduty"], "accounts": [
        {"name": "desk", "account_id": PRIMARY, "_session": object()},
        {"name": "member", "account_id": A, "_session": object()}]})
    collect.collect(profile, skip={("guardduty", A)})
    assert calls == [PRIMARY]
    assert all("_session" not in a for a in profile["accounts"])  # probe sessions are used once, never stored


def test_board_shows_account_coverage():
    report = {"mode": "organization", "admin": {"securityhub": [A, B]}, "full_read": [PRIMARY, A],
              "findings_only": [B], "not_covered": [], "member_role_name": "RemediGeniusReadOnly", "newly_readable": []}
    scan = {"scanned_at": "2026-10-21T00:00:00", "profile": {"name": "t"}, "issues": [], "findings": [],
            "coverage": [{"source": "securityhub", "account": "desk", "region": "us-east-1", "status": "ok", "count": 0}],
            "changes": {}, "onboarding": report}
    board = digest.markdown(scan)
    assert "Accounts: 2 read fully · 1 findings only" in board and "rgtriage onboarding" in board
    failed = {"mode": "unknown", "admin": {}, "notes": ["account discovery failed: boom"]}
    assert accounts.summary_lines(failed) == ["Accounts: account discovery failed: boom"]


def test_account_listed_by_id_uses_the_member_role():
    profile = config.normalize({"accounts": [{"name": "desk"}, {"account_id": A, "criticality": "mission_critical"}],
                                "organization": {"member_role_name": "CustomRead"}})
    assert "role_arn" not in profile["accounts"][0]
    assert profile["accounts"][1]["role_arn"] == f"arn:aws:iam::{A}:role/CustomRead"
