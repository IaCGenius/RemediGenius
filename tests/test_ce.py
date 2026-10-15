import copy
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rgce import core
from rgce.app import create_app
from rgce.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_demo_rule_proposal_and_reassessment(store):
    d = core.demo(store)
    a, b = d["before"], d["after"]
    assert a["body"]["origin"] == "deterministic_check"
    assert a["body"]["findings"][0]["rule_id"] == "SGNET-002"
    assert not b["body"]["findings"]
    p = core.proposal(store, a["id"], a["body"]["findings"][0]["row_id"])
    assert not p["ai_used"] and p["status"] == "DRAFT_REQUIRES_REVIEW"
    assert p["evidence_id"] == a["body"]["evidence_id"]
    comparison = core.compare(store, a["id"], b["id"])
    assert comparison["no_longer_observed"][0]["status"] == "RULE_NO_LONGER_MATCHES"
    assert core.assess(store, a["body"]["evidence_id"])["id"] == a["id"]


@pytest.mark.parametrize("module,skill", [("sg", "sg-exposure"), ("s3", "s3-public-access"), ("iam", "iam-least-privilege")])
def test_packaged_rules_match_preserved_skills(module, skill):
    root = Path(__file__).resolve().parents[1]
    source = (root / "profiles/analyst/skills/remedigenius" / skill / "scripts/check.py").read_text(encoding="utf-8")
    packaged = (root / "rgce/rules" / (module + ".py")).read_text(encoding="utf-8")
    source = source.replace('sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skillresult" / "scripts"))\n', '')
    source = source.replace('from skillresult import envelope, finding  # noqa: E402', 'from .skillresult import envelope, finding')
    assert packaged == source


@pytest.mark.parametrize("change", ["partial", "missing", "stale", "wrong_scope", "wrong_engine", "errors", "same_time"])
def test_no_false_clearance(store, change):
    d = core.demo(store)
    a, b = d["before"], copy.deepcopy(d["after"]["body"])
    e = copy.deepcopy(store.get(b["evidence_id"])["body"])
    if change == "partial": b["coverage"] = "partial"
    if change == "missing": e["facts"]["security_groups"] = []
    if change == "stale": b["observed_at"] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    if change == "wrong_scope": b["scope"]["account"] = "444455556666"
    if change == "wrong_engine": b["engine_hash"] = "different"
    if change == "errors": e["errors"] = [{"code": "AccessDenied"}]
    if change == "same_time": b["observed_at"] = a["body"]["observed_at"]
    b["evidence_id"] = store.put("evidence", e)["id"]
    later = store.put("assessment", b)
    assert core.compare(store, a["id"], later["id"])["no_longer_observed"][0]["status"] == "UNKNOWN"


def test_import_cannot_self_attest_collector_coverage(store):
    d = core.demo(store)
    e = store.get(d["before"]["body"]["evidence_id"])["body"]
    imported = core.ingest(store, {**e, "authority": "collector", "demo": True})
    assert imported["body"]["coverage"] == "unknown"
    assert imported["body"]["authority"] == "user_import"
    assert not imported["body"]["demo"]


def test_knowledge_hash_pinning_and_immutable_approval(store):
    a = core.demo(store)["before"]
    d = core.draft_knowledge(store, a["id"], "Owned by the sample team", "Alice")
    with pytest.raises(ValueError): core.approve_knowledge(store, d["id"], "other version", "Bob")
    k = core.approve_knowledge(store, d["id"], d["id"], "Bob")
    assert k["body"]["origin"] == "human_approved_context"
    assert store.get(d["id"])["body"]["status"] == "draft"
    assert core.investigation(store, a["id"], a["body"]["findings"][0]["row_id"])["approved_knowledge"][0]["id"] == k["id"]
    # Context is never silently carried over to a different assessment.
    assert k["body"]["assessment_id"] == a["id"]


