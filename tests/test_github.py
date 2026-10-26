"""GitHub integration: policy gate, App auth, states, publish workflow and the things that must never reach GitHub.

All of this runs against an in-memory fake of the GitHub REST API (`FakeGitHub`) that records every request, so the tests can
prove what was *not* sent. Real-GitHub checks live in docs/GITHUB-EVIDENCE.md (run against a disposable repository).
"""
import base64
import hashlib
import io
import json
import re
import shutil
import tarfile
import time
import urllib.parse
from pathlib import Path

import pytest

from rgtriage import github, server, store, validators
from test_rgtriage import home  # noqa: F401  (fixture: RGTRIAGE_HOME in a temp folder)

REPO, BASE, DEFAULT = "acme/infra", "dev", "main"
POLICY = {"repo": REPO, "base": BASE, "branch_prefix": "feature/remedigenius/", "reviewers": ["alice"], "writes_enabled": False}
APP = {"app_id": 4242, "slug": "remedigenius-ce-abc", "owner": "acme", "installation_id": 77}
GOOD_RULES = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1, "dismiss_stale_reviews_on_push": True}},
              {"type": "non_fast_forward"}, {"type": "deletion"}, {"type": "required_status_checks"}]
TF = b'resource "aws_s3_bucket" "data" {\n  bucket = "example"\n}\n'


