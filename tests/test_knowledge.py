"""Knowledge: OKF v0.2 bundle handling, shipped concepts, what changes triage, write guards, CLI and the Knowledge tab helpers."""
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from rgtriage import cli, digest, knowledge, okf, playbooks, prioritize, server

ROOT = Path(__file__).resolve().parents[1]
FUTURE = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%d")
PAST = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
REVIEWED = {"verified": [{"by": "human:alex", "at": "2026-10-01T00:00:00Z"}]}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    monkeypatch.delenv("RGTRIAGE_KNOWLEDGE", raising=False)
    monkeypatch.delenv("RGTRIAGE_KNOWLEDGE_INBOX", raising=False)
    (tmp_path / "knowledge-inbox").mkdir()
    (tmp_path / "proposals" / "knowledge").mkdir(parents=True)
    return tmp_path


def finding(**over):
    f = {"key": "k1", "native_id": "n1", "source": "securityhub", "product": "Security Hub", "title": "S3 bucket allows public read",
         "severity": "HIGH", "category": "exposure", "type": "", "control_id": "S3.8", "account": "111122223333",
         "region": "us-east-1", "resource": {"type": "AwsS3Bucket", "id": "arn:aws:s3:::pay-data", "name": "pay-data",
                                             "tags": {"app": "payments"}},
         "signals": {"public_exposure": True}, "context": {}, "remediation": {}}
    f.update(over)
    return f


def concept(b, rel, meta, body="Body."):
    return b.write(rel, meta, body)


# ------------------------------------------------------------------ OKF format

def test_parse_keeps_unknown_keys_and_timestamps_as_written():
    text = ("---\ntype: Metric\ntitle: Revenue\nstale_after: 2026-12-31T00:00:00Z\nverified: {by: human:jsmith, at: 2026-07-01T09:00:00Z}\n"
            "custom: {nested: [1, 2]}\n---\n\nRevenue is [orders](/tables/orders.md).\n")
    meta, body = okf.parse(text)
    assert meta["stale_after"] == "2026-12-31T00:00:00Z" and meta["custom"] == {"nested": [1, 2]}
    assert okf.trust_tier(meta) == "human-reviewed"  # a bare `verified` mapping is a one-element list (spec 5.2)
    again = okf.parse(okf.dump(meta, body))
    assert again[0] == meta and "orders" in again[1]
    assert okf.links_in("metrics/revenue.md", body) == ["tables/orders.md"]


@pytest.mark.parametrize("text,error", [
    ("no frontmatter", "no YAML frontmatter"),
    ("---\ntitle: x\n---\nbody", "type"),
    ("---\ntype: A\ntype: B\n---\n", "duplicate"),
    ("---\ntype: A\nbase: &b {x: 1}\nother: *b\n---\n", "anchors"),
    ("---\ntype: !!python/object:os.system x\n---\n", "anchors, aliases and tags"),
    ("---\ntype: A\n", "closing"),
])
def test_parse_rejects_unsafe_or_invalid_frontmatter(text, error):
    with pytest.raises(okf.OKFError, match=error):
        okf.parse(text)


def test_trust_tiers_status_and_staleness():
    assert okf.trust_tier({}) == "unverified"
    assert okf.trust_tier({"verified": [{"by": "process:nightly", "at": "x"}]}) == "machine-confirmed"
    assert okf.trust_tier({"verified": [{"by": "process:nightly"}, {"by": "human:a"}]}) == "human-reviewed"
    assert okf.status({}) == "stable" and okf.status({"status": "draft"}) == "draft"
    assert okf.is_stale({"stale_after": "2020-01-01"}) and not okf.is_stale({"stale_after": FUTURE})