def test_disk_tampering_detected(store):
    r = store.put("test", {"x": 1})
    with store.connect() as db: db.execute("UPDATE records SET body=? WHERE id=?", ('{"x":2}', r["id"]))
    with pytest.raises(ValueError, match="integrity"): store.get(r["id"])


def test_worse_rule_on_same_resource_is_not_clearance(store):
    d = core.demo(store)
    a = d["before"]
    e = copy.deepcopy(store.get(d["after"]["body"]["evidence_id"])["body"])
    e["facts"]["security_groups"][0]["ip_permissions"] = [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]
    later = core.assess(store, store.put("evidence", e)["id"])
    result = core.compare(store, a["id"], later["id"])
    assert later["body"]["findings"][0]["rule_id"] == "SGNET-001"
    assert result["no_longer_observed"][0]["status"] == "UNKNOWN"
    assert any("still flagged" in r for r in result["no_longer_observed"][0]["reasons"])


def test_native_findings_keep_source_origin(store):
    p = {"adapter": "securityhub-asff", "scope": {"account": "111122223333", "regions": ["us-east-1"]},
         "observed_at": datetime.now(timezone.utc).isoformat(), "facts": {"Findings": [{"Id": "provider-finding", "ProductArn": "provider", "AwsAccountId": "111122223333", "Severity": {"Label": "HIGH"}, "Resources": [{"Id": "resource"}]}]}}
    a = core.assess(store, core.ingest(store, p)["id"])
    assert a["body"]["origin"] == "source_evidence"
    assert a["body"]["findings"][0]["severity"] == "high"


def test_local_http_boundaries_and_human_workflow(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        assert c.post("/api/demo", json={}).status_code == 403
        assert c.get("/api/state", headers={"host": "attacker.example"}).status_code == 403
        assert c.get("/api/session", headers={"origin": "https://evil.example"}).status_code == 403
        assert c.get("/api/state", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        headers = {"X-RGCE-Token": c.get("/api/session").json()["token"]}
        d = c.post("/api/demo", json={}, headers=headers).json()
        assert len(c.get("/api/state").json()["assessments"]) == 2
        draft = c.post("/api/knowledge/draft", json={"assessment_id": d["before"]["id"], "text": "<script>alert(1)</script>", "author": "Reviewer"}, headers=headers).json()
        approval = c.post("/api/knowledge/approve", json={"draft_id": draft["id"], "expected_hash": draft["id"], "reviewer": "Reviewer"}, headers=headers)
        assert approval.status_code == 200
        assert c.post("/api/import", json={"adapter": "bad"}, headers=headers).status_code == 400
        assert "frame-ancestors 'none'" in c.get("/").headers["content-security-policy"]
        assert c.get("/static/app.js").status_code == 200


def test_repo_snapshot_pins_committed_files_and_skips_tfvars(tmp_path):
    from rgce.adapters import repository_snapshot
    repo = tmp_path / "sample"
    repo.mkdir()
    def git(*args): subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    git("init")
    (repo / "main.tf").write_text('resource "example" "x" {}')
    (repo / "secret.tfvars").write_text('password = "do-not-import"')
    git("add", ".")
    git("-c", "user.name=CE Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    (repo / "main.tf").write_text("uncommitted should not be read")
    snapshot = repository_snapshot(repo)
    assert len(snapshot["facts"]["files"]) == 1
    assert snapshot["facts"]["files"][0]["content"] == 'resource "example" "x" {}'
    assert len(snapshot["scope"]["commit"]) == 40


def test_mcp_round_trip(store):
    import asyncio
    from mcp import Client
    from rgce.mcp_server import create_server
    d = core.demo(store)
    async def run():
        async with Client(create_server(store)) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {"list_capabilities", "list_assessments", "list_evidence", "get_record", "investigate", "prepare_proposal", "reassess", "search_knowledge_sources", "list_knowledge_concepts", "prepare_knowledge_review"}
            assert all(t.annotations.read_only_hint for t in tools)
            result = await client.call_tool("reassess", {"before": d["before"]["id"], "after": d["after"]["id"]})
            assert not result.is_error
    asyncio.run(run())