class FakeGitHub:
    """Just enough of the GitHub REST API for the desk: refs, git objects, PRs, rules, installation tokens."""

    def __init__(self, rules=None, users=None):
        self.requests, self.blobs, self.trees, self.commits, self.refs, self.pulls = [], {}, {}, {}, {}, []
        self.rules = {BASE: GOOD_RULES, DEFAULT: GOOD_RULES} if rules is None else rules
        self.users = users or {"alice": "User", "ci-bot": "Bot"}
        self.fail = {}  # (method, regex) -> status, to simulate outages
        self.installation_repos = [REPO]
        blob = self._blob(TF)
        tree = self._tree({"terraform/main.tf": blob})
        c0 = self._commit(tree, [], "acme-dev")
        self.refs = {DEFAULT: c0, BASE: c0}

    def _blob(self, data):
        sha = hashlib.sha1(data).hexdigest()
        self.blobs[sha] = data
        return sha

    def _tree(self, entries):
        sha = hashlib.sha1(json.dumps(entries, sort_keys=True).encode()).hexdigest()
        self.trees[sha] = dict(entries)
        return sha

    def _commit(self, tree, parents, author):
        sha = hashlib.sha1(f"{tree}{parents}{author}{len(self.commits)}".encode()).hexdigest()
        self.commits[sha] = {"tree": tree, "parents": parents, "author": author}
        return sha

    def tarball(self, sha):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for path, blob in self.trees[self.commits[sha]["tree"]].items():
                data = self.blobs[blob]
                info = tarfile.TarInfo(f"acme-infra-{sha[:7]}/{path}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def reply(self, status, body=None, headers=None):
        return status, headers or {}, (b"" if body is None else json.dumps(body).encode())

    def __call__(self, method, url, headers, body):
        parsed = urllib.parse.urlparse(url)
        path, query = urllib.parse.unquote(parsed.path), urllib.parse.parse_qs(parsed.query)
        self.requests.append((method, parsed.hostname, path, body, headers.get("Authorization", "")))
        for (m, pattern), status in self.fail.items():
            if m == method and re.search(pattern, path):
                return self.reply(status, {"message": "simulated failure"})
        if parsed.hostname == "codeload.github.com":
            return 200, {}, self.tarball(path.rsplit("/", 1)[-1])
        r = re.fullmatch
        if (m := r(r"/app/installations/(\d+)/access_tokens", path)) and method == "POST":
            return self.reply(201, {"token": "ghs_" + "T" * 36, "expires_at": "2099-01-01T00:00:00Z"})
        if path == "/installation/repositories":
            return self.reply(200, {"repositories": [{"full_name": n} for n in self.installation_repos]})
        if (m := r(r"/users/([^/]+)", path)):
            return self.reply(200, {"type": self.users[m.group(1)]}) if m.group(1) in self.users else self.reply(404, {"message": "Not Found"})
        if (m := r(r"/repos/acme/infra(/.*)?", path)) is None:
            return self.reply(404, {"message": "Not Found"})
        rest = m.group(1) or ""
        if rest == "":
            return self.reply(200, {"default_branch": DEFAULT})
        if (m := r(r"/branches/([^/]+)", rest)) and method == "GET":
            sha = self.refs.get(m.group(1))
            return self.reply(200, {"commit": {"sha": sha}}) if sha else self.reply(404, {"message": "Branch not found"})
        if (m := r(r"/rules/branches/([^/]+)", rest)):
            return self.reply(200, self.rules.get(m.group(1), []))
        if r(r"/branches/[^/]+/protection", rest) or rest == "/rulesets":
            return self.reply(404, {"message": "Not Found"}) if "protection" in rest else self.reply(200, [])
        if (m := r(r"/tarball/([0-9a-f]+)", rest)):
            return 302, {"Location": f"https://codeload.github.com/acme/infra/legacy.tar.gz/{m.group(1)}"}, b""
        if (m := r(r"/git/ref/heads/(.+)", rest)):
            sha = self.refs.get(m.group(1))
            return self.reply(200, {"object": {"sha": sha}}) if sha else self.reply(404, {"message": "Not Found"})
        if (m := r(r"/commits/([0-9a-f]+)", rest)) and method == "GET":
            return self.reply(200, {"author": {"login": self.commits[m.group(1)]["author"]}})
        if (m := r(r"/git/commits/([0-9a-f]+)", rest)) and method == "GET":
            return self.reply(200, {"tree": {"sha": self.commits[m.group(1)]["tree"]}})
        if rest == "/git/blobs" and method == "POST":
            return self.reply(201, {"sha": self._blob(base64.b64decode(body["content"]))})
        if rest == "/git/trees" and method == "POST":
            tree = dict(self.trees[body["base_tree"]])
            tree.update({e["path"]: e["sha"] for e in body["tree"]})
            return self.reply(201, {"sha": self._tree(tree)})
        if rest == "/git/commits" and method == "POST":
            return self.reply(201, {"sha": self._commit(body["tree"], body["parents"], f"{APP['slug']}[bot]")})
        if rest == "/git/refs" and method == "POST":
            name = body["ref"][len("refs/heads/"):]
            if name in self.refs:
                return self.reply(422, {"message": "Reference already exists"})
            self.refs[name] = body["sha"]
            return self.reply(201, {"ref": body["ref"]})
        if (m := r(r"/git/refs/heads/(.+)", rest)) and method == "PATCH":
            if body["sha"] and self.commits[body["sha"]]["parents"] != [self.refs[m.group(1)]] and not body.get("force"):
                return self.reply(422, {"message": "Update is not a fast forward"})
            self.refs[m.group(1)] = body["sha"]
            return self.reply(200, {})
        if rest == "/pulls" and method == "POST":
            number = len(self.pulls) + 1
            pr = {"number": number, "html_url": f"https://github.com/{REPO}/pull/{number}", "title": body["title"], "body": body["body"], "state": "open",
                  "head": {"ref": body["head"], "sha": self.refs[body["head"]]}, "base": {"ref": body["base"]}, "merged": False, "mergeable_state": "blocked"}
            self.pulls.append(pr)
            return self.reply(201, pr)
        if rest == "/pulls" and method == "GET":
            head = query.get("head", [""])[0].split(":", 1)[-1]
            return self.reply(200, [p for p in self.pulls if p["head"]["ref"] == head and p["state"] == "open"])
        if (m := r(r"/pulls/(\d+)", rest)):
            pr = self.pulls[int(m.group(1)) - 1]
            if method == "PATCH":
                pr.update({k: v for k, v in body.items()})
            pr["head"]["sha"] = self.refs[pr["head"]["ref"]]
            return self.reply(200, pr)
        if (m := r(r"/pulls/(\d+)/requested_reviewers", rest)):
            return self.reply(201, {})
        if (m := r(r"/pulls/(\d+)/reviews", rest)):
            return self.reply(200, [{"user": {"login": "alice", "type": "User"}, "state": "APPROVED"},
                                    {"user": {"login": "ci-bot", "type": "Bot"}, "state": "APPROVED"}])
        if r(r"/commits/[0-9a-f]+/check-runs", rest):
            return self.reply(200, {"check_runs": [{"name": "tf-validate", "conclusion": "success"}]})
        if r(r"/commits/[0-9a-f]+/status", rest):
            return self.reply(200, {"state": "success"})
        return self.reply(404, {"message": f"fake has no {method} {rest}"})

    def sent(self, method=None, pattern=""):
        return [x for x in self.requests if (method is None or x[0] == method) and re.search(pattern, x[2])]


def fake_sign(data):
    return b"signature-of-" + hashlib.sha256(data).digest()


class SignedClient(github.Client):
    """Client with the fake signer, for flows that build their own Client (connect)."""

    def __init__(self, *args, **kwargs):
        kwargs["sign"] = fake_sign
        super().__init__(*args, **kwargs)


@pytest.fixture
def gh(home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    monkeypatch.setenv("RGGITHUB_IAC_DIR", str(home / "iac"))  # tests never write to the real /data/iac
    monkeypatch.setenv("RGTRIAGE_KNOWLEDGE", str(home / "kb"))
    return FakeGitHub()


def make_client(gh, policy=None, app=None):
    pol = dict(POLICY if policy is None else policy)
    pol.setdefault("writes_enabled", False)
    client = github.Client(pol, dict(APP if app is None else app), transport=gh, sleep=lambda s: None, sign=fake_sign)
    return client


@pytest.fixture
def connected(gh, home):  # noqa: F811
    """App 'created', key file present, policy saved and verified, as after `connect` + `configure`."""
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    return gh


def new_client(gh):
    return github.Client(sleep=lambda s: None, transport=gh, sign=fake_sign)


# ---------------------------------------------------------------- policy gate

@pytest.mark.parametrize("method,path,body", [
    ("DELETE", f"/repos/{REPO}/git/refs/heads/feature/remedigenius/x", None),
    ("DELETE", f"/repos/{REPO}/branches/dev/protection", None),
    ("PUT", f"/repos/{REPO}/pulls/1/merge", {"merge_method": "squash"}),
    ("PUT", f"/repos/{REPO}/branches/main/protection", {}),
    ("POST", f"/repos/{REPO}/pulls/1/reviews", {"event": "APPROVE"}),
    ("POST", f"/repos/{REPO}/pulls/1/merge", {}),
    ("POST", f"/repos/{REPO}/pulls/1/auto-merge", {}),
    ("POST", "/graphql", {"query": "mutation { mergePullRequest }"}),
    ("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/heads/main", "sha": "a" * 40}),
    ("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/heads/dev", "sha": "a" * 40}),
    ("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/tags/v1", "sha": "a" * 40}),
    ("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/heads/feature/remedigenius/../../main", "sha": "a" * 40}),
    ("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/heads/feature/other/x", "sha": "a" * 40}),
    ("PATCH", f"/repos/{REPO}/git/refs/heads/main", {"sha": "a" * 40}),
    ("PATCH", f"/repos/{REPO}/git/refs/heads/dev", {"sha": "a" * 40}),
    ("PATCH", f"/repos/{REPO}/git/refs/heads/feature/remedigenius/x", {"sha": "a" * 40, "force": True}),
    ("POST", f"/repos/{REPO}/pulls", {"title": "t", "head": "feature/remedigenius/x", "base": "main"}),
    ("POST", f"/repos/{REPO}/pulls", {"title": "t", "head": "feature/remedigenius/x", "base": "master"}),
    ("POST", f"/repos/{REPO}/pulls", {"title": "t", "head": "other:feature/remedigenius/x", "base": "dev"}),
    ("POST", f"/repos/{REPO}/pulls", {"title": "t", "head": "main", "base": "dev"}),
    ("POST", f"/repos/{REPO}/pulls", {"title": "t", "head": "feature/remedigenius/x", "base": "dev", "auto_merge": True}),
    ("PATCH", f"/repos/{REPO}/pulls/3", {"base": "main"}),
    ("PATCH", f"/repos/{REPO}/pulls/3", {"state": "closed"}),
    ("POST", f"/repos/{REPO}/pulls/3/requested_reviewers", {"reviewers": ["mallory"]}),
    ("POST", f"/repos/{REPO}/pulls/3/requested_reviewers", {}),
    ("POST", f"/repos/{REPO}/rulesets", {"name": "x"}),
    ("POST", f"/repos/{REPO}/collaborators/mallory", {}),
    ("PATCH", f"/repos/{REPO}", {"default_branch": "dev"}),
    ("POST", f"/repos/{REPO}/actions/workflows/ci.yml/dispatches", {}),
    ("GET", f"/repos/{REPO}/actions/secrets", None),
    ("GET", f"/repos/{REPO}/keys", None),
    ("GET", "/repos/other-org/other-repo", None),
    ("GET", f"/repos/{REPO}-fork/pulls", None),
    ("POST", "/repos/other-org/other-repo/git/blobs", {}),
    ("GET", "/user", None),
    ("GET", "/orgs/acme/members", None),
])
def test_gate_refuses_everything_outside_the_policy(gh, method, path, body):
    client = make_client(gh)
    with pytest.raises(github.Denied):
        client.gate.check(method, path, body)
    with pytest.raises(github.Denied):
        client.call(method, path, body)
    assert gh.requests == []  # refused before anything was sent, not even a token request