def test_indexes_logs_validation_and_graph(home):
    b = okf.Bundle(home / "bundle")
    concept(b, "apps/payments.md", {"type": "Application", "title": "Payments", "description": "Card payments."},
            "Owned by [the team](/teams/payments.md). See [missing](/nowhere.md).")
    concept(b, "teams/payments.md", {"type": "Team", "title": "Payments team", "description": "Owns payments."})
    (home / "bundle" / "broken.md").write_text("---\ntitle: no type\n---\n", encoding="utf-8")
    b.build_indexes(title="Test")
    root = (home / "bundle" / "index.md").read_text(encoding="utf-8")
    assert root.startswith('---\nokf_version: "0.2"\n---') and "* [apps](apps/) - 1 concept" in root
    assert "* [Payments](payments.md) - Card payments." in (home / "bundle" / "apps" / "index.md").read_text(encoding="utf-8")
    b.log("Creation", "first", day="2026-10-01")
    b.log("Update", "second", day="2026-10-02")
    log = (home / "bundle" / "log.md").read_text(encoding="utf-8")
    assert log.index("## 2026-10-02") < log.index("## 2026-10-01")  # newest first (spec 9)
    issues = b.validate()
    assert {"level": "error", "path": "broken.md", "message": "frontmatter needs a non-empty `type`"} in issues
    assert any(i["message"] == "link to missing concept /nowhere.md" for i in issues)
    graph = b.graph()
    assert {"source": "apps/payments.md", "target": "teams/payments.md"} in graph["edges"]
    assert b.backlinks("teams/payments.md") == ["apps/payments.md"]
    assert okf.search(b.concepts(), "payments owner")[0]["path"] == "apps/payments.md"


@pytest.mark.parametrize("rel", ["../escape.md", "/../outside.md", "a/../../b.md", "notes.txt", ".hidden/x.md", "index.md"])
def test_bundle_refuses_paths_outside_or_reserved(home, rel):
    with pytest.raises(okf.OKFError):
        okf.Bundle(home / "bundle").write(rel, {"type": "Note"}, "x")


# ------------------------------------------------------------------ shipped knowledge

def test_shipped_knowledge_is_conformant_linked_and_idempotent(home):
    first = knowledge.seed()
    b = knowledge.bundle()
    concepts = b.concepts()
    assert first["shipped"] == len(concepts) >= 20 and not any(c.error for c in concepts)
    assert b.validate(concepts) == []  # every shipped concept has a title and description, and every link resolves
    assert {c.type for c in concepts} >= {"Guide", "Source Guide", "Playbook"}
    assert knowledge.seed()["changed"] == 0
    org = concept(b, "notes/mine.md", {"type": "Note", "title": "Mine", "description": "kept"})
    (b.root / "remedigenius" / "guides" / "old.md").write_text("---\ntype: Guide\n---\nold", encoding="utf-8")
    assert knowledge.seed()["changed"] == 1 and not (b.root / "remedigenius/guides/old.md").exists()
    assert (b.root / org).exists()


def test_frameworks_and_practices_map_controls(home):
    knowledge.seed()
    concepts = knowledge.bundle().concepts()
    types = {c.type for c in concepts}
    assert {"Framework", "Security Practice"} <= types
    practices = [c for c in concepts if c.type == "Security Practice"]
    assert len(practices) == 6 and all(c.meta["remedigenius"]["controls"] for c in practices)
    assert [c.path for c in knowledge.practices_for("S3.8", concepts)] == ["remedigenius/practices/data-protection.md"]
    assert [c.path for c in knowledge.practices_for("EC2.53", concepts)] == ["remedigenius/practices/network-exposure.md"]
    assert knowledge.practices_for("NotAControl.1", concepts) == []
    related = [k["path"] for k in knowledge.for_finding(finding())]
    assert related[0] == "remedigenius/practices/data-protection.md" and "remedigenius/playbooks/s3-public-access.md" in related
    b = knowledge.bundle()
    concept(b, "policies/buckets.md", {"type": "Policy", "title": "Bucket rules", "description": "S3.8 must pass on pay-data."})
    concept(b, "notes/unrelated.md", {"type": "Note", "title": "Software and configuration checks", "description": "x"})
    related = [k["path"] for k in knowledge.for_finding(finding(type="Software and Configuration Checks/AWS Security Best Practices"))]
    assert "policies/buckets.md" in related and "notes/unrelated.md" not in related  # identifiers, not generic words


def test_playbooks_are_okf_concepts_and_fix_prints_them_without_frontmatter():
    for name in playbooks.names():
        meta, _ = okf.parse((playbooks.DIR / f"{name}.md").read_text(encoding="utf-8"))
        assert meta["type"] == "Playbook" and meta["description"]
        assert playbooks.load(name).startswith("# ")


