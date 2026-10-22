"""Issues #4-#10: evidence labels, coverage, AWS exposure findings, fix records, business context, data notice."""
import importlib.util
import json
from pathlib import Path

import pytest

from rgtriage import cli, collect, config, digest, fixes, knowledge, prioritize, store

PLUGIN = Path(__file__).resolve().parents[1] / "profiles" / "remedigenius" / "plugins" / "rg-triage" / "__init__.py"
PROFILE = {"accounts": [{"name": "prod", "account_id": "111122223333", "regions": ["us-east-1"], "criticality": "business_critical"}],
           "goals": [], "environment_tag_keys": [], "applications": []}

EXPOSURE = {
    "class_name": "Exposure", "severity_id": 5, "severity": "Critical", "status": "New",
    "finding_info": {"uid": "exp-1", "title": "EC2 instance is reachable from the internet and has an exploitable CVE",
                     "desc": "Port 22 open; CVE with exploit; role can read S3", "types": ["Reachability", "Vulnerability"]},
    "cloud": {"account": {"uid": "111122223333"}, "region": "us-east-1"},
    "resources": [{"uid": "arn:aws:ec2:us-east-1:111122223333:instance/i-0abc", "type": "AwsEc2Instance", "name": "i-0abc"}],
    "remediation": {"desc": "Restrict the security group; patch the package."},
    "traits": [{"name": "network reachable"}, {"name": "unused permissions: 47"}],
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------- #6 AWS exposure findings and attack sequences

def test_exposure_finding_keeps_aws_conclusion_and_is_never_ranked_below_aws():
    f = collect.normalize_exposure(EXPOSURE, "us-east-1")
    assert f["source"] == "securityhub-exposure" and f["severity"] == "CRITICAL" and f["signals"]["aws_exposure"]
    assert f["resource"]["name"] == "i-0abc" and "patch the package" in f["remediation"]["text"]
    assert "unused permissions: 47" in json.dumps(f["context"]["exposure"])
    scored = prioritize.score_finding(dict(f, category="exposure"), {**PROFILE, "applications": []})
    assert scored["priority"] == "P1"
    high = prioritize.score_finding(collect.normalize_exposure(dict(EXPOSURE, severity_id=4), "us-east-1"), PROFILE)
    assert high["priority"] in ("P1", "P2")


def test_attack_sequence_is_p1():
    f = collect.base_finding("guardduty", "arn:x", product="GuardDuty", account="111122223333", region="us-east-1",
                             title="Attack sequence", severity="LOW", category="threat", type="AttackSequence:IAM/CompromisedCredentials")
    f["signals"] = {"active_threat": True, "attack_sequence": True}
    assert prioritize.score_finding(f, PROFILE)["priority"] == "P1"


def test_exposure_collector_reports_not_enabled_instead_of_silence():
    from botocore.exceptions import ClientError

    class Hub:
        def describe_security_hub_v2(self):
            raise ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": "not subscribed"}}, "DescribeSecurityHubV2")

    collect_aws = collect.aws.client
    collect.aws.client = lambda session, service, region: Hub()
    try:
        _, entry = collect.run_one("securityhub-exposure", None, {"name": "prod", "account_id": "1"}, "us-east-1", {"limit": 10})
    finally:
        collect.aws.client = collect_aws
    assert entry["status"] == "not_enabled" and "exposure analysis" in entry["note"]


def test_existing_profiles_gain_the_exposure_source(home):
    (home / "triage.yaml").write_text("name: x\naccounts: [{name: prod}]\nsources: [securityhub, guardduty]\n")
    assert config.load()["sources"][:3] == ["securityhub", "securityhub-exposure", "guardduty"]


# ---------------------------------------------------------------- #4 desk-derived signals are labelled

def test_desk_derived_signals_say_what_is_not_verified():
    f = collect.base_finding("securityhub", "x", product="Security Hub", account="1", region="us-east-1", severity="HIGH",
                             category="exposure", title="SG open")
    f["signals"] = {"public_exposure": True, "correlated": "exposure + vulnerability"}
    reasons = " ".join(prioritize.score_finding(f, PROFILE)["reasons"])
    assert "path not verified" in reasons and "desk heuristic" in reasons


def test_plugin_flags_cited_evidence_ids_the_desk_never_returned(home, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_TRACES_DIR", str(home / "traces"))
    spec = importlib.util.spec_from_file_location("rg_triage_plugin_trust", PLUGIN)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    plugin.on_post_tool_call(tool_name="rg_triage", args={"action": "aws"}, session_id="s", turn_id="t",
                             result="Evidence e-1a2b3c4d · iam.get_role · ...")
    plugin.on_post_llm_call(session_id="s", turn_id="t", user_message="q",
                            assistant_response="Trust is scoped (e-1a2b3c4d); the role is read-only (e-deadbeef).")
    record = json.loads(next((home / "traces").glob("*.jsonl")).read_text().splitlines()[-1])
    assert record["unsupported_evidence"] == ["e-deadbeef"]
    from rgtriage.improve import traces
    assert any("never returned" in r for r in traces.failure_reasons(record))


# ---------------------------------------------------------------- #5 coverage headline

def test_board_states_what_was_inspected_and_what_was_not():
    scan = {"coverage": [{"source": "securityhub", "account": "prod", "account_id": "1", "region": "us-east-1", "status": "ok"},
                         {"source": "guardduty", "account": "prod", "account_id": "1", "region": "us-east-1", "status": "not_enabled"}],
            "footprint": {"1": {"account": "prod", "enabled_regions": ["eu-west-1", "us-east-1", "us-west-2"],
                                "unscanned_with_resources": {"eu-west-1": {"instances": 4}}}},
            "onboarding": {"findings_only": ["2", "3"]}}
    line = digest.coverage_headline(scan)
    assert "1 of 3 enabled region(s)" in line and "1 of 2 sources" in line
    assert "eu-west-1 (4 instances) in prod" in line and "Findings only (no live inspection): 2 account(s)" in line
    assert "no detectors of its own" in digest.SCOPE_NOTE


# ---------------------------------------------------------------- #8 fix records

def _scan(active=True, covered=True):
    finding = {"key": "k1", "source": "securityhub", "account": "111122223333", "region": "us-east-1", "workflow": "NEW",
               "title": "S3.8 block public access", "resource": {"name": "bucket"}}
    return {"findings": [finding] if active else [],
            "coverage": [{"source": "securityhub", "account_id": "111122223333", "region": "us-east-1",
                          "status": "ok" if covered else "denied"}]}


PROOF = {"service": "s3", "operation": "get_public_access_block", "parameters": {"Bucket": "bucket"},
         "expect": {"PublicAccessBlockConfiguration.BlockPublicPolicy": True}}


def test_fix_record_lifecycle_from_decision_to_verified_and_reopened(home):
    store.save_decision("k1", "fixing", "user will fix", fix={"state": "decided", "proof": PROOF, "owner": "Payments",
                                                              "source": "securityhub", "account": "111122223333", "region": "us-east-1"})
    failing = lambda proof, account, region: {"passed": False, "observed": {"x": False}}  # noqa: E731
    passing = lambda proof, account, region: {"passed": True, "observed": {"x": True}}  # noqa: E731
    assert fixes.advance(_scan(), PROFILE, check=failing)[0]["state"] == "decided"
    d = store.load_decisions()
    d["k1"]["fix"]["pr"] = "https://github.com/org/repo/pull/1"
    store._write(home / "decisions.json", d)
    assert fixes.advance(_scan(), PROFILE, check=failing)[0]["state"] == "pr"
    assert fixes.advance(_scan(active=True), PROFILE, check=passing)[0]["state"] == "deployed"  # AWS not re-evaluated yet
    assert fixes.advance(_scan(active=False, covered=False), PROFILE, check=passing)[0]["state"] == "deployed"  # unknown
    record = fixes.advance(_scan(active=False), PROFILE, check=passing)[0]
    assert record["state"] == "verified" and store.load_decisions()["k1"]["status"] == "resolved"
    assert fixes.advance(_scan(active=True), PROFILE, check=passing)[0]["state"] == "reopened"
    assert store.load_decisions()["k1"]["status"] == "fixing"
    assert "1 reopened" in fixes.board_line(fixes.advance(_scan(active=True), PROFILE, check=failing))


def test_fix_record_stalls_without_progress(home):
    store.save_decision("k1", "fixing", "x", fix={"state": "decided", "changed_at": "2020-01-01T00:00:00Z", "owner": "Team A",
                                                   "source": "securityhub", "account": "111122223333", "region": "us-east-1"})
    records = fixes.advance(_scan(), PROFILE, check=lambda *a: {"passed": False})
    assert records[0]["state"] == "stalled" and "stalled: Team A" in fixes.board_line(records)


def test_proof_check_reads_recorded_responses_and_refuses_writes(home, monkeypatch):
    (home / "aws").mkdir()
    (home / "aws" / "s3.get_public_access_block.json").write_text(json.dumps(
        {"PublicAccessBlockConfiguration": {"BlockPublicPolicy": True}}))
    monkeypatch.setenv("RGTRIAGE_EVAL_AWS", str(home / "aws"))
    assert fixes.check_proof(PROOF, PROFILE["accounts"][0], "us-east-1")["passed"]
    assert "not a read-only" in fixes.check_proof(dict(PROOF, operation="put_public_access_block"), {}, "us-east-1")["error"]


# ---------------------------------------------------------------- #9 business context basics

def test_board_shows_missing_business_context_basics():
    lines = knowledge.board_lines({"knowledge": {"organization": 1, "used_in": 2, "findings": 10, "basics": {
        "account_criticality": True, "critical_applications": False, "owners": False, "IaC_location": True, "a_policy": False}}})
    assert "applied to 2 of 10 findings" in lines[0]
    assert "2 of 5 basics set" in lines[1] and "set up business context" in lines[1]


def test_remember_needs_a_draft_under_proposals_and_the_users_click(home, monkeypatch):
    spec = importlib.util.spec_from_file_location("rg_triage_plugin_remember", PLUGIN)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    calls = []
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=0: calls.append(args) or '{"path": "teams/finance.md"}')
    gate = plugin.on_pre_tool_call(tool_name="rg_triage", args={"action": "remember", "path": "x.md"})
    assert gate["action"] == "approve" and gate["rule_key"] == "rg_triage:remember"
    assert "needs path" in plugin.handle({"action": "remember", "path": str(home / "elsewhere.md")})
    draft = home / "proposals" / "knowledge" / "teams" / "finance.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("---\ntype: Team\ntitle: Finance\n---\nOwns vendor-reporting.\n")
    plugin.handle({"action": "remember", "path": str(draft)})
    assert calls[-1][:2] == ["knowledge-edit", "save"] and "--verify" in calls[-1] and not draft.exists()


def test_decide_passes_fix_record_fields(home, monkeypatch):
    spec = importlib.util.spec_from_file_location("rg_triage_plugin_decide", PLUGIN)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    calls = []
    monkeypatch.setattr(plugin, "_run", lambda args, timeout=0: calls.append(args) or "ok")
    plugin.handle({"action": "decide", "ref": "abc", "status": "fixing", "reason": "will fix", "proof": PROOF,
                   "pr": "https://x/pull/1", "owner": "Payments"})
    args = calls[-1]
    assert json.loads(args[args.index("--proof") + 1]) == PROOF and "--pr" in args and "--owner" in args


# ---------------------------------------------------------------- #10 data flow

def test_doctor_says_whether_the_model_endpoint_is_local(monkeypatch):
    monkeypatch.setenv("REMEDIGENIUS_MODEL_BASE_URL", "https://api.example.com/v1")
    assert "third-party" in cli.model_line()
    monkeypatch.setenv("REMEDIGENIUS_MODEL_BASE_URL", "http://192.168.1.20:11434/v1")
    assert "local endpoint" in cli.model_line()
    monkeypatch.delenv("REMEDIGENIUS_MODEL_BASE_URL")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert "runs no model of its own" in cli.model_line()