@pytest.mark.parametrize("method,path,body", [
    ("GET", f"/repos/{REPO}", None),
    ("GET", f"/repos/{REPO}/pulls?head=acme:feature/remedigenius/x&state=open", None),
    ("GET", f"/repos/{REPO}/commits/{'a' * 40}/check-runs", None),
    ("POST", f"/repos/{REPO}/git/blobs", {"content": "x", "encoding": "base64"}),
    ("POST", f"/repos/{REPO}/git/refs", {"ref": "refs/heads/feature/remedigenius/fix-1", "sha": "a" * 40}),
    ("PATCH", f"/repos/{REPO}/git/refs/heads/feature/remedigenius/fix-1", {"sha": "a" * 40, "force": False}),
    ("POST", f"/repos/{REPO}/pulls", {"title": "t", "head": "feature/remedigenius/fix-1", "base": "dev", "body": "b"}),
    ("PATCH", f"/repos/{REPO}/pulls/3", {"title": "t", "body": "b"}),
    ("POST", f"/repos/{REPO}/pulls/3/requested_reviewers", {"reviewers": ["Alice"]}),
])
def test_gate_allows_the_narrow_operations(gh, method, path, body):
    make_client(gh).gate.check(method, path, body)


def test_gate_is_case_insensitive_about_the_repository_but_nothing_else(gh):
    make_client(gh).gate.check("GET", "/repos/ACME/Infra/pulls")
    with pytest.raises(github.Denied):
        make_client(gh).gate.check("GET", "/repos/acme/infra2/pulls")


def test_writes_are_denied_until_enabled_but_reads_work(gh):
    gate = make_client(gh).gate
    gate.check("GET", f"/repos/{REPO}")
    with pytest.raises(github.Denied, match="not enabled"):
        gate.check("POST", f"/repos/{REPO}/git/blobs", {}, write_enabled=False)


@pytest.mark.parametrize("bad", [
    {},
    {"repo": REPO},
    {**POLICY, "base": "main"},
    {**POLICY, "base": "master"},
    {**POLICY, "base": "release/1.0"},
    {**POLICY, "base": "production"},
    {**POLICY, "base": "dev", "default_branch": "dev"},
    {**POLICY, "repo": "not-a-repo"},
    {**POLICY, "repo": "a/b/c"},
    {**POLICY, "branch_prefix": ""},
    {**POLICY, "branch_prefix": "main/"},
    {**POLICY, "branch_prefix": "feature/remedigenius"},
    {**POLICY, "branch_prefix": "../x/"},
    {**POLICY, "base": "feature", "branch_prefix": "feature/remedigenius/"},
    {"repo": REPO, "base": None, "branch_prefix": 5},
])
def test_missing_or_malformed_policy_denies_everything(gh, bad):
    client = github.Client(bad, dict(APP), transport=gh, sleep=lambda s: None, sign=fake_sign)
    with pytest.raises(github.Denied):
        client.call("GET", f"/repos/{REPO}")
    with pytest.raises(github.Denied):
        client.call("POST", f"/repos/{REPO}/git/blobs", {})
    assert gh.requests == []


def test_a_policy_file_that_is_not_json_is_a_missing_policy(home, monkeypatch):
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    (home / "github").mkdir()
    (home / "github" / "policy.json").write_text("{not json")
    assert github.load_policy() == {}
    assert github.status()["state"] == "Disconnected"


@pytest.mark.parametrize("path", [".github/workflows/ci.yml", ".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS", ".git/config", "a/.git/hooks/pre-push",
                                  ".gitmodules", ".terraform/x", "terraform.tfstate", "prod.tfvars", "prod.auto.tfvars.json", ".env", "key.pem", "../escape.tf",
                                  "/abs.tf", "C:/x.tf", "a/../../x.tf", "id_rsa"])
def test_the_runtime_cannot_change_files_that_could_grant_it_authority(path):
    with pytest.raises(github.Denied):
        github._safe_repo_path(path)


def test_ordinary_iac_paths_are_accepted():
    assert github._safe_repo_path("terraform/modules/s3/main.tf") == "terraform/modules/s3/main.tf"
    assert github._safe_repo_path("cfn\\queue.yaml") == "cfn/queue.yaml"


def test_proposals_must_live_under_the_proposals_folder(tmp_path):
    proposals, outside = tmp_path / "proposals", tmp_path / "secrets.tf"
    proposals.mkdir()
    (proposals / "ok.tf").write_bytes(TF)
    outside.write_bytes(TF)
    assert github.read_proposals([f"{proposals / 'ok.tf'}=terraform/main.tf"], proposals) == {"terraform/main.tf": TF}
    for spec in (f"{outside}=terraform/main.tf", f"{proposals}/../secrets.tf=a.tf", f"{proposals / 'missing.tf'}=a.tf"):
        with pytest.raises(github.Denied):
            github.read_proposals([spec], proposals)
    with pytest.raises(github.Denied):
        github.read_proposals([], proposals)
    (proposals / "big.tf").write_bytes(b"x" * (github.MAX_FILE_BYTES + 1))
    with pytest.raises(github.Denied, match="larger"):
        github.read_proposals([f"{proposals / 'big.tf'}=big.tf"], proposals)


# ---------------------------------------------------------------- App authentication and tokens

def test_app_jwt_has_the_documented_shape():
    token = github.app_jwt("4242", Path("unused.pem"), now=1_000_000, sign=fake_sign)
    head, claims, signature = token.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    assert json.loads(base64.urlsafe_b64decode(pad(head))) == {"alg": "RS256", "typ": "JWT"}
    body = json.loads(base64.urlsafe_b64decode(pad(claims)))
    assert body == {"iat": 1_000_000 - 60, "exp": 1_000_000 + 540, "iss": "4242"}
    assert body["exp"] - body["iat"] <= 600  # GitHub allows at most 10 minutes
    assert base64.urlsafe_b64decode(pad(signature)) == fake_sign(f"{head}.{claims}".encode())