# ------------------------------------------------------------------ what changes triage

def org_bundle(home):
    knowledge.seed()
    b = knowledge.bundle()
    concept(b, "teams/payments-team.md", {"type": "Team", "title": "Payments team", "description": "x", **REVIEWED})
    concept(b, "applications/payments.md", {"type": "Application", "title": "Payments", "description": "Card payments.",
                                            "remedigenius": {"match_tags": {"app": "payments"}, "criticality": "mission_critical",
                                                             "owner": "/teams/payments-team.md"}, **REVIEWED})
    concept(b, "accounts/sandbox.md", {"type": "Account", "title": "Sandbox", "description": "x",
                                       "remedigenius": {"account_id": "999988887777", "criticality": "test_development"}, **REVIEWED})
    concept(b, "applications/unreviewed.md", {"type": "Application", "title": "Ledger", "description": "x",
                                              "remedigenius": {"match_tags": {"app": "ledger"}, "criticality": "mission_critical"}})
    return b


def test_reviewed_application_sets_criticality_and_owner_with_citation(home):
    org_bundle(home)
    eff = knowledge.effective()
    assert [a["path"] for a in eff["applications"]] == ["applications/payments.md"]
    assert eff["ignored"] == [{"path": "applications/unreviewed.md",
                               "reason": "stable, unverified: approve it in the Knowledge tab to apply it"}]
    f = finding()
    _, issues = prioritize.prioritize([f], {"goals": [], "applications": [], "accounts": []}, {}, eff)
    assert "business criticality mission_critical (application Payments, knowledge applications/payments.md) (+15)" in f["reasons"]
    assert f["owner"]["title"] == "Payments team" and f["knowledge"] == ["applications/payments.md", "teams/payments-team.md"]
    assert issues[0]["owner"]["path"] == "teams/payments-team.md"
    lower = finding(key="k2", account="999988887777", resource={"type": "AwsS3Bucket", "id": "b", "name": "b", "tags": {}})
    prioritize.prioritize([lower], {"goals": [], "applications": [], "accounts": []}, {}, eff)
    assert any("knowledge accounts/sandbox.md" in r and "(-10)" in r for r in lower["reasons"])
    unreviewed = finding(key="k3", resource={"type": "AwsS3Bucket", "id": "l", "name": "l", "tags": {"app": "ledger"}})
    prioritize.prioritize([unreviewed], {"goals": [], "applications": [], "accounts": []}, {}, eff)
    assert not unreviewed.get("knowledge")


def test_risk_exception_accepts_until_expiry_then_returns(home):
    b = org_bundle(home)
    concept(b, "exceptions/public-site.md", {"type": "Risk Exception", "title": "Public website bucket", "description": "Static site, no data.",
                                             "remedigenius": {"control_id": "S3.8", "resource": "pay-data", "expires": FUTURE,
                                                              "approved_by": "CISO"}, **REVIEWED})
    f = finding()
    prioritize.prioritize([f], {"goals": [], "applications": [], "accounts": []}, {}, knowledge.effective())
    assert f["decision"]["status"] == "accepted_risk" and f["decision"]["knowledge"] == "exceptions/public-site.md"
    assert not prioritize.is_open(f)
    assert any("risk exception exceptions/public-site.md" in r for r in f["reasons"])
    concept(b, "exceptions/public-site.md", {"type": "Risk Exception", "title": "Public website bucket", "description": "x",
                                             "remedigenius": {"control_id": "S3.8", "expires": PAST}, **REVIEWED})
    g = finding()
    prioritize.prioritize([g], {"goals": [], "applications": [], "accounts": []}, {}, knowledge.effective())
    assert prioritize.is_open(g) and g["expired_exception"]["path"] == "exceptions/public-site.md"
    assert any("expired" in r for r in g["reasons"])
    assert any("expired" in gap for gap in knowledge.gaps(None))
    explicit = finding()
    prioritize.prioritize([explicit], {"goals": [], "applications": [], "accounts": []},
                          {"k1": {"status": "fixing", "reason": "on it"}}, knowledge.effective())
    assert explicit["decision"]["status"] == "fixing"  # the user's own decision always wins


