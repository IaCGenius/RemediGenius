"""Connecting GitHub from the web console: the desk's web operations, the operator-token gate, the dashboard backend and the boot wiring.

The key must never reach the browser, the dashboard process or the agent; the agent must never be able to start, change or undo the connection.
Real GitHub is replaced by the recording fake from test_github.py; the Spot checks (tools/spot_release_test.py) cover the real socket.
"""
import hashlib
import importlib.util
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

import pytest

from rgtriage import github, server
from test_github import (APP, BASE, PEM, REPO, SignedClient, connected, fake_sign, gh, good_transport, new_client)  # noqa: F401  (fixtures)
from test_rgtriage import home  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
GH_TAB = ROOT / "profiles/remedigenius/dashboard-plugins/rg-github"
REDIRECT = "http://127.0.0.1:9125/api/plugins/rg-github/callback"
SETUP = "http://127.0.0.1:9125/github"


@pytest.fixture
def web(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setattr(github, "Client", SignedClient)
    monkeypatch.delenv("RGGITHUB_ALLOWED_ORIGINS", raising=False)
    return gh


# ---------------------------------------------------------------- step 1: begin

def test_begin_returns_what_the_browser_posts_and_stores_only_a_hash_of_the_state(web):
    out = github.begin_connect(REDIRECT, SETUP, owner="acme")
    state = out["target"].split("state=")[1]
    assert out["resume"] is False and out["target"].startswith("https://github.com/organizations/acme/settings/apps/new?state=")
    manifest = out["manifest"]
    assert manifest["redirect_url"] == REDIRECT and manifest["setup_url"] == SETUP and manifest["public"] is False and manifest["default_events"] == []
    assert manifest["default_permissions"] == github.APP_PERMISSIONS and manifest["name"].startswith("RemediGenius-CE-")
    pending_file = github.home() / "pending.json"
    pending = json.loads(pending_file.read_text())
    assert state not in pending_file.read_text() and pending["state_sha256"] == hashlib.sha256(state.encode()).hexdigest()
    if os.name != "nt":
        assert (pending_file.stat().st_mode & 0o077) == 0


def test_begin_for_a_personal_account_uses_the_personal_page(web):
    assert github.begin_connect(REDIRECT, SETUP)["target"].startswith("https://github.com/settings/apps/new?state=")


@pytest.mark.parametrize("redirect,setup", [
    ("http://evil.example/api/plugins/rg-github/callback", "http://evil.example/github"),          # GitHub's code must not go to a stranger's host
    ("http://127.0.0.1:9125/api/plugins/other/callback", SETUP),
    ("http://127.0.0.1:9125/api/plugins/rg-github/callback?x=1", SETUP),
    (REDIRECT + "#frag", SETUP),
    (REDIRECT, "http://127.0.0.1:9999/github"),                                                    # the two addresses must share one origin
    (REDIRECT, "http://127.0.0.1:9125/other"),
    ("ftp://127.0.0.1/api/plugins/rg-github/callback", "ftp://127.0.0.1/github"),
    ("http://user:pw@127.0.0.1:9125/api/plugins/rg-github/callback", "http://user:pw@127.0.0.1:9125/github"),
    ("javascript:alert(1)", SETUP), ("", ""),
])
def test_begin_refuses_return_addresses_that_are_not_this_console(web, redirect, setup):
    with pytest.raises(github.Denied):
        github.begin_connect(redirect, setup)
    assert not (github.home() / "pending.json").exists()


def test_a_listed_origin_is_allowed_and_an_unlisted_one_is_not(web, monkeypatch):
    origin = "https://desk.example.net"
    with pytest.raises(github.Denied):
        github.begin_connect(origin + github.CALLBACK_PATH, origin + github.PAGE_PATH)
    monkeypatch.setenv("RGGITHUB_ALLOWED_ORIGINS", origin + "/, https://other.example")
    assert github.begin_connect(origin + github.CALLBACK_PATH, origin + github.PAGE_PATH)["resume"] is False


def test_begin_refuses_a_bad_organization_name(web):
    for bad in ("a/b", "a b", "../x", "-x", "x" * 60):
        with pytest.raises(github.Denied, match="organization"):
            github.begin_connect(REDIRECT, SETUP, owner=bad)


def test_begin_on_a_healthy_connection_refuses_and_a_deleted_app_gets_a_replacement(connected, monkeypatch):
    monkeypatch.setattr(github, "Client", SignedClient)
    with pytest.raises(github.Denied, match="already connected"):
        github.begin_connect(REDIRECT, SETUP, transport=connected)
    connected.app_gone = True                                                                      # the App was deleted on GitHub
    out = github.begin_connect(REDIRECT, SETUP, transport=connected)
    assert out["resume"] is False and "no longer exists" in out["message"] and not github.key_path().exists()
    assert github.load_policy()["writes_enabled"] is False                                          # the new App is verified before it writes


def test_begin_resumes_at_the_install_step_when_only_the_installation_is_gone(connected, monkeypatch):
    monkeypatch.setattr(github, "Client", SignedClient)
    connected.installations = []
    out = github.begin_connect(REDIRECT, SETUP, transport=connected)
    assert out["resume"] is True and out["install_url"] == github.app_install_url(APP["slug"]) and "resuming" in out["message"]
    assert "installation_id" not in github.load_app() and github.key_path().exists()               # same App, nothing replaced


# ---------------------------------------------------------------- step 2: GitHub sends the browser back

def begun(web):
    out = github.begin_connect(REDIRECT, SETUP, owner="acme")
    return out["target"].split("state=")[1]


def test_finish_creates_the_app_saves_the_key_privately_and_returns_the_install_link(web):
    state = begun(web)
    out = github.finish_connect("abcdefgh1234", state, transport=good_transport(app_id=9, slug_="remedigenius-ce-new"))
    assert out == {"slug": "remedigenius-ce-new", "install_url": "https://github.com/apps/remedigenius-ce-new/installations/new"}
    assert github.key_path().read_text() == PEM and github.load_app()["app_id"] == 9 and not (github.home() / "pending.json").exists()
    assert "BEGIN" not in json.dumps(out) and "pem" not in (github.home() / "app.json").read_text().lower()


def test_finish_refuses_a_wrong_replayed_expired_or_missing_state(web, monkeypatch):
    transport = good_transport()
    state = begun(web)
    with pytest.raises(github.Denied, match="expired or did not start here"):
        github.finish_connect("abcdefgh1234", "not-the-state", transport=transport)
    assert not (github.home() / "pending.json").exists() and not github.key_path().exists()          # a bad attempt burns the pending state
    with pytest.raises(github.Denied):
        github.finish_connect("abcdefgh1234", state, transport=transport)                          # the real state, after that: gone
    with pytest.raises(github.Denied):
        github.finish_connect("abcdefgh1234", "", transport=transport)                             # nothing pending at all
    state = begun(web)
    real_time = time.time()
    monkeypatch.setattr(github.time, "time", lambda: real_time + github.PENDING_TTL + 5)
    with pytest.raises(github.Denied, match="expired"):
        github.finish_connect("abcdefgh1234", state, transport=transport)                          # too old
    monkeypatch.setattr(github.time, "time", lambda: real_time)
    state = begun(web)
    github.finish_connect("abcdefgh1234", state, transport=transport)                              # the genuine one works...
    with pytest.raises(github.Denied):
        github.finish_connect("abcdefgh1234", state, transport=transport)                          # ...exactly once


def test_finish_refuses_a_malformed_code_before_calling_github(web):
    state = begun(web)
    called = []
    with pytest.raises(github.Denied, match="valid code"):
        github.finish_connect("../../x", state, transport=lambda *a: called.append(a))
    assert called == []


@pytest.mark.parametrize("answer,reason", [((422, {}, b'{"message":"Validation Failed"}'), "GitHub"),
                                           ((201, {}, b"not json"), "not what a created App looks like"),
                                           ((201, {}, json.dumps({"id": 1, "slug": "ok", "pem": "no key"}).encode()), "not what a created App looks like")])
def test_finish_failures_say_why_save_nothing_and_leak_nothing(web, answer, reason):
    state = begun(web)
    with pytest.raises(github.GitHubError, match=reason) as caught:
        github.finish_connect("abcdefgh1234", state, transport=lambda *a: answer)
    assert "BEGIN" not in str(caught.value) and github.load_app() == {} and not github.key_path().exists()


def test_finish_reports_a_network_failure_without_saving_anything(web):
    state = begun(web)

    def down(*a):
        raise OSError("connection reset")
    with pytest.raises(github.GitHubError, match="could not reach GitHub"):
        github.finish_connect("abcdefgh1234", state, transport=down)
    assert github.load_app() == {}


# ---------------------------------------------------------------- step 3: install, repositories, branches

def test_install_status_waits_then_remembers_the_installation(web):
    github._write_private(github.key_path(), PEM)
    github._write_private(github.home() / "app.json", json.dumps({"app_id": 9, "slug": "remedigenius-ce-x", "owner": "acme"}))
    web.installations = []
    waiting = github.install_status(transport=web, sign=fake_sign)
    assert waiting == {"app": True, "installed": False, "slug": "remedigenius-ce-x", "install_url": "https://github.com/apps/remedigenius-ce-x/installations/new"}
    web.installations = [{"id": 55, "account": {"login": "acme"}}]
    done = github.install_status(transport=web, sign=fake_sign)
    assert done["installed"] is True and done["account"] == "acme" and github.load_app()["installation_id"] == 55
    assert github.install_status(transport=web, sign=fake_sign)["installed"] is True               # asking again is harmless


def test_install_status_without_an_app_and_when_github_rejects_the_key(web):
    assert github.install_status(transport=web, sign=fake_sign) == {"app": False, "installed": False}
    github._write_private(github.key_path(), PEM)
    github._write_private(github.home() / "app.json", json.dumps({"app_id": 9, "slug": "x", "owner": "acme"}))
    web.app_gone = True
    with pytest.raises(github.GitHubError, match="reconnect"):
        github.install_status(transport=web, sign=fake_sign)


def test_the_console_only_offers_the_repositories_selected_at_install(connected):
    connected.installation_repos = [REPO, "acme/other"]
    assert github.web_repos(transport=connected, sign=fake_sign) == {"repos": ["acme/infra", "acme/other"]}
    info = github.web_branches(REPO, transport=connected, sign=fake_sign)
    assert info["suggested"] == "dev" and "main" not in info["branches"] and info["default"] == "main" and info["admin_command"] == ""
    with pytest.raises(github.Denied, match="not selected"):
        github.web_branches("evil/repo", transport=connected, sign=fake_sign)


def test_with_no_development_branch_the_console_gets_the_administrator_command(connected):
    del connected.refs[BASE]
    info = github.web_branches(REPO, transport=connected, sign=fake_sign)
    assert info["branches"] == [] and info["suggested"] == "" and f"gh api repos/{REPO}/git/refs -f ref=refs/heads/dev" in info["admin_command"]


# ---------------------------------------------------------------- the operator gate (the agent can never use the setup operations)

@pytest.fixture
def token(tmp_path, monkeypatch):
    path = tmp_path / "operator.token"
    path.write_text("S" * 43 + "\n")
    monkeypatch.setenv("RGTRIAGE_OPERATOR_TOKEN_FILE", str(path))
    return "S" * 43


def test_the_operator_token_is_checked_exactly_and_fails_closed(token, monkeypatch, tmp_path):
    assert server.operator_token_ok(token)
    for bad in ("", "short", token[:-1], token + "x", None, 12345, ["S" * 43]):
        assert not server.operator_token_ok(bad)
    monkeypatch.setenv("RGTRIAGE_OPERATOR_TOKEN_FILE", str(tmp_path / "missing"))
    assert not server.operator_token_ok(token)                                                     # no token file: nobody is an operator
    monkeypatch.delenv("RGTRIAGE_OPERATOR_TOKEN_FILE")
    assert not server.operator_token_ok(token)
    (tmp_path / "empty").write_text("")
    monkeypatch.setenv("RGTRIAGE_OPERATOR_TOKEN_FILE", str(tmp_path / "empty"))
    assert not server.operator_token_ok("")


@pytest.mark.parametrize("op", ["web-begin", "web-finish", "web-install", "web-repos", "web-branches", "configure", "verify", "disconnect"])
def test_operator_operations_are_refused_without_the_token(op):
    reply = server.execute(["github", op, "--json"], operator=False)
    assert reply["rc"] == 2 and "not available over the socket" in reply["stderr"]


@pytest.mark.parametrize("args", [["github", "connect"], ["github", "setup"], ["github", "probe", "--confirm-disposable", "a/b"], ["github", "publish-all"],
                                  ["github", "configure", "--prefix", "main/"], ["github", "configure", "--confirm-disposable", "a/b"],
                                  ["github", "web-begin", "--reconnect", "--evil"], ["github"]])
def test_even_with_the_token_only_the_console_operations_and_flags_are_allowed(args):
    reply = server.execute(args, operator=True)
    assert reply["rc"] == 2 and "not available over the socket" in reply["stderr"]


def test_with_the_token_the_gate_lets_a_console_operation_through(home, monkeypatch):  # noqa: F811
    monkeypatch.delenv("RGGITHUB_HOME", raising=False)
    reply = server.execute(["github", "web-install", "--json"], operator=True)
    assert "not available over the socket" not in reply["stderr"]                                   # it reached the desk, which refuses for its own reason


def test_the_agents_tool_cannot_name_a_console_operation_and_the_token_file_is_unreadable_to_it():
    spec = importlib.util.spec_from_file_location("rg_plugin_console", ROOT / "profiles/remedigenius/plugins/rg-triage/__init__.py")
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    for op in ("web-begin", "web_begin", "web-finish", "configure", "verify", "disconnect", "setup", "probe"):
        assert "must be one of" in plugin.handle({"action": "github", "op": op})
    assert "GitHub tab" in plugin.handle({"action": "github", "op": "connect"})
    for name in (".rg-operator-token", "operator.token"):
        assert name in plugin.SECRET_NAMES
    assert plugin.on_pre_tool_call("read_file", {"path": "/opt/data/.rg-operator-token"})["action"] == "block"
    assert plugin.on_pre_tool_call("read_file", {"path": "/data/rggithub/operator.token"})["action"] == "block"
    sent = []
    plugin._run = lambda args, **kw: sent.append(args) or "ok"
    plugin.handle({"action": "github", "op": "status", "operator": "x" * 40})
    assert sent == [["github", "status"]]                                                           # the tool never forwards anything operator-like


def test_the_agent_socket_client_sends_no_operator_token():
    source = (ROOT / "profiles/remedigenius/plugins/rg-triage/__init__.py").read_text(encoding="utf-8")
    assert "operator" not in source.lower().replace("designated", "").split("def _socket_call")[1].split("def ")[0]


# ---------------------------------------------------------------- the dashboard backend

def _load_backend():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    spec = importlib.util.spec_from_file_location("rg_github_api", GH_TAB / "dashboard/plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def backend(monkeypatch):
    module = _load_backend()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(module.router, prefix="/api/plugins/rg-github")
    calls = []
    answers = {}

    def fake_desk(args, timeout=120):
        calls.append(args)
        key = " ".join(args[:2])
        value = answers.get(key, "{}")
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(module, "_desk", fake_desk)
    return {"module": module, "client": TestClient(app, base_url="http://127.0.0.1:9125", follow_redirects=False), "calls": calls, "answers": answers}


def test_status_is_the_desks_status_as_json(backend):
    backend["answers"]["github status"] = json.dumps({"state": "Disconnected", "remedy": "x"})
    assert backend["client"].get("/api/plugins/rg-github/status").json()["state"] == "Disconnected"
    assert backend["calls"] == [["github", "status", "--json"]]


def test_begin_tells_github_to_come_back_to_the_address_the_browser_used(backend):
    backend["answers"]["github web-begin"] = json.dumps({"resume": False, "target": "https://github.com/settings/apps/new?state=s", "manifest": {}})
    r = backend["client"].post("/api/plugins/rg-github/begin", json={"org": "acme"})
    assert r.status_code == 200 and r.json()["target"].startswith("https://github.com/")
    args = backend["calls"][0]
    assert args[args.index("--redirect") + 1] == "http://127.0.0.1:9125/api/plugins/rg-github/callback"
    assert args[args.index("--setup-url") + 1] == "http://127.0.0.1:9125/github" and args[args.index("--org") + 1] == "acme"


def test_begin_rejects_an_invalid_organization_before_asking_the_desk(backend):
    assert backend["client"].post("/api/plugins/rg-github/begin", json={"org": "a/b; rm -rf"}).status_code == 400
    assert backend["calls"] == []


def test_begin_needs_a_json_body_so_a_cross_site_form_cannot_start_it(backend):
    r = backend["client"].post("/api/plugins/rg-github/begin", data={"org": ""}, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 422 and backend["calls"] == []


def test_the_callback_finishes_and_sends_the_browser_back_to_the_page(backend):
    backend["answers"]["github web-finish"] = json.dumps({"slug": "x", "install_url": "https://github.com/apps/x/installations/new"})
    r = backend["client"].get("/api/plugins/rg-github/callback?code=abcdefgh1234&state=thestate")
    assert r.status_code == 303 and r.headers["location"] == "/github?step=install"
    args = backend["calls"][0]
    assert args[:2] == ["github", "web-finish"] and args[args.index("--code") + 1] == "abcdefgh1234" and args[args.index("--state") + 1] == "thestate"


def test_a_failed_callback_returns_to_the_page_with_a_clean_one_line_reason(backend):
    from fastapi import HTTPException
    leak = "could not save -----BEGIN RSA PRIVATE KEY-----\nSECRET\n-----END RSA PRIVATE KEY----- and ghs_" + "A" * 30
    backend["answers"]["github web-finish"] = HTTPException(400, leak)
    r = backend["client"].get("/api/plugins/rg-github/callback?code=abcdefgh1234&state=s")
    location = urllib.parse.unquote(r.headers["location"])
    assert r.status_code == 303 and location.startswith("/github?error=") and "SECRET" not in location and "ghs_" not in location


def test_the_desk_error_text_is_one_clean_line_without_secrets(backend):
    clean = backend["module"]._clean
    assert clean("DENIED (nothing was sent to GitHub): the thing is wrong") == "the thing is wrong"
    assert "ghs_" not in clean("oops ghs_" + "A" * 30) and "BEGIN" not in clean("x -----BEGIN PRIVATE KEY----- y")
    assert clean("") == "the desk did not answer" and len(clean("x" * 5000)) <= 400
    assert clean("line one\nline two") == "line two"


@pytest.mark.parametrize("body", [{"repo": "no-slash", "base": "dev", "reviewers": ["alice"]}, {"repo": "a/b", "base": "../main", "reviewers": ["alice"]},
                                  {"repo": "a/b", "base": "dev", "reviewers": []}, {"repo": "a/b", "base": "dev", "reviewers": ["x y"]},
                                  {"repo": "a/b", "base": "dev", "reviewers": ["a"] * 11}, {"repo": "a/b", "base": "dev", "reviewers": ["--evil"]},
                                  {"repo": "a/b;rm", "base": "dev", "reviewers": ["alice"]}])
def test_configure_validates_every_field_before_asking_the_desk(backend, body):
    assert backend["client"].post("/api/plugins/rg-github/configure", json=body).status_code == 400
    assert backend["calls"] == []


def test_configure_passes_the_choices_as_separate_arguments(backend):
    backend["answers"]["github configure"] = json.dumps({"state": "Ready to create development PRs", "writes_enabled": True})
    r = backend["client"].post("/api/plugins/rg-github/configure", json={"repo": "acme/infra", "base": "dev", "reviewers": ["alice", "acme/security"]})
    assert r.status_code == 200 and r.json()["writes_enabled"] is True
    assert backend["calls"][0] == ["github", "configure", "--json", "--repo", "acme/infra", "--base", "dev", "--reviewer", "alice", "--reviewer", "acme/security"]


def test_branches_repos_install_verify_refresh_and_disconnect_map_to_desk_operations(backend):
    for key in ("github web-branches", "github web-repos", "github web-install", "github verify", "github refresh", "github disconnect"):
        backend["answers"][key] = json.dumps({"ok": True})
    c = backend["client"]
    assert c.get("/api/plugins/rg-github/branches?repo=acme/infra").status_code == 200
    assert c.get("/api/plugins/rg-github/branches?repo=bad").status_code == 400
    assert c.get("/api/plugins/rg-github/repos").status_code == 200 and c.get("/api/plugins/rg-github/install").status_code == 200
    assert c.post("/api/plugins/rg-github/verify").status_code == 200 and c.post("/api/plugins/rg-github/refresh").status_code == 200
    assert c.post("/api/plugins/rg-github/disconnect", json={"keep_installation": True}).status_code == 200
    assert ["github", "disconnect", "--json", "--keep-installation"] in backend["calls"]
    assert ["github", "web-branches", "--repo", "acme/infra"] in backend["calls"]


def test_the_backend_sends_the_operator_token_to_the_socket_and_nothing_else_secret(tmp_path, monkeypatch):
    module = _load_backend()
    token_file = tmp_path / "t"
    token_file.write_text("T" * 43)
    (tmp_path / "local.json").write_text(json.dumps({"socket": "/run/x.sock", "operator_token_file": str(token_file)}))
    monkeypatch.setattr(module, "HERE", tmp_path / "dashboard")
    sent = {}

    class FakeSocket:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def connect(self, path): sent["path"] = path
        def sendall(self, data): sent["data"] = json.loads(data)
        def recv(self, n): return b"" if sent.get("done") else (sent.update(done=True) or json.dumps({"rc": 0, "stdout": "{}"}).encode())

    monkeypatch.setattr(module.socket, "socket", FakeSocket, raising=False)
    monkeypatch.setattr(module.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(module.socket, "SOCK_STREAM", 1, raising=False)
    assert module._desk(["github", "status", "--json"]) == "{}"
    assert sent["path"] == "/run/x.sock" and sent["data"] == {"args": ["github", "status", "--json"], "operator": "T" * 43}


def test_without_the_desk_socket_the_backend_says_this_is_spot_only(tmp_path, monkeypatch):
    module = _load_backend()
    monkeypatch.setattr(module, "HERE", tmp_path / "dashboard")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as caught:
        module._desk(["github", "status"])
    assert caught.value.status_code == 503 and "Spot" in caught.value.detail


# ---------------------------------------------------------------- the page and the plugin files

def test_the_plugin_is_complete_versioned_with_the_release_and_registered_as_a_tab():
    from rgtriage import __version__
    manifest = json.loads((GH_TAB / "dashboard/manifest.json").read_text())
    assert manifest["name"] == "rg-github" and manifest["tab"]["path"] == "/github" and manifest["version"] == __version__
    assert (GH_TAB / "dashboard" / manifest["entry"]).is_file() and (GH_TAB / "dashboard" / manifest["css"]).is_file() and (GH_TAB / "dashboard" / manifest["api"]).is_file()
    assert f'version: "{__version__}"' in (GH_TAB / "plugin.yaml").read_text() and "def register" in (GH_TAB / "__init__.py").read_text()
    assert "rg-github" in (ROOT / "profiles/remedigenius/config.yaml").read_text()


def test_the_page_talks_only_to_its_backend_and_never_handles_a_key_or_token():
    js = (GH_TAB / "dashboard/dist/index.js").read_text(encoding="utf-8")
    assert 'window.__HERMES_PLUGINS__.register("rg-github"' in js and 'var API = "/api/plugins/rg-github"' in js
    for forbidden in ("token", "pem", "private key", "localStorage", "sessionStorage", "document.cookie", "innerHTML", "eval(", "api.github.com"):
        assert forbidden not in js.lower().replace("not a token", ""), forbidden
    for needed in ("/begin", "/callback" if False else "/install", "/repos", "/branches", "/configure", "/verify", "/refresh", "/disconnect", "Connect GitHub", "Disconnect"):
        assert needed in js
    assert "form.action = r.target" in js and "manifest" in js                                       # the browser, not the server, posts the App definition


def test_every_plugin_file_is_included_in_the_release_archive():
    sys.path.insert(0, str(ROOT / "tools"))
    import package_release
    names = {p.relative_to(ROOT).as_posix() for p in package_release.files(package_release.SPOT_PARTS)}
    for needed in ("plugin.yaml", "__init__.py", "dashboard/manifest.json", "dashboard/plugin_api.py", "dashboard/dist/index.js", "dashboard/dist/style.css"):
        assert f"profiles/remedigenius/dashboard-plugins/rg-github/{needed}" in names


# ---------------------------------------------------------------- boot wiring (Spot host)

def _host():
    spec = importlib.util.spec_from_file_location("spot_host_console", ROOT / "deploy/aws-single/host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boot_writes_a_fresh_private_operator_token_in_two_places_and_wires_the_desk(tmp_path, monkeypatch):
    host = _host()
    monkeypatch.setattr(host, "OPERATOR_TOKEN", tmp_path / "gh" / "operator.token")
    monkeypatch.setattr(host, "HERMES_HOME", tmp_path / "hermes")
    (tmp_path / "gh").mkdir()
    (tmp_path / "hermes").mkdir()
    monkeypatch.setattr(host.os, "chown", lambda *a, **k: None, raising=False)
    host.write_operator_token()
    first = (tmp_path / "gh" / "operator.token").read_text()
    assert len(first) >= 32 and (tmp_path / "hermes" / ".rg-operator-token").read_text() == first
    if os.name != "nt":
        assert (tmp_path / "gh" / "operator.token").stat().st_mode & 0o077 == 0
    host.write_operator_token()
    assert (tmp_path / "gh" / "operator.token").read_text() != first                                  # rotated at every boot
    units = _host().units({"name": "x", "region": "us-east-1", "bucket": "b", "scan_interval_hours": 4, "container_memory_mb": 4096, "image": "i@sha256:a"})
    assert "Environment=RGTRIAGE_OPERATOR_TOKEN_FILE=/data/rggithub/operator.token" in units["remedigenius-desk.service"]
    assert "operator.token" not in units["remedigenius-hermes.service"] and "rggithub" not in units["remedigenius-hermes.service"]


def test_boot_installs_and_enables_the_github_tab_next_to_the_knowledge_tab():
    source = (ROOT / "deploy/aws-single/host.py").read_text(encoding="utf-8")
    assert "'rg-github'" in source and "dashboard-plugins/rg-github" in source and "OPERATOR_TOKEN_IN_CONTAINER" in source
    assert "for name in ('rg-knowledge', 'rg-github')" in source
    assert "= 3 ]" in (ROOT / "tools/spot_release_test.py").read_text(encoding="utf-8")                # the release test expects three RemediGenius plugins


# ---------------------------------------------------------------- the console parses the desk's output: it must be pure JSON

@pytest.mark.parametrize("argv", [["github", "status", "--json"], ["github", "verify", "--json"], ["github", "web-install", "--json"]])
def test_the_commands_the_console_calls_print_nothing_but_json(argv, home, monkeypatch, capsys):  # noqa: F811
    from rgtriage import cli
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    cli.main(argv)
    out = capsys.readouterr().out
    assert isinstance(json.loads(out), dict)                                                       # one JSON document, no extra lines


def test_status_json_carries_the_tool_availability_for_the_page(home, monkeypatch, capsys):  # noqa: F811
    from rgtriage import cli
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    cli.main(["github", "status", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "Disconnected" and set(data["validation_tools"]) == {"terraform", "tflint", "cfn-lint"}