@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl not installed")
def test_app_jwt_signs_with_a_real_rsa_key(tmp_path):
    import subprocess
    pem = tmp_path / "k.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(pem), "2048"], check=True, capture_output=True)
    pub = tmp_path / "k.pub"
    subprocess.run(["openssl", "rsa", "-in", str(pem), "-pubout", "-out", str(pub)], check=True, capture_output=True)
    token = github.app_jwt("1", pem)
    head, claims, signature = token.split(".")
    sig = tmp_path / "sig"
    sig.write_bytes(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
    proc = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig)], input=f"{head}.{claims}".encode(), capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_installation_tokens_are_narrowed_to_the_repository_and_the_operation(connected):
    client = new_client(connected)
    client.call("GET", f"/repos/{REPO}")
    client.call("POST", f"/repos/{REPO}/git/blobs", {"content": "eA==", "encoding": "base64"})
    mints = [x[3] for x in connected.sent("POST", r"/access_tokens")]
    assert mints[-2:] == [{"permissions": github.READ_PERMISSIONS, "repositories": ["infra"]},
                          {"permissions": github.WRITE_PERMISSIONS, "repositories": ["infra"]}]
    assert "administration" not in github.WRITE_PERMISSIONS and github.WRITE_PERMISSIONS["pull_requests"] == "write"


def test_tokens_are_never_stored(connected):
    new_client(connected).call("GET", f"/repos/{REPO}")
    blob = " ".join(p.read_text(errors="ignore") for p in github.home().iterdir() if p.is_file())
    assert "ghs_" not in blob


def test_errors_never_contain_the_token_or_key(gh):
    client = make_client(gh)
    secret = "ghs_" + "T" * 36
    gh.fail[("GET", r"/repos/acme/infra$")] = 403
    with pytest.raises(github.GitHubError) as caught:
        client.call("GET", f"/repos/{REPO}")
    assert secret not in str(caught.value) and "BEGIN" not in str(caught.value)
    assert "ghs_" not in github._redact(f"oops {secret} and github_pat_{'x' * 30}", [])
    assert "PRIVATE KEY" not in github._redact("-----BEGIN RSA PRIVATE KEY-----", [])


def test_rate_limits_and_server_errors_are_retried_with_backoff_not_hammered(connected):
    calls, delays = {"n": 0}, []
    real = connected

    def flaky(method, url, headers, body):
        if "/access_tokens" not in url:
            calls["n"] += 1
            if calls["n"] < 3:
                return 503, {}, b'{"message":"unavailable"}'
        return real(method, url, headers, body)

    client = github.Client(dict(POLICY), dict(APP), transport=flaky, sleep=delays.append, sign=fake_sign)
    assert client.call("GET", f"/repos/{REPO}")["default_branch"] == DEFAULT
    assert delays == [1, 2]
    always = github.Client(dict(POLICY), dict(APP), transport=lambda *a: (429, {"Retry-After": "7"}, b"{}"), sleep=delays.append, sign=fake_sign)
    with pytest.raises(github.GitHubError, match="rate limit"):
        always.call("GET", f"/repos/{REPO}")
    assert delays[-1] == 7


def test_a_timeout_is_a_clear_error_not_a_hang(connected):
    def down(*a):
        raise TimeoutError("timed out")
    client = github.Client(dict(POLICY), dict(APP), transport=down, sleep=lambda s: None, sign=fake_sign)
    with pytest.raises(github.GitHubError, match="could not be reached"):
        client.call("GET", f"/repos/{REPO}")


def test_redirects_are_never_followed_with_a_credential():
    assert github._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/") is None
    with pytest.raises(github.GitHubError):
        github._http("GET", "http://api.github.com/x", {}, None)


# ---------------------------------------------------------------- connection states

def test_status_walks_through_the_four_states(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    assert github.status()["state"] == "Disconnected"
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps({"app_id": 1, "slug": "x", "owner": "acme"}))
    assert github.status()["state"] == "Blocked" and "install" in github.status()["remedy"].lower()
    github._write_private(github.home() / "app.json", json.dumps(APP))
    assert github.status(github.Client({}, dict(APP), transport=gh, sign=fake_sign))["state"].startswith("Connected")
    github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    st = github.status(new_client(gh))
    assert st["state"] == "Ready to create development PRs" and st["writes_enabled"] and st["identity"].startswith("remedigenius-ce-abc[bot]")


def test_login_alone_does_not_enable_writes_missing_protection_keeps_proposal_mode(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    gh.rules = {}
    st = github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    assert st["state"].startswith("Connected") and not st["writes_enabled"]
    assert "requires a reviewed PR" in st["remedy"]
    with pytest.raises(github.Denied, match="writes are not enabled"):
        github.publish("ref1", {"terraform/main.tf": TF}, client=new_client(gh), validators=False)
    assert not gh.sent("POST", r"/git/")


@pytest.mark.parametrize("weak", [
    {BASE: [], DEFAULT: GOOD_RULES},
    {BASE: GOOD_RULES, DEFAULT: []},
    {BASE: [{"type": "pull_request", "parameters": {"required_approving_review_count": 0}}, {"type": "non_fast_forward"}, {"type": "deletion"}], DEFAULT: GOOD_RULES},
    {BASE: [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}, {"type": "deletion"}], DEFAULT: GOOD_RULES},
    {BASE: [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}, {"type": "non_fast_forward"}], DEFAULT: GOOD_RULES},
])
def test_each_missing_protection_blocks_writes(gh, home, monkeypatch, weak):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    gh.rules = weak
    assert not github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)["writes_enabled"]


def test_missing_ci_or_stale_approval_rules_warn_but_do_not_block(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    rules = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}, {"type": "non_fast_forward"}, {"type": "deletion"}]
    gh.rules = {BASE: rules, DEFAULT: rules}
    st = github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    assert st["writes_enabled"]
    results = {c["check"]: c["result"] for c in st["protection"]["checks"]}
    assert results["development base requires CI checks"] == "warn" and results["development base dismisses stale approvals"] == "warn"