def test_security_goal_boost_is_cited(home):
    b = org_bundle(home)
    concept(b, "goals/pii.md", {"type": "Security Goal", "title": "Protect customer PII", "description": "x",
                                "remedigenius": {"resource_types": ["AwsS3Bucket"], "points": 7}, **REVIEWED})
    f = finding(resource={"type": "AwsS3Bucket", "id": "x", "name": "x", "tags": {}})
    prioritize.prioritize([f], {"goals": [], "applications": [], "accounts": []}, {}, knowledge.effective())
    assert "matches goal: Protect customer PII (knowledge goals/pii.md) (+7)" in f["reasons"]


def test_shipped_folder_never_changes_scores(home):
    knowledge.seed()
    concept(knowledge.bundle(), "remedigenius/guides/sneaky.md", {"type": "Account", "title": "x", "description": "x",
                                                                  "remedigenius": {"account_id": "111122223333", "criticality": "mission_critical"}, **REVIEWED})
    assert knowledge.effective()["accounts"] == {}


# ------------------------------------------------------------------ write guards

def test_save_compose_and_guards(home):
    knowledge.seed()
    meta, body = knowledge.compose("Application", {"title": "Payments", "description": "Card API.", "match_tags": "app=payments, env=prod",
                                                   "criticality": "mission_critical", "owner": "Payments Team"}, "human:alex")
    assert meta["remedigenius"]["match_tags"] == {"app": "payments", "env": "prod"} and "/teams/payments-team.md" in body
    result = knowledge.save(meta, body, "human:alex", verify=True)
    assert result == {"path": "applications/payments.md", "trust": "human-reviewed", "status": "stable", "replaced": False}
    with pytest.raises(okf.OKFError, match="already exists"):
        knowledge.save(meta, body, "human:alex")
    with pytest.raises(okf.OKFError, match="shipped"):
        knowledge.save(meta, body, "human:alex", path="remedigenius/guides/x.md")
    with pytest.raises(okf.OKFError, match="human:"):
        knowledge.save(meta, body, "agent")
    for kind, fields, error in [
        ("Account", {"title": "a", "description": "b", "account_id": "123", "criticality": "non_critical"}, "12 digits"),
        ("Risk Exception", {"title": "a", "description": "b", "expires": FUTURE, "approved_by": "x"}, "control id"),
        ("Risk Exception", {"title": "a", "description": "b", "control_id": "S3.8", "expires": PAST, "approved_by": "x"}, "future"),
        ("Application", {"title": "a", "description": "b", "match_tags": "nope", "criticality": "mission_critical"}, "key=value"),
        ("Nope", {"title": "a"}, "unknown concept kind"),
    ]:
        with pytest.raises(okf.OKFError, match=error):
            knowledge.compose(kind, fields, "human:alex")
    assert knowledge.verify("applications/payments.md", "human:sam")["trust"] == "human-reviewed"
    assert knowledge.deprecate("applications/payments.md", "human:sam", "replaced")["status"] == "deprecated"
    moved = knowledge.remove("applications/payments.md", "human:sam")
    assert Path(moved["trash"]).exists() and not (knowledge.bundle_dir() / "applications/payments.md").exists()
    log = (knowledge.bundle_dir() / "log.md").read_text(encoding="utf-8")
    assert "**Removal**" in log and "**Deprecation**" in log and "confirmed by human:sam" in log


def test_inbox_file_refuses_files_outside_the_inbox(home, tmp_path):
    inside = home / "knowledge-inbox" / "a.md"
    inside.write_text("x", encoding="utf-8")
    assert knowledge.inbox_file(str(inside)) == inside.resolve()
    outside = tmp_path.parent / "secret.md"
    outside.write_text("x", encoding="utf-8")
    for raw in (str(outside), str(home / "knowledge-inbox" / ".." / "triage.yaml"), str(home / "knowledge-inbox")):
        with pytest.raises(okf.OKFError):
            knowledge.inbox_file(raw)
    link = home / "knowledge-inbox" / "link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks need privileges on this OS")
    with pytest.raises(okf.OKFError, match="symbolic link"):
        knowledge.inbox_file(str(link))


def test_import_reference_and_review_queue(home):
    knowledge.seed()
    result = knowledge.import_reference("# Payments\n\nOwned by the payments team.", "Payments Runbook.pdf", "human:alex",
                                        sha256="ab" * 32, converter="markitdown/0.1.9")
    again = knowledge.import_reference("# changed text", "copy.pdf", "human:sam", sha256="ab" * 32)
    assert again["existing"] and again["path"] == result["path"]  # the same file is imported once
    c = knowledge.bundle().read(result["path"])
    assert c.type == "Reference" and okf.trust_tier(c.meta) == "unverified" and c.meta["generated"]["by"] == "markitdown/0.1.9"
    draft = home / "proposals" / "knowledge" / "teams" / "payments.md"
    draft.parent.mkdir()
    draft.write_text("---\ntype: Team\ntitle: Payments team\ndescription: Owns payments.\nstatus: draft\n"
                     "generated: {by: remedigenius-agent, at: '2026-10-21T10:00:00Z'}\n---\n\nTold by Alex.\n", encoding="utf-8")
    queue = knowledge.review_queue()
    assert queue[0]["target"] == "teams/payments-team.md" and queue[0]["type"] == "Team" and not queue[0]["affects_triage"]
    item = knowledge.inspect_file(str(draft))
    assert item["raw"].startswith("---") and item["target_exists"] is False


# ------------------------------------------------------------------ CLI, socket and agent tool