def test_missing_development_branch_is_reported_with_the_remedy(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    del gh.refs[BASE]
    st = github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    assert not st["writes_enabled"] and "create it" in st["remedy"]


def test_configure_refuses_main_unselected_repos_and_bot_reviewers(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    with pytest.raises(github.Denied, match="development branch"):
        github.configure(REPO, "main", reviewers=["alice"], transport=gh, sign=fake_sign)
    with pytest.raises(github.Denied, match="default branch"):
        github.configure(REPO, DEFAULT, reviewers=["alice"], transport=gh, sign=fake_sign)
    with pytest.raises(github.GitHubError, match="not selected"):
        github.configure("acme/other", BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    with pytest.raises(github.Denied, match="humans"):
        github.configure(REPO, BASE, reviewers=["ci-bot"], transport=gh, sign=fake_sign)
    with pytest.raises(github.Denied, match="humans"):
        github.configure(REPO, BASE, reviewers=["nobody"], transport=gh, sign=fake_sign)
    assert not (github.home() / "policy.json").exists()  # a refused configuration leaves no policy behind


def test_default_branch_dev_is_refused_even_if_the_operator_types_it(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    gh_default_dev = gh
    original = gh_default_dev.__call__

    def default_is_dev(method, url, headers, body):
        status, h, raw = original(method, url, headers, body)
        if url.endswith(f"/repos/{REPO}") and method == "GET":
            return status, h, json.dumps({"default_branch": BASE}).encode()
        return status, h, raw
    with pytest.raises(github.Denied, match="default branch"):
        github.configure(REPO, BASE, reviewers=["alice"], transport=default_is_dev, sign=fake_sign)


def test_revoked_or_removed_access_blocks_with_a_reconnect_remedy(connected):
    connected.fail[("POST", r"/access_tokens")] = 401
    st = github.status(new_client(connected))
    assert st["state"] == "Blocked" and "reconnect" in st["remedy"].lower() and not st["writes_enabled"]
    connected.fail.clear()
    connected.installation_repos = []
    st = github.status(new_client(connected))
    assert st["state"] == "Blocked" and "cannot see" in st["remedy"]


def test_suspended_app_or_org_approval_pending_is_reported(connected):
    connected.fail[("POST", r"/access_tokens")] = 403
    st = github.status(new_client(connected))
    assert st["state"] == "Blocked" and "organization approval" in st["remedy"]


def test_unavailable_enforcement_denies_writes(connected):
    connected.fail[("GET", r"/rules/branches")] = 500
    st = github.status(new_client(connected), verify=True)
    assert st["state"] == "Blocked" and not st["writes_enabled"]  # the protection check could not run: no writes
    with pytest.raises(github.Denied):  # publish re-verifies; the check cannot run, so the branch is not touched
        github.publish("r", {"terraform/main.tf": TF}, client=new_client(connected), validators=False)
    assert not connected.sent("POST", r"/git/")


def test_disconnect_removes_key_and_installation_and_is_idempotent(connected):
    seen = []

    def spy(method, url, headers, body):
        seen.append((method, urllib.parse.urlparse(url).path))
        return (204, {}, b"") if method == "DELETE" else connected(method, url, headers, body)
    result = github.disconnect(transport=spy, sign=fake_sign)
    assert ("DELETE", "/app/installations/77") in seen
    assert not list(github.home().glob("app.*")) and not (github.home() / "policy.json").exists()
    assert github.status()["state"] == "Disconnected"
    assert any("delete it there" in n for n in result["notes"])
    github.disconnect(transport=spy, sign=fake_sign)  # second time: nothing to do, no error


# ---------------------------------------------------------------- the publish workflow

def ok_validation(tree, files):
    return [{"check": "terraform validate", "result": "pass", "detail": ""}]


def publish(gh, files=None, ref="ab12cd34ef56", **kw):
    return github.publish(ref, files or {"terraform/main.tf": TF + b"# fix\n"}, title="Block public policy", client=new_client(gh), validators=ok_validation,
                          finding={"ref": ref, "title": "S3.8 bucket allows public policy"}, evidence="Observed BlockPublicPolicy=false in 123456789012",
                          change="set block_public_policy = true", effect="in-place", risk="low", rollback="revert", topic="s3 public policy", **kw)


def test_publish_opens_one_pr_from_a_feature_branch_into_dev_with_the_review_asked(connected):
    result = publish(connected)
    assert result["published"] and result["action"] == "opened" and result["pr"].endswith("/pull/1")
    assert result["branch"].startswith("feature/remedigenius/s3-public-policy-")
    pr = connected.pulls[0]
    assert pr["base"]["ref"] == BASE and pr["head"]["ref"] == result["branch"]
    assert connected.refs[DEFAULT] == connected.refs[BASE] and BASE in connected.refs
    assert "************" in pr["body"] and "123456789012" not in pr["body"]  # sanitized evidence
    for section in ("## Finding", "## Evidence", "## Proposed change", "## Expected effect", "## Validation", "## Operational risk", "## Rollback"):
        assert section in pr["body"]
    assert connected.sent("POST", r"/pulls/1/requested_reviewers")[0][3] == {"reviewers": ["alice"]}


def test_nothing_in_the_whole_workflow_ever_merges_approves_deletes_or_touches_protected_refs(connected):
    publish(connected)
    publish(connected, files={"terraform/main.tf": TF + b"# fix 2\n"})
    github.pr_status(number=1, client=new_client(connected))
    for method, host, path, body, _auth in connected.requests:
        assert method in ("GET", "POST", "PATCH")
        assert not re.search(r"/(merge|auto-merge|reviews)$", path) or method == "GET"
        assert "protection" not in path or method == "GET"
        if method != "GET" and "/git/refs" in path:
            assert "refs/heads/feature/remedigenius/" in (body.get("ref") or "refs/heads/feature/remedigenius/") or path.split("/refs/heads/")[-1].startswith("feature/remedigenius/")
            assert not body.get("force")
        if method == "POST" and path.endswith("/pulls"):
            assert body["base"] == BASE
    assert connected.refs[BASE] == connected.refs[DEFAULT] and not any(c["author"].endswith("[bot]") for c in
                                                                        [connected.commits[connected.refs[b]] for b in (BASE, DEFAULT)])


def test_a_retry_with_the_same_change_makes_no_duplicate_pr_or_commit(connected):
    first = publish(connected)
    commits = len(connected.commits)
    again = publish(connected)
    assert again["published"] and again["changed"] is False and again["pr"] == first["pr"]
    assert len(connected.pulls) == 1 and len(connected.commits) == commits


def test_a_resumed_session_with_new_content_updates_the_same_branch_and_pr(connected):
    first = publish(connected)
    second = publish(connected, files={"terraform/main.tf": TF + b"# second take\n"})
    assert second["action"] == "updated" and second["pr"] == first["pr"] and len(connected.pulls) == 1
    patches = connected.sent("PATCH", r"/git/refs/heads/")
    assert patches and all(p[3]["force"] is False for p in patches)
    chain = connected.commits[connected.refs[first["branch"]]]["parents"]
    assert chain == [next(iter(c for c in connected.commits if c != connected.refs[first["branch"]] and connected.commits[c]["author"].endswith("[bot]")))]


def test_a_branch_with_someone_elses_commits_is_never_built_on_or_overwritten(connected):
    first = publish(connected)
    human = connected._commit(connected.commits[connected.refs[first["branch"]]]["tree"], [connected.refs[first["branch"]]], "bob")
    connected.refs[first["branch"]] = human
    before = dict(connected.refs)
    with pytest.raises(github.Denied, match="bob"):
        publish(connected, files={"terraform/main.tf": TF + b"# other\n"})
    assert connected.refs == before and len(connected.pulls) == 1


def test_a_branch_that_moves_during_publish_is_not_force_pushed(connected):
    first = publish(connected)
    real = connected.__call__

    def racing(method, url, headers, body):
        if method == "PATCH" and "/git/refs/heads/" in url:  # someone pushes between our read and our update
            connected.refs[first["branch"]] = connected._commit(connected.commits[connected.refs[first["branch"]]]["tree"], [connected.refs[first["branch"]]], "carol")
        return real(method, url, headers, body)
    client = github.Client(sleep=lambda s: None, transport=racing, sign=fake_sign)
    with pytest.raises(github.GitHubError, match="not a fast-forward"):
        github.publish("ab12cd34ef56", {"terraform/main.tf": TF + b"# third\n"}, title="t", client=client, validators=ok_validation, topic="s3 public policy")
    assert connected.commits[connected.refs[first["branch"]]]["author"] == "carol"
    assert not any(p[3] and p[3].get("force") for p in connected.requests)


def test_failed_validation_pushes_nothing(connected):
    def failing(tree, files):
        return [{"check": "terraform validate", "result": "fail", "detail": "Error: Unsupported argument"}]
    result = github.publish("r1", {"terraform/main.tf": b"broken"}, client=new_client(connected), validators=failing)
    assert result["published"] is False and "validation failed" in result["reason"]
    assert not connected.sent("POST", r"/git/") and not connected.pulls


def test_validation_runs_on_a_credential_free_copy_of_the_base_branch(connected):
    seen = {}

    def spy(tree, files):
        seen["files"] = sorted(str(p.relative_to(tree)).replace("\\", "/") for p in tree.rglob("*") if p.is_file())
        seen["token"] = [x[4] for x in connected.requests if "codeload" in str(x[1])]
        return ok_validation(tree, files)
    github.publish("r1", {"terraform/new.tf": TF}, client=new_client(connected), validators=spy, topic="x")
    assert seen["files"] == ["terraform/main.tf"]  # the repository as of the base commit, before the overlay
    assert seen["token"] and set(seen["token"]) == {""}  # the download host never saw a credential


def test_protected_and_foreign_files_are_refused_before_any_call(connected):
    for path in (".github/workflows/ci.yml", "CODEOWNERS", ".github/CODEOWNERS"):
        with pytest.raises(github.Denied):
            github.publish("r1", {path: b"x"}, client=new_client(connected), validators=False)
    assert not connected.sent("POST", r"/git/")


def test_reviewer_request_failure_does_not_lose_the_pr(connected):
    connected.fail[("POST", r"requested_reviewers")] = 422
    assert publish(connected)["pr"].endswith("/pull/1")


def test_publish_links_the_pr_to_the_remediation_record(connected, home):  # noqa: F811
    store.save_decision("ab12cd34ef56", "fixing", "fix it", fix={"state": "decided", "owner": "team-a", "pr": None})
    result = publish(connected)
    fix = store.load_decisions()["ab12cd34ef56"]["fix"]
    assert fix["pr"] == result["pr"] and fix["state"] == "pr"


def test_publish_without_a_fix_record_still_works(connected):
    assert publish(connected, ref="notrecorded01")["published"]


def test_pr_status_reports_human_reviews_separately_from_bots(connected):
    publish(connected)
    info = github.pr_status(number=1, client=new_client(connected))
    assert info["human_reviews"] == {"alice": "APPROVED"}  # the bot's approval is not counted
    assert info["checks"] == {"tf-validate": "success"} and info["base"] == BASE
    assert github.pr_status(branch="feature/remedigenius/none", client=new_client(connected)) == {"found": False}


def test_restart_recovery_keeps_the_restrictions(connected):
    publish(connected)
    fresh = new_client(connected)  # a new process: nothing cached in memory, only the files
    assert github.status(fresh)["state"] == "Ready to create development PRs"
    assert publish(connected)["changed"] is False
    with pytest.raises(github.Denied):
        fresh.call("PUT", f"/repos/{REPO}/pulls/1/merge", {})


def test_the_secret_key_is_private_and_never_in_policy_or_app_files(connected):
    key = github.key_path()
    assert key.read_text().startswith("-----BEGIN")
    assert (key.stat().st_mode & 0o077) == 0 or __import__("os").name == "nt"
    for name in ("app.json", "policy.json"):
        text = (github.home() / name).read_text()
        assert "BEGIN" not in text and "ghs_" not in text and "pem" not in text.lower()


# ---------------------------------------------------------------- what the agent can reach

def test_the_socket_exposes_only_status_publish_and_pr_status():
    for args in (["github", "connect"], ["github", "configure", "--repo", "a/b", "--base", "dev"], ["github", "disconnect"], ["github", "verify"],
                 ["github", "publish", "--ref", "x", "--file", "a=b", "--repo", "evil/repo"], ["github", "status", "--org", "evil"], ["github"]):
        reply = server.execute(args)
        assert reply["rc"] == 2 and "not available over the socket" in reply["stderr"], args


def test_the_agent_tool_offers_no_connect_merge_or_approve(monkeypatch):
    import importlib.util as u
    spec = u.spec_from_file_location("rg_plugin", Path(__file__).resolve().parents[1] / "profiles/remedigenius/plugins/rg-triage/__init__.py")
    plugin = u.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    assert plugin.GITHUB_OPS == ("status", "publish", "pr_status", "refresh")
    for op in ("connect", "configure", "merge", "approve", "disconnect", "delete_branch", "auto_merge"):
        assert "must be one of" in plugin.handle({"action": "github", "op": op})
    assert "needs ref and files" in plugin.handle({"action": "github", "op": "publish", "ref": "x"})
    sent = []
    monkeypatch.setattr(plugin, "_run", lambda args, **kw: sent.append(args) or "ok")
    plugin.handle({"action": "github", "op": "publish", "ref": "x", "files": ["/opt/data/proposals/a.tf=terraform/a.tf"], "title": "t", "base": "main", "repo": "evil/x"})
    assert sent[0][:2] == ["github", "publish"] and "--base" not in sent[0] and "--repo" not in sent[0]  # repo and base are never model-controlled
    approval = plugin.on_pre_tool_call("rg_triage", {"action": "github", "op": "publish", "ref": "x", "files": ["a=b"]})
    assert approval["action"] == "approve" and "human still has to review and merge" in approval["message"]
    assert plugin.on_pre_tool_call("rg_triage", {"action": "github", "op": "status"}) is None


def test_the_agent_toolsets_still_have_no_terminal():
    text = (Path(__file__).resolve().parents[1] / "profiles/remedigenius/config.yaml").read_text()
    toolsets = re.findall(r"platform_toolsets:\n((?:  .*\n)+)", text)[0]
    assert "terminal" not in toolsets and "github" not in toolsets and "rg_triage" in toolsets


# ---------------------------------------------------------------- deterministic validators

def test_missing_tools_are_reported_as_not_validated_never_as_passed(tmp_path):
    results = validators.validate_overlay(tmp_path, {"main.tf": TF, "q.yaml": b"AWSTemplateFormatVersion: x\nResources: {}\n"}, which=lambda name: None)
    by = {r["check"]: r for r in results}
    assert by["terraform ."]["result"] == "skipped" and "NOT validated" in by["terraform ."]["detail"]
    assert by["cfn-lint q.yaml"]["result"] == "skipped" and "NOT linted" in by["cfn-lint q.yaml"]["detail"]
    assert all(r["result"] != "pass" for r in results)


def test_cloudformation_detection_and_plain_file_checks(tmp_path):
    cfn = b"AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  Q:\n    Type: AWS::SQS::Queue\n"
    assert validators.is_cloudformation("a.yaml", cfn.decode()) and not validators.is_cloudformation("values.yaml", "replicas: 2\n")
    assert validators.is_cloudformation("t.json", '{"Resources": {"Q": {"Type": "AWS::SQS::Queue"}}}')
    results = validators.validate_overlay(tmp_path, {"values.yaml": b"a: [1, 2\n", "ok.yaml": b"a: 1\n", "bad.json": b"{", "good.json": b"{}"}, which=lambda n: None)
    by = {r["check"]: r["result"] for r in results}
    assert by == {"yaml values.yaml": "fail", "yaml ok.yaml": "pass", "json bad.json": "fail", "json good.json": "pass"}
    assert validators.validate_overlay(tmp_path, {"README.md": b"x"}, which=lambda n: None)[0]["result"] == "skipped"


def test_tools_never_see_credentials_in_their_environment(monkeypatch):
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "RGGITHUB_HOME", "MODEL_API_KEY", "MY_SERVICE_TOKEN"):
        monkeypatch.setenv(name, "x")
    env = validators.clean_env()
    assert not [k for k in env if k.startswith(("GITHUB_", "GH_", "AWS_", "RGGITHUB_")) or k.endswith("TOKEN") or k == "MODEL_API_KEY"]
    assert env["TF_IN_AUTOMATION"] == "1"


@pytest.mark.skipif(not shutil.which("terraform"), reason="terraform not installed")
def test_terraform_validate_catches_a_broken_change_and_passes_a_good_one(tmp_path):
    good = validators.validate_overlay(tmp_path / "g", {"m/main.tf": b'locals {\n  a = 1\n}\n'})
    assert {r["check"]: r["result"] for r in good}["terraform m validate"] == "pass"
    bad = validators.validate_overlay(tmp_path / "b", {"m/main.tf": b'locals {\n  a = nope.missing\n}\n'})
    assert {r["check"]: r["result"] for r in bad}["terraform m validate"] == "fail"
    ugly = validators.validate_overlay(tmp_path / "u", {"m/main.tf": b'locals {\n a   = 1\n}\n'})
    assert {r["check"]: r["result"] for r in ugly}["terraform m fmt"] == "warn"  # formatting advice does not block


# ---------------------------------------------------------------- connect flow (App Manifest)

def test_connect_creates_the_app_from_the_manifest_and_waits_for_the_installation(gh, home, monkeypatch):  # noqa: F811
    import threading
    import urllib.request
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    seen = {}

    def transport(method, url, headers, body):
        path = urllib.parse.urlparse(url).path
        if path.startswith("/app-manifests/") and path.endswith("/conversions"):
            seen["code"] = path.split("/")[2]
            return 201, {}, json.dumps({"id": 9, "slug": "remedigenius-ce-zzz", "pem": "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----\n",
                                        "owner": {"login": "acme"}, "html_url": "https://github.com/apps/x"}).encode()
        if path == "/app/installations":
            return 200, {}, json.dumps([{"id": 55, "account": {"login": "acme"}}]).encode()
        return 404, {}, b"{}"

    messages, result = [], {}
    port = 18743
    monkeypatch.setattr(github, "Client", SignedClient)
    thread = threading.Thread(target=lambda: result.update(github.connect(owner="acme", port=port, open_browser=False, timeout=20, transport=transport, say=messages.append)))
    thread.start()
    deadline = time.time() + 10
    page = ""
    while time.time() < deadline and not page:
        try:
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2).read().decode()
        except OSError:
            time.sleep(0.2)
    state = re.search(r"\?state=([A-Za-z0-9_-]+)", page).group(1)
    manifest = json.loads(__import__("html").unescape(re.search(r'name=manifest value="([^"]+)"', page).group(1)))
    assert "organizations/acme/settings/apps/new" in page
    assert manifest["default_permissions"] == github.APP_PERMISSIONS and manifest["public"] is False and manifest["default_events"] == []
    assert manifest["redirect_url"] == f"http://localhost:{port}/created" and manifest["name"].startswith("RemediGenius-CE-")
    assert "merge" not in json.dumps(manifest["default_permissions"]) and "workflows" not in manifest["default_permissions"]
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/created?code=abcdefgh1234&state=wrong", timeout=2)
    except urllib.error.HTTPError as exc:
        assert exc.code == 400 and "code" not in seen  # a forged redirect is refused before any exchange
    urllib.request.urlopen(f"http://127.0.0.1:{port}/created?code=abcdefgh1234&state={state}", timeout=2).read()
    thread.join(30)
    assert result == {"connected": True, "app": "remedigenius-ce-zzz", "installation": 55, "account": "acme"} and seen["code"] == "abcdefgh1234"
    assert github.load_app()["app_id"] == 9 and github.key_path().read_text().startswith("-----BEGIN RSA")
    assert "pem" not in (github.home() / "app.json").read_text().lower()


# ---------------------------------------------------------------- deployment: where the key lives

def _host():
    import importlib.util
    spec = importlib.util.spec_from_file_location("spot_host_gh", Path(__file__).resolve().parents[1] / "deploy/aws-single/host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOST_CFG = {"name": "remedigenius-ce", "region": "us-east-1", "bucket": "bucket-x", "scan_interval_hours": 4, "container_memory_mb": 4096,
            "image": "nousresearch/hermes-agent:stable@sha256:abc"}


def test_spot_keeps_the_app_key_out_of_the_agent_container_but_in_durable_state():
    host = _host()
    units = host.units(HOST_CFG)
    assert str(host.GITHUB) == str(Path("/data/rggithub")) or host.GITHUB.as_posix() == "/data/rggithub"
    hermes, desk = units["remedigenius-hermes.service"], units["remedigenius-desk.service"]
    webui = units["remedigenius-webui.service"] if "remedigenius-webui.service" in units else ""
    assert "rggithub" not in hermes and "rggithub" not in webui  # never mounted into an agent-facing container
    assert "/data:" not in hermes.replace("/data/hermes:/opt/data", "")  # no broad /data mount that would include it
    assert "Environment=RGGITHUB_HOME=/data/rggithub" in desk and "ReadWritePaths=/data/rgtriage -/data/hermes/rg-wiki /data/rggithub /data/iac" in desk and "RGGITHUB_IAC_DIR=/data/iac" in desk
    assert "--home github=/data/rggithub" in desk  # checkpointed to the private bucket: a rebuild keeps the connection


def test_spot_installs_pinned_checksummed_validators():
    host = _host()
    assert re.fullmatch(r"[0-9a-f]{64}", host.TFLINT[1]) and re.fullmatch(r"\d+\.\d+\.\d+", host.TFLINT[0])
    assert any(p.startswith("cfn-lint==") for p in host.PACKAGES)


def test_without_an_isolated_key_folder_github_is_blocked_not_half_working(monkeypatch, home):  # noqa: F811
    monkeypatch.delenv("RGGITHUB_HOME", raising=False)
    st = github.status()
    assert st["state"] == "Blocked" and "agent cannot read" in st["remedy"] and not st["writes_enabled"]
    with pytest.raises(github.Denied):
        github.publish("r", {"a.tf": TF}, client=github.Client({}, {}), validators=False)
    assert not (home / "github").exists()  # and nothing was created in the agent-readable desk folder


# ---------------------------------------------------------------- keeping the desk's view of the repository current

def _seed_secrets(gh):
    entries = {"terraform/main.tf": gh._blob(TF), "terraform/prod.tfvars": gh._blob(b'password = "hunter2"\n'), ".env": gh._blob(b"TOKEN=abc\n"),
               "keys/deploy.pem": gh._blob(b"-----BEGIN RSA PRIVATE KEY-----"), "terraform/terraform.tfstate": gh._blob(b"{}"),
               "cfn/queue.yaml": gh._blob(b"AWSTemplateFormatVersion: x\nResources: {}\n"), "cdk/cdk.json": gh._blob(b"{}"), "README.md": gh._blob(b"hi")}
    tree = gh._tree(entries)
    commit = gh._commit(tree, [gh.refs[BASE]], "acme-dev")
    gh.refs[BASE] = commit
    return commit


def test_refresh_mirrors_the_development_branch_without_secrets_and_records_the_repository(connected, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_IAC_DIR", str(home / "iac"))
    monkeypatch.setenv("RGTRIAGE_KNOWLEDGE", str(home / "kb"))
    commit = _seed_secrets(connected)
    result = github.refresh(new_client(connected))
    mirror = home / "iac" / "acme-infra"
    assert result["commit"] == commit and result["mirror"] == str(mirror)
    files = {p.relative_to(mirror).as_posix() for p in mirror.rglob("*") if p.is_file()}
    assert files == {"terraform/main.tf", "cfn/queue.yaml", "cdk/cdk.json", "README.md", ".rg-mirror.json"}  # no tfvars, .env, .pem or state
    assert set(result["iac"]) == {"Terraform", "CloudFormation", "CDK"}
    page = (home / "kb" / "repositories" / "acme-infra.md").read_text()
    assert "type: Repository" in page and commit[:10] in page and "human reviewer approves and merges" in page and "verified" not in page.split("---")[1]
    assert not [x for x in connected.requests if x[0] != "GET" and "/access_tokens" not in x[2]]  # a refresh only reads


def test_refresh_replaces_the_mirror_atomically_and_follows_new_commits(connected, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_IAC_DIR", str(home / "iac"))
    monkeypatch.setenv("RGTRIAGE_KNOWLEDGE", str(home / "kb"))
    github.refresh(new_client(connected))
    stale = home / "iac" / "acme-infra" / "stale.txt"
    stale.write_text("old")
    commit = _seed_secrets(connected)
    github.refresh(new_client(connected))
    assert not stale.exists() and json.loads((home / "iac" / "acme-infra" / ".rg-mirror.json").read_text())["commit"] == commit
    assert not list((home / "iac").glob(".*.new"))
    assert "refresh" in server.GITHUB_OPS


def test_refresh_is_refused_when_not_connected_and_changes_nothing(home, monkeypatch, gh):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    monkeypatch.setenv("RGGITHUB_IAC_DIR", str(home / "iac"))
    with pytest.raises(github.Denied):
        github.refresh(github.Client({}, {}, transport=gh))
    assert not (home / "iac").exists() and gh.requests == []


def test_a_mirror_failure_does_not_undo_a_valid_connection(gh, home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("RGGITHUB_HOME", str(home / "github"))
    monkeypatch.setenv("RGGITHUB_IAC_DIR", str(home / "file-not-folder"))
    (home / "file-not-folder").write_text("x")
    github._write_private(github.key_path(), "-----BEGIN PRIVATE KEY-----\n")
    github._write_private(github.home() / "app.json", json.dumps(APP))
    st = github.configure(REPO, BASE, reviewers=["alice"], transport=gh, sign=fake_sign)
    assert st["writes_enabled"] and "mirror not updated" in st["repository"]["note"]


def test_operators_get_a_wrapper_that_runs_the_desk_cli_as_the_desk_user():
    script = _host().wrapper_script()
    assert script.startswith("#!/bin/sh") and "sudo -u '#10000'" in script and "RGGITHUB_HOME=/data/rggithub" in script
    assert "-m rgtriage" in script and '"$@"' in script