def test_cli_knowledge_views_and_edit(home, capsys):
    (home / "knowledge-inbox" / "fields.json").write_text(json.dumps({
        "title": "Prod", "description": "Production workloads.", "account_id": "111122223333",
        "criticality": "mission_critical", "environment": "production"}), encoding="utf-8")
    cli.main(["knowledge-edit", "save", "--fields", str(home / "knowledge-inbox" / "fields.json"), "--kind", "Account",
              "--by", "human:alex", "--verify"])
    assert json.loads(capsys.readouterr().out)["path"] == "accounts/prod.md"
    cli.main(["knowledge"])
    out = capsys.readouterr().out
    assert "Changing priorities now: 0 applications, 1 accounts" in out and "okf_version" not in out
    cli.main(["knowledge", "search", "production", "workloads", "--json"])
    assert json.loads(capsys.readouterr().out)[0]["path"] == "accounts/prod.md"
    cli.main(["knowledge", "show", "accounts/prod.md", "--json"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["affects_triage"] and shown["raw"].startswith("---") and shown["trust"] == "human-reviewed"
    cli.main(["knowledge", "validate", "--json"])
    assert json.loads(capsys.readouterr().out)["errors"] == 0
    with pytest.raises(SystemExit, match="not a file in the knowledge inbox"):
        cli.main(["knowledge-edit", "save", "--file", str(Path(cli.__file__)), "--by", "human:alex"])


def test_approving_knowledge_rescores_the_stored_board_without_aws(home, capsys):
    from rgtriage import store
    (home / "triage.yaml").write_text("name: t\naccounts:\n  - name: desk\n    account_id: '111122223333'\n", encoding="utf-8")
    findings, _ = prioritize.prioritize([finding()], cli.config.load(), {}, {})
    scan = {"version": "t", "scanned_at": "2026-10-21T00:00:00Z", "profile": {"name": "t", "accounts": []}, "findings": findings,
            "coverage": [{"source": "securityhub", "account": "desk", "account_id": "111122223333", "region": "us-east-1",
                          "status": "ok", "count": 1}], "onboarding": {}}
    store.mark_changes(scan)
    scan["issues"] = prioritize.build_issues(findings)
    store.cap_findings(scan, 100)
    store.save_scan(scan)
    before = findings[0]["priority"]
    (home / "knowledge-inbox" / "app.json").write_text(json.dumps({
        "title": "Payments", "description": "Card API.", "match_tags": "app=payments", "criticality": "test_development"}), encoding="utf-8")
    cli.main(["knowledge-edit", "save", "--fields", str(home / "knowledge-inbox" / "app.json"), "--kind", "Application",
              "--by", "human:alex", "--verify"])
    result = json.loads(capsys.readouterr().out)
    assert result["rescored"] == {"findings": 1, "changed_priority": int(before != store.load_latest()["findings"][0]["priority"])}
    latest = store.load_latest()
    assert any("knowledge applications/payments.md" in r for r in latest["findings"][0]["reasons"])
    assert latest["knowledge"]["used_in"] == 1
    assert "Knowledge: 1 organization concepts (1 reviewed) · business context applied to 1 of 1 findings" in (home / "board.md").read_text(encoding="utf-8")
    cli.main(["knowledge-edit", "remove", "--path", "applications/payments.md", "--by", "human:alex"])
    capsys.readouterr()
    assert not any("knowledge" in r for r in store.load_latest()["findings"][0]["reasons"])  # removal applies at once too


def test_socket_allows_knowledge_and_the_agent_tool_is_read_only():
    assert {"knowledge", "knowledge-edit"} <= server.ALLOWED and "knowledge-edit" in server.STATE_CHANGING
    spec = importlib.util.spec_from_file_location("rg_triage_plugin_k", ROOT / "profiles/remedigenius/plugins/rg-triage/__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    calls = []
    plugin._run = lambda args, timeout=300: calls.append(args) or "ok"
    plugin.handle({"action": "knowledge", "view": "search", "query": "payments"})
    plugin.handle({"action": "knowledge", "view": "for", "ref": "abc"})
    assert calls == [["knowledge", "search", "payments", "--limit", "8"], ["knowledge", "for", "abc"]]
    assert "must be one of" in plugin.handle({"action": "knowledge", "view": "save"})
    assert "knowledge-edit" not in plugin.ACTIONS


def test_board_shows_knowledge_line():
    scan = {"scanned_at": "2026-10-21T00:00:00", "profile": {"name": "t"}, "issues": [], "findings": [], "coverage": [],
            "changes": {}, "knowledge": {"organization": 4, "human_reviewed": 3, "used_in": 12, "findings": 40, "review_queue": 2, "stale": ["a"],
                                         "gaps": ["5 open P1/P2 findings sit on resources the desk cannot map"]}}
    board = digest.markdown(scan)
    assert "Knowledge: 4 organization concepts (3 reviewed) · business context applied to 12 of 40 findings · 2 draft(s) to review · 1 stale" in board
    assert "Knowledge gap: 5 open P1/P2" in board


# ------------------------------------------------------------------ the generated wiki view (Hermes WebUI)

def test_wiki_view_is_generated_from_the_bundle(home):
    knowledge.seed()
    b = knowledge.bundle()
    concept(b, "applications/payments.md", {"type": "Application", "title": "Payments", "description": "Card payments.",
                                            "remedigenius": {"match_tags": {"app": "payments"}}, **REVIEWED}, "Runs in prod.")
    concept(b, "references/runbook.md", {"type": "Reference", "title": "Runbook", "description": "Imported."})
    b.log("Creation", "[Payments](/applications/payments.md) by human:alex", day="2026-10-21")
    dest = home / "rg-wiki"
    counts = knowledge.export_wiki(dest)
    assert counts["entities"] == 1 and counts["raw"] == 1 and counts["concepts"] >= 20
    assert counts["pages"] == counts["entities"] + counts["concepts"] + counts["raw"]
    page = dest / "entities/applications-payments.md"
    meta, body = okf.parse(page.read_text(encoding="utf-8"))
    assert meta["title"] == "Payments" and meta["remedigenius"]["match_tags"] == {"app": "payments"}  # frontmatter kept
    assert meta["updated_by"].startswith("human:")  # the WebUI shows the reviewer as last writer, not "ai-agent"
    shipped, _ = okf.parse((dest / "concepts/data-protection.md").read_text(encoding="utf-8"))
    assert shipped["updated_by"].startswith("remedigenius-ce")
    assert body.startswith("> Generated from applications/payments.md (human-reviewed). Edit in the dashboard Knowledge tab.")
    assert "Runs in prod." in body
    assert (dest / "concepts/data-protection.md").exists() and (dest / "raw/runbook.md").exists()
    index = (dest / "index.md").read_text(encoding="utf-8")
    assert "## Application" in index and "applications/payments.md, human-reviewed, stable" in index
    assert "## Guide" in index and "concepts/" in index and "## Reference" in index
    assert "Do not edit; edit in the dashboard Knowledge tab." in (dest / "SCHEMA.md").read_text(encoding="utf-8")
    assert "## [2026-10-21] Creation | /applications/payments.md" in (dest / "log.md").read_text(encoding="utf-8")
    if os.name == "posix":
        assert page.stat().st_mode & 0o777 == 0o644 and dest.stat().st_mode & 0o777 == 0o755


def test_wiki_view_drops_pages_of_removed_concepts(home):
    knowledge.seed()
    b = knowledge.bundle()
    concept(b, "notes/first.md", {"type": "Note", "title": "First", "description": "x"})
    dest = home / "rg-wiki"
    knowledge.export_wiki(dest)
    assert (dest / "entities/notes-first.md").exists()
    b.path_of("notes/first.md").unlink()
    knowledge.export_wiki(dest)
    assert not (dest / "entities/notes-first.md").exists()
    assert not any(p.name.startswith(".build-") for p in dest.iterdir())  # the staging folder is gone


def test_wiki_export_writes_only_inside_dest_and_never_follows_links(home, tmp_path):
    b = knowledge.bundle()
    concept(b, "notes/escape.md", {"type": "Note", "title": "../../outside", "description": "x"})
    dest = home / "rg-wiki"
    knowledge.export_wiki(dest)
    assert all(dest in p.parents for p in dest.rglob("*"))  # nothing escaped the destination
    assert all(p.is_dir() or p.suffix == ".md" for p in dest.rglob("*"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    try:
        (dest / "raw").symlink_to(outside, target_is_directory=True)
        (b.root / "notes/link.md").symlink_to(outside / "keep.txt")
    except OSError:
        pytest.skip("symlinks need privileges on this OS")
    knowledge.export_wiki(dest)
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"  # never written through
    assert not (dest / "raw/keep.txt").exists() and not (dest / "entities/notes-link.md").exists()


def test_wiki_export_failure_never_breaks_a_knowledge_change(home, monkeypatch, capsys):
    from rgtriage import store
    (home / "triage.yaml").write_text("name: t\naccounts:\n  - name: desk\n    account_id: '111122223333'\n", encoding="utf-8")
    findings, _ = prioritize.prioritize([finding()], cli.config.load(), {}, {})
    store.save_scan({"version": "t", "scanned_at": "2026-10-21T00:00:00Z", "profile": {"name": "t", "accounts": []},
                     "findings": findings, "coverage": [], "onboarding": {}, "changes": {},
                     "issues": prioritize.build_issues(findings)})
    monkeypatch.setenv("RGTRIAGE_WIKI_DIR", str(home / "rg-wiki"))

    def broken(*_args, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(knowledge, "export_wiki", broken)
    assert cli.rescore()["findings"] == 1
    assert "wiki export failed: OSError: disk full" in capsys.readouterr().err
    assert not (home / "rg-wiki").exists()


# ------------------------------------------------------------------ Knowledge tab backend helpers

@pytest.fixture
def tab():
    pytest.importorskip("fastapi")
    path = ROOT / "profiles/remedigenius/dashboard-plugins/rg-knowledge/dashboard/plugin_api.py"
    spec = importlib.util.spec_from_file_location("rg_knowledge_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_drafts_are_valid_okf_drafts_without_review(tab):
    text = tab._draft_text({"type": "Application", "title": "Payments: card API", "description": "Takes \"card\" payments.",
                            "body": "Runs in prod.", "evidence": "the payments team owns it", "criticality": "mission_critical",
                            "match_tags": {"app": "payments"}, "owner_team": "Payments Team"},
                           "references/runbook.md", "custom/deepseek-v4.1-flash")
    meta, body = okf.parse(text)
    assert meta["status"] == "draft" and "verified" not in meta and meta["generated"]["by"] == "custom/deepseek-v4.1-flash"
    assert meta["remedigenius"] == {"criticality": "mission_critical", "match_tags": {"app": "payments"}, "owner": "/teams/payments-team.md"}
    assert meta["sources"][0]["resource"] == "/references/runbook.md" and "[^doc]" in body
    assert tab._is_concept("---\ntype: Note\n---\nx") and not tab._is_concept("# just markdown")
    with pytest.raises(tab.HTTPException):
        tab._inside(Path("/etc/passwd"), Path("/opt/data/proposals/knowledge"))
    assert tab._actor("alex") == "human:alex"
    with pytest.raises(tab.HTTPException):
        tab._actor("alex; rm -rf /")
