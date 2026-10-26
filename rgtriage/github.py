"""GitHub for the desk: a per-installation GitHub App and a small, deny-by-default set of operations.

The model never holds a token. It asks the desk (`rg_triage action=github`) for three structured operations:
`status`, `publish` (validate a saved proposal, push it to a feature branch, open or update one PR into the development
branch) and `pr-status`. Everything else (connect, configure, disconnect) is for the operator on the host.

Layers, outermost first:
  1. This module: every request to GitHub passes `Gate.check` inside `Client.call`, before anything is sent. A missing or
     malformed policy, a repository other than the configured one, a ref outside the feature-branch prefix, a PR base other
     than the configured development branch, a force update, a delete, a review, a merge or a protection change are all refused.
  2. GitHub itself: branch protection or rulesets on the development and production branches, CODEOWNERS and human review.
     GitHub App permissions cannot separate "open a PR" from "approve or merge a PR"; this module does (see docs/GITHUB.md).

Credentials: the App private key and ids live under RGGITHUB_HOME (default <desk home>/github), mode 0600, in a folder that is not
mounted into the agent container. Installation tokens last one hour, are minted per operation, narrowed to the one repository and
to the permissions the operation needs, and are never written down or printed.
"""
from __future__ import annotations

import base64
import hashlib
import html
import http.server
import json
import os
import re
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config, knowledge, store

API = "https://api.github.com"
DEFAULT_PREFIX = "feature/remedigenius/"
# Branches that are never a PR base or a write target, whatever the operator types.
PROTECTED_NAMES = {"main", "master", "trunk", "production", "prod", "release", "stable", "live"}
PROTECTED_PATTERNS = (r"^release[/-].*", r"^prod(uction)?[/-].*", r"^hotfix[/-].*")
# Files the runtime may never change: they could grant it more authority.
FORBIDDEN_PATHS = (r"^\.github/", r"(^|/)CODEOWNERS$", r"^\.git/", r"(^|/)\.git/", r"(^|/)\.gitmodules$", r"(^|/)\.gitattributes$",
                   r"(^|/)\.terraform/", r"\.tfstate", r"\.tfvars(\.json)?$", r"(^|/)\.env", r"\.pem$", r"(^|/)id_(rsa|ed25519)")
MAX_FILES, MAX_FILE_BYTES, MAX_TARBALL = 40, 512 * 1024, 200 * 1024 * 1024
READ_PERMISSIONS = {"contents": "read", "pull_requests": "read", "checks": "read", "statuses": "read", "metadata": "read"}
WRITE_PERMISSIONS = {"contents": "write", "pull_requests": "write", "metadata": "read"}
APP_PERMISSIONS = {"contents": "write", "pull_requests": "write", "checks": "read", "statuses": "read",
                   "administration": "read", "metadata": "read"}
OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
REPO = r"[A-Za-z0-9._-]{1,100}"
SHA = r"[0-9a-f]{40}"


class Denied(Exception):
    """The operation is refused by policy; nothing was sent to GitHub."""


class GitHubError(Exception):
    """GitHub answered with an error or could not be reached (messages never contain credentials)."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ state on disk

ISOLATION_REMEDY = ("GitHub publishing is only enabled where RGGITHUB_HOME points to a folder the agent cannot read (the Spot deployment sets "
                    "it). In the workstation and existing-Hermes modes the desk's state folder is readable by the agent, so the App key could not "
                    "be kept out of its reach.")


def home(create: bool = False) -> Path:
    if not os.environ.get("RGGITHUB_HOME"):
        raise Denied(ISOLATION_REMEDY)
    path = Path(os.environ["RGGITHUB_HOME"])
    if create:
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


def _write_private(path: Path, text: str) -> None:
    home(create=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_app() -> dict:
    return _read_json(home() / "app.json")


def load_policy() -> dict:
    return _read_json(home() / "policy.json")


def proposals_dir() -> Path:
    """Where the agent saves proposals (the same path on the host and inside the agent container)."""
    for candidate in (os.environ.get("RGTRIAGE_PROPOSALS"), "/opt/data/proposals", str(config.home() / "proposals")):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return config.home() / "proposals"


def key_path() -> Path:
    return home() / "app.pem"


# ------------------------------------------------------------------ policy

def slug(text: str, limit: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:limit].strip("-") or "change"


def is_protected(branch: str, default_branch: str = "") -> bool:
    name = branch.strip().lower()
    return (name in PROTECTED_NAMES or (default_branch and name == default_branch.lower())
            or any(re.match(p, name) for p in PROTECTED_PATTERNS))


def validate_policy(policy: dict) -> list[str]:
    """Problems with an operator policy; an empty list means it is well formed."""
    problems = []
    repo = str(policy.get("repo") or "")
    if not re.fullmatch(f"{OWNER}/{REPO}", repo):
        problems.append("repo must look like owner/name")
    base = str(policy.get("base") or "")
    if not base or is_protected(base, str(policy.get("default_branch") or "")):
        problems.append("base must be a development branch, never main, master, release/production or the repository's default branch")
    prefix = str(policy.get("branch_prefix") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*/", prefix) or is_protected(prefix.rstrip("/")):
        problems.append("branch_prefix must be a folder-style prefix such as feature/remedigenius/")
    if prefix and base and (base.startswith(prefix) or prefix.startswith(base + "/")):
        problems.append("branch_prefix must not contain the base branch")
    return problems


class Gate:
    """Deny-by-default check of every GitHub REST request before it is sent."""

    def __init__(self, policy: dict):
        self.policy = policy
        problems = validate_policy(policy)
        if problems:
            raise Denied("policy is missing or malformed: " + "; ".join(problems))
        self.repo = policy["repo"].lower()
        self.base = policy["base"]
        self.prefix = policy["branch_prefix"]
        self.reviewers = {r.lower() for r in policy.get("reviewers") or []}

    def _branch_ok(self, ref: str) -> bool:
        return ref.startswith(self.prefix) and len(ref) > len(self.prefix) and ".." not in ref and not ref.endswith((".lock", "/", "."))

    def check(self, method: str, path: str, body: dict | None = None, write_enabled: bool = True) -> None:
        method = method.upper()
        if "?" in path:
            path = path.split("?", 1)[0]
        path = urllib.parse.unquote(path)
        if method not in ("GET", "POST", "PATCH"):
            raise Denied(f"{method} is never allowed (no deletes, no PUT: merges and protection changes are not available)")
        match = re.fullmatch(rf"/repos/({OWNER})/({REPO})(/.*)?", path)
        if not match:
            if method == "GET" and path == "/installation/repositories":
                return
            raise Denied(f"{method} {path} is outside the configured repository")
        if f"{match.group(1)}/{match.group(2)}".lower() != self.repo:
            raise Denied(f"repository {match.group(1)}/{match.group(2)} is not the configured repository")
        rest, body = match.group(3) or "", body or {}
        if method == "GET":
            if rest == "" or re.fullmatch(rf"/(git/(ref|commits|trees|blobs)|branches|rules/branches|contents|tarball|commits|pulls|rulesets|issues)(/.*)?", rest):
                return
            raise Denied(f"GET {rest} is not an allowed read")
        if not write_enabled:
            raise Denied("writes are not enabled: connect, configure and let the protection check pass first")
        if method == "POST":
            if rest in ("/git/blobs", "/git/trees", "/git/commits"):
                return
            if rest == "/git/refs":
                ref = str(body.get("ref") or "")
                if not ref.startswith("refs/heads/") or not self._branch_ok(ref[len("refs/heads/"):]):
                    raise Denied(f"refs may only be created under refs/heads/{self.prefix}")
                return
            if rest == "/pulls":
                if body.get("base") != self.base:
                    raise Denied(f"PR base must be {self.base!r}, not {body.get('base')!r}")
                head = str(body.get("head") or "")
                if ":" in head or not self._branch_ok(head):
                    raise Denied(f"PR head must be a branch under {self.prefix} in the configured repository")
                if set(body) - {"title", "body", "head", "base", "draft", "maintainer_can_modify"}:
                    raise Denied("unsupported PR fields")
                return
            requested = re.fullmatch(r"/pulls/\d+/requested_reviewers", rest)
            if requested:
                names = {n.lower() for n in body.get("reviewers") or []} | {n.lower() for n in body.get("team_reviewers") or []}
                if not names or not names <= self.reviewers or set(body) - {"reviewers", "team_reviewers"}:
                    raise Denied("reviewers must be among the designated human reviewers")
                return
            if re.fullmatch(r"/issues/\d+/comments", rest):
                return
            raise Denied(f"POST {rest} is not allowed (reviews, merges, auto-merge and protection changes are never available)")
        # PATCH
        ref = re.fullmatch(r"/git/refs/heads/(.+)", rest)
        if ref:
            if not self._branch_ok(ref.group(1)):
                raise Denied(f"only branches under {self.prefix} can be updated")
            if body.get("force"):
                raise Denied("force updates are never allowed")
            if set(body) - {"sha", "force"}:
                raise Denied("unsupported ref fields")
            return
        if re.fullmatch(r"/pulls/\d+", rest):
            if set(body) - {"title", "body"}:
                raise Denied("a PR may only have its title and description updated (not its base, state or merge settings)")
            return
        raise Denied(f"PATCH {rest} is not allowed")


# ------------------------------------------------------------------ talking to GitHub

def _redact(text: str, secrets_: list[str]) -> str:
    for s in secrets_:
        if s:
            text = text.replace(s, "[redacted]")
    return re.sub(r"(gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]+PRIVATE KEY-----)", "[redacted]", text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # surface the 3xx: a credential is never forwarded to another host
        return None


def _http(method: str, url: str, headers: dict, body: dict | None, timeout: float = 30) -> tuple[int, dict, bytes]:
    if urllib.parse.urlparse(url).scheme != "https":
        raise GitHubError("only https URLs are used")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def app_jwt(app_id: str, pem: Path, now: float | None = None, sign=None) -> str:
    """RS256 JWT for the App, valid 9 minutes, signed by `openssl` reading the key file directly (no key in memory or a temp copy)."""
    now = int(now or time.time())
    head = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    signing_input = f"{head}.{claims}".encode()
    if sign is None:
        if not shutil.which("openssl"):
            raise GitHubError("openssl is required to sign the GitHub App token and was not found")
        proc = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(pem)], input=signing_input, capture_output=True, timeout=20)
        if proc.returncode != 0:
            raise GitHubError("could not sign the GitHub App token (is the key file valid?)")
        signature = proc.stdout
    else:
        signature = sign(signing_input)
    return f"{head}.{claims}.{b64url(signature)}"


class Client:
    """Calls GitHub for one operation. `transport` is replaceable in tests; production uses `_http`."""

    def __init__(self, policy: dict | None = None, app: dict | None = None, transport=None, sleep=time.sleep, sign=None):
        self.policy = load_policy() if policy is None else policy
        self.app = load_app() if app is None else app
        self.transport = transport or _http
        self.sleep = sleep
        self.sign = sign
        self._tokens: dict[str, tuple[str, float]] = {}
        self._gate: Gate | None = None

    @property
    def gate(self) -> Gate:
        if self._gate is None:
            self._gate = Gate(self.policy)  # raises Denied when the policy is missing or malformed
        return self._gate

    def _raw(self, method: str, path: str, token: str, body: dict | None, bearer: str = "Bearer") -> tuple[int, dict, bytes]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "RemediGenius-CE",
                   "Authorization": f"{bearer} {token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        last = (0, {}, b"")
        for attempt in range(4):
            try:
                last = self.transport(method, API + path if path.startswith("/") else path, headers, body)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = (0, {}, str(getattr(exc, "reason", exc)).encode())
            status, resp_headers, _ = last
            retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
            limited = status in (429,) or (status == 403 and (retry_after or resp_headers.get("x-ratelimit-remaining") == "0"))
            if status == 0 or status >= 500 or limited:
                if attempt < 3:
                    self.sleep(min(float(retry_after), 30) if retry_after and str(retry_after).isdigit() else 2 ** attempt)
                    continue
            break
        return last

    def jwt(self) -> str:
        if not self.app.get("app_id") or not key_path().is_file():
            raise GitHubError("GitHub is not connected (no App identity). Run: rgtriage github connect")
        return app_jwt(self.app["app_id"], key_path(), sign=self.sign)

    def token(self, kind: str) -> str:
        """A one-hour installation token narrowed to the configured repository and to what `kind` (read|write) needs."""
        cached = self._tokens.get(kind)
        if cached and cached[1] > time.time() + 120:
            return cached[0]
        installation = self.app.get("installation_id")
        if not installation:
            raise GitHubError("the GitHub App is not installed on any repository yet. Run: rgtriage github connect")
        repo = (self.policy.get("repo") or "").split("/")[-1]
        body = {"permissions": READ_PERMISSIONS if kind == "read" else WRITE_PERMISSIONS}
        if repo:
            body["repositories"] = [repo]
        jwt = self.jwt()
        status, _, raw = self._raw("POST", f"/app/installations/{int(installation)}/access_tokens", jwt, body)
        if status != 201:
            raise GitHubError(_redact(_explain(status, raw, "minting an installation token"), [jwt]), status)
        token = json.loads(raw)["token"]
        self._tokens[kind] = (token, time.time() + 3300)
        return token

    def call(self, method: str, path: str, body: dict | None = None, write_enabled: bool = True) -> dict | list | None:
        """The only way the desk reaches the repository: gate first, then send. Returns parsed JSON (None for 404)."""
        self.gate.check(method, path, body, write_enabled=write_enabled)
        kind = "read" if method.upper() == "GET" else "write"
        token = self.token(kind)
        status, _, raw = self._raw(method, path, token, body)
        if status == 404 and method.upper() == "GET":
            return None
        if status >= 400 or status == 0:
            raise GitHubError(_redact(_explain(status, raw, f"{method.upper()} {path.split('?')[0]}"), [token]), status)
        if not raw:
            return {}
        return json.loads(raw)

    def raw_read(self, path: str) -> bytes:
        """Download a file (tarball) from the configured repository; gated like any read."""
        self.gate.check("GET", path)
        token = self.token("read")
        status, headers, raw = self._raw("GET", path, token, None)
        location = headers.get("Location") or headers.get("location") or ""
        if status in (301, 302, 307):  # the tarball redirects to GitHub's download host, which needs no credential
            host = urllib.parse.urlparse(location).hostname or ""
            if not host.endswith(("githubusercontent.com", ".github.com")):
                raise GitHubError("unexpected download redirect refused")
            status, _, raw = self.transport("GET", location, {"User-Agent": "RemediGenius-CE"}, None)
        if len(raw) > MAX_TARBALL:
            raise GitHubError("repository archive is too large to validate")
        if status >= 400 or status == 0:
            raise GitHubError(_redact(_explain(status, raw, "downloading the repository"), [token]), status)
        return raw


def _explain(status: int, raw: bytes, doing: str) -> str:
    try:
        message = json.loads(raw).get("message", "")
    except (ValueError, AttributeError):
        message = raw.decode("utf-8", "replace")[:200]
    hints = {0: "GitHub could not be reached (network or timeout)", 401: "credentials were rejected or expired: reconnect with `rgtriage github connect`",
             403: "GitHub refused (missing permission, organization approval pending, rate limit or the App was suspended)",
             404: "not found, or the App cannot see it (is the repository selected in the App installation?)",
             409: "conflict (the branch changed)", 429: "rate limit reached; wait and retry", 422: "GitHub rejected the request (for example a non-fast-forward branch update)"}
    return f"GitHub {doing} failed ({status}): {hints.get(status, 'error')}. {message}".strip()


# ------------------------------------------------------------------ protection check

def protection_check(client: Client) -> dict:
    """Read what protects the development base and the production branch. Never assumes; unknown is reported as unknown."""
    policy, checks = client.policy, []
    repo = policy["repo"]
    info = client.call("GET", f"/repos/{repo}", write_enabled=False) or {}
    default = info.get("default_branch") or ""
    policy["default_branch"] = default
    if info.get("archived") or info.get("disabled"):
        checks.append(("repository writable", "fail", "the repository is archived or disabled"))
    for branch, role in ((policy["base"], "development base"), (default, "default (production) branch")):
        if not branch:
            continue
        exists = client.call("GET", f"/repos/{repo}/branches/{urllib.parse.quote(branch, safe='')}", write_enabled=False)
        if exists is None:
            checks.append((f"{role} {branch!r} exists", "fail", "branch not found; create it (from the recorded starting commit) before enabling writes"))
            continue
        rules = client.call("GET", f"/repos/{repo}/rules/branches/{urllib.parse.quote(branch, safe='')}", write_enabled=False) or []
        classic = client.call("GET", f"/repos/{repo}/branches/{urllib.parse.quote(branch, safe='')}/protection", write_enabled=False) or {}
        types = {r.get("type") for r in rules if isinstance(r, dict)}
        review = next((r for r in rules if r.get("type") == "pull_request"), None)
        approvals = max([(review or {}).get("parameters", {}).get("required_approving_review_count", 0) or 0,
                         (classic.get("required_pull_request_reviews") or {}).get("required_approving_review_count", 0) or 0])
        stale = bool((review or {}).get("parameters", {}).get("dismiss_stale_reviews_on_push")
                     or (review or {}).get("parameters", {}).get("require_last_push_approval")
                     or (classic.get("required_pull_request_reviews") or {}).get("dismiss_stale_reviews")
                     or (classic.get("required_pull_request_reviews") or {}).get("require_last_push_approval"))
        no_force = bool(("non_fast_forward" in types) or (classic and not (classic.get("allow_force_pushes") or {}).get("enabled", True)))
        no_delete = bool(("deletion" in types) or (classic and not (classic.get("allow_deletions") or {}).get("enabled", True)))
        has_checks = "required_status_checks" in types or bool(classic.get("required_status_checks"))
        visible = bool(rules) or bool(classic)
        unknown = "" if visible else " (no rule or protection is visible: none exists, or this App cannot read it)"
        checks += [(f"{role} requires a reviewed PR", "pass" if approvals >= 1 else "fail", f"{branch}: {approvals} approval(s) required{unknown}"),
                   (f"{role} blocks force pushes", "pass" if no_force else "fail", branch),
                   (f"{role} blocks deletion", "pass" if no_delete else "fail", branch),
                   (f"{role} dismisses stale approvals", "pass" if stale else "warn", branch),
                   (f"{role} requires CI checks", "pass" if has_checks else "warn", branch)]
        if role.startswith("development"):
            rulesets = client.call("GET", f"/repos/{repo}/rulesets", write_enabled=False) or []
            bypass = [a for r in rulesets for a in r.get("bypass_actors") or [] if a.get("actor_type") in ("Integration", "OrganizationAdmin", "RepositoryRole")]
            if bypass:
                checks.append((f"{role} bypass list", "warn", "rulesets list bypass actors; confirm the agent App is not among them"))
    ok = all(c[1] != "fail" for c in checks)
    return {"ok": ok, "checks": [{"check": c, "result": r, "detail": d} for c, r, d in checks],
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "default_branch": default}


def reviewers_ok(client: Client, reviewers: list[str]) -> list[str]:
    """Designated reviewers must be real users, not bots or service accounts."""
    problems = []
    for name in reviewers:
        if "/" in name:  # org/team slug: accepted, verified by GitHub when review is requested
            continue
        user = _public_user(client, name)
        if user is None:
            problems.append(f"{name}: no such GitHub user")
        elif user.get("type") != "User" or name.lower().endswith("[bot]"):
            problems.append(f"{name}: is a {user.get('type')}, not a human user")
    return problems


def _public_user(client: Client, login: str) -> dict | None:
    """Public profile lookup; the only call outside the repository, so it bypasses the repo gate on purpose and sends no token."""
    status, _, raw = client.transport("GET", f"{API}/users/{urllib.parse.quote(login)}",
                                      {"Accept": "application/vnd.github+json", "User-Agent": "RemediGenius-CE"}, None)
    return json.loads(raw) if status == 200 else None


# ------------------------------------------------------------------ status

def status(client: Client | None = None, verify: bool = False) -> dict:
    """The four user-facing states, with the specific remedy when blocked."""
    if not os.environ.get("RGGITHUB_HOME"):
        return {"state": "Blocked", "writes_enabled": False, "identity": None, "repo": None, "base": None, "branch_prefix": None, "reviewers": [],
                "remedy": ISOLATION_REMEDY}
    app, policy = load_app() if client is None else client.app, load_policy() if client is None else client.policy
    out = {"state": "Disconnected", "writes_enabled": False, "identity": None, "repo": policy.get("repo"), "base": policy.get("base"),
           "branch_prefix": policy.get("branch_prefix"), "reviewers": policy.get("reviewers", []), "remedy": ""}
    if not app.get("app_id") or not (key_path().is_file() or client is not None):
        out["remedy"] = "Run `rgtriage github connect` to create and install the GitHub App."
        return out
    out["identity"] = f"{app.get('slug')}[bot] (App {app.get('app_id')}, owner {app.get('owner')})"
    if not app.get("installation_id"):
        out.update(state="Blocked", remedy="The App is created but not installed. Open its install page and select the repository, then run `rgtriage github connect` again.")
        return out
    if not policy.get("repo"):
        out.update(state="Connected: read/proposal access", remedy="Select the repository: `rgtriage github configure --repo owner/name --base dev --reviewer <login>`.")
        return out
    problems = validate_policy(policy)
    if problems:
        out.update(state="Blocked", remedy="Policy is malformed (" + "; ".join(problems) + "). Run `rgtriage github configure` again.")
        return out
    client = client or Client(policy, app)
    try:
        repos = client.call("GET", "/installation/repositories", write_enabled=False)
        names = {r["full_name"].lower() for r in (repos or {}).get("repositories", [])} if isinstance(repos, dict) else set()
        if policy["repo"].lower() not in names and repos is not None:
            raise GitHubError("the App cannot see the configured repository", 404)
        if verify:
            result = protection_check(client)
            policy["protection"] = result
            policy["writes_enabled"] = bool(result["ok"] and policy.get("reviewers"))
            _write_private(home() / "policy.json", json.dumps(policy, indent=1))
        check = policy.get("protection") or {}
    except GitHubError as exc:
        out.update(state="Blocked", remedy=str(exc) + " If the installation was removed, run `rgtriage github connect` again.")
        return out
    except Denied as exc:
        out.update(state="Blocked", remedy=str(exc))
        return out
    out["protection"] = check
    if policy.get("writes_enabled") and check.get("ok") and policy.get("reviewers"):
        out.update(state="Ready to create development PRs", writes_enabled=True)
        return out
    failed = [c for c in check.get("checks", []) if c["result"] == "fail"]
    out["state"] = "Connected: read/proposal access"
    out["remedy"] = ("Fix on GitHub, then run `rgtriage github verify`: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed)) if failed else (
        "Run `rgtriage github verify` to check the branch protection and enable writes." if not check else
        "Set a designated human reviewer: `rgtriage github configure --reviewer <login>`.")
    return out


# ------------------------------------------------------------------ configure / verify / disconnect (operator, on the host)

def configure(repo: str, base: str, prefix: str = DEFAULT_PREFIX, reviewers: list[str] | None = None, transport=None, sign=None) -> dict:
    app = load_app()
    policy = {"repo": repo, "base": base, "branch_prefix": prefix, "reviewers": list(reviewers or []), "writes_enabled": False}
    problems = validate_policy(policy)
    if problems:
        raise Denied("; ".join(problems))
    client = Client(policy, app, transport=transport, sign=sign)
    repos = client.call("GET", "/installation/repositories", write_enabled=False)
    names = {r["full_name"].lower() for r in (repos or {}).get("repositories", [])}
    if repo.lower() not in names:
        raise GitHubError(f"{repo} is not selected in the App installation (selected: {', '.join(sorted(names)) or 'none'}). "
                          f"Change the selection at https://github.com/settings/installations and retry.")
    info = client.call("GET", f"/repos/{repo}", write_enabled=False) or {}
    policy["default_branch"] = info.get("default_branch", "")
    problems = validate_policy(policy)
    if problems:
        raise Denied("; ".join(problems))
    bad = reviewers_ok(client, policy["reviewers"])
    if bad:
        raise Denied("reviewers must be humans: " + "; ".join(bad))
    _write_private(home() / "policy.json", json.dumps(policy, indent=1))
    result = status(Client(policy, app, transport=transport, sign=sign), verify=True)
    try:
        result["repository"] = refresh(Client(policy, app, transport=transport, sign=sign))
    except (GitHubError, Denied, OSError) as exc:  # the connection is valid even when the mirror cannot be written yet
        result["repository"] = {"note": f"repository mirror not updated: {exc}"}
    return result


def disconnect(uninstall: bool = True, transport=None, sign=None) -> dict:
    app, notes = load_app(), []
    if uninstall and app.get("installation_id") and key_path().is_file():
        client = Client({}, app, transport=transport, sign=sign)
        try:
            jwt = client.jwt()
            status_, _, raw = client._raw("DELETE", f"/app/installations/{int(app['installation_id'])}", jwt, None)
            notes.append("installation removed on GitHub" if status_ in (204, 404) else _explain(status_, raw, "removing the installation"))
        except GitHubError as exc:
            notes.append(str(exc))
    for name in ("app.pem", "app.json", "policy.json"):
        path = home() / name
        if path.exists():
            path.unlink()
    notes.append("local key and settings deleted")
    if app.get("slug"):
        notes.append(f"To remove the App itself: https://github.com/settings/apps/{app['slug']}/advanced (delete it there)")
    return {"state": "Disconnected", "notes": notes}


# ------------------------------------------------------------------ connect: App Manifest flow

def manifest(name: str, redirect_url: str, homepage: str) -> dict:
    return {"name": name, "url": homepage, "redirect_url": redirect_url, "public": False, "default_permissions": APP_PERMISSIONS,
            "default_events": [], "description": "RemediGenius-CE: proposes IaC fixes as pull requests into a development branch. Never merges or approves."}


def connect(owner: str = "", port: int = 8743, open_browser: bool = True, timeout: int = 900, transport=None, say=print) -> dict:
    """Create the App through GitHub's manifest flow and wait for the installation. Runs on the host; the browser reaches
    http://localhost:<port> directly (or through an SSM port forward on Spot)."""
    state = secrets.token_urlsafe(24)
    redirect = f"http://localhost:{port}/created"
    app_name = f"RemediGenius-CE-{secrets.token_hex(3)}"
    target = f"https://github.com/organizations/{urllib.parse.quote(owner)}/settings/apps/new" if owner else "https://github.com/settings/apps/new"
    form = (f"<html><body><p>Sending the RemediGenius-CE App definition to GitHub...</p>"
            f"<form id=f method=post action=\"{html.escape(target)}?state={state}\"><input type=hidden name=manifest "
            f"value=\"{html.escape(json.dumps(manifest(app_name, redirect, 'https://github.com/IaCGenius/RemediGenius')))}\">"
            f"<noscript><button>Continue to GitHub</button></noscript></form><script>document.getElementById('f').submit()</script></body></html>")
    result: dict = {}
    done = threading.Event()
    post = transport or _http

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _page(self, text: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(text.encode())

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == "/":
                return self._page(form)
            if url.path == "/created":
                if query.get("state", [""])[0] != state:
                    return self._page("State mismatch: start again from the terminal.", 400)
                code = query.get("code", [""])[0]
                if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", code):
                    return self._page("Missing code.", 400)
                status_, _, raw = post("POST", f"{API}/app-manifests/{code}/conversions",
                                       {"Accept": "application/vnd.github+json", "User-Agent": "RemediGenius-CE"}, None)
                if status_ != 201:
                    result["error"] = _explain(status_, raw, "creating the App from the manifest")
                    done.set()
                    return self._page("GitHub did not create the App; see the terminal.", 502)
                data = json.loads(raw)
                _write_private(key_path(), data["pem"])
                _write_private(home() / "app.json", json.dumps({"app_id": data["id"], "slug": data["slug"], "owner": (data.get("owner") or {}).get("login", owner or "personal"),
                                                                "html_url": data.get("html_url")}, indent=1))
                result["created"] = data["slug"]
                done.set()
                return self._page(f"The App was created. Next: <a href=\"https://github.com/apps/{html.escape(data['slug'])}/installations/new\">install it</a> "
                                  f"and select only the repository RemediGenius may use. You can close this tab afterwards.")
            self._page("Not found", 404)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    say(f"Open http://localhost:{port}/ in your browser (on Spot, first forward port {port} with SSM), then click 'Create GitHub App' on GitHub.")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{port}/")
        except Exception:
            pass
    try:
        if not done.wait(timeout):
            raise GitHubError("timed out waiting for the App creation; run connect again")
        if result.get("error"):
            raise GitHubError(result["error"])
    finally:
        server.shutdown()
    app = load_app()
    say(f"App created: {app['slug']}. Install it and select the repository: https://github.com/apps/{app['slug']}/installations/new")
    client = Client({}, app, transport=transport)
    deadline = time.time() + timeout
    while time.time() < deadline:
        status_, _, raw = client._raw("GET", "/app/installations", client.jwt(), None)
        if status_ == 200:
            installs = json.loads(raw)
            if installs:
                app["installation_id"] = installs[0]["id"]
                app["installed_on"] = (installs[0].get("account") or {}).get("login")
                _write_private(home() / "app.json", json.dumps(app, indent=1))
                return {"connected": True, "app": app["slug"], "installation": app["installation_id"], "account": app["installed_on"]}
        time.sleep(3)
    raise GitHubError("the App was created but not installed in time; install it, then run `rgtriage github connect` again")


# ------------------------------------------------------------------ keep the desk's view of the repository current

MIRROR_SKIP = FORBIDDEN_PATHS[2:] + (r"(^|/)\.git/",)
IAC_MARKERS = (("Terraform", r"\.tf$"), ("CloudFormation", r"(^|/)(cfn|cloudformation|templates?)[^/]*(/|\.(ya?ml|json)$)"), ("CDK", r"(^|/)cdk\.json$"))


def mirror_root() -> Path:
    """Where the desk keeps a read-only copy of the development branch for `fix` and file reads (the agent mounts it read-only)."""
    return Path(os.environ.get("RGGITHUB_IAC_DIR") or "/data/iac")


def detect_iac(paths: list[str]) -> dict:
    """What kind of IaC the repository holds, from file names only (labelled as such in the knowledge concept)."""
    found: dict[str, set[str]] = {}
    for path in paths:
        for kind, pattern in IAC_MARKERS:
            if re.search(pattern, path, re.I):
                found.setdefault(kind, set()).add(str(Path(path).parent).replace("\\", "/") or ".")
    return {kind: sorted(folders)[:20] for kind, folders in found.items()}


def refresh(client: Client | None = None) -> dict:
    """Mirror the development branch (read-only, no secrets) and record the repository in the knowledge bundle.

    Run by the operator after `configure`, and on request; the agent only ever sees the resulting files. The knowledge concept is an
    unreviewed draft: a person confirms it in the Knowledge tab."""
    client = client or Client()
    st = status(client)
    if st["state"].startswith(("Disconnected", "Blocked")) or not client.policy.get("repo"):
        raise Denied(f"{st['state']}: {st['remedy'] or 'no repository is selected'}")
    repo, base = client.policy["repo"], client.policy["base"]
    head = client.call("GET", f"/repos/{repo}/branches/{urllib.parse.quote(base, safe='')}", write_enabled=False)
    if head is None:
        raise GitHubError(f"development branch {base!r} was not found")
    sha = head["commit"]["sha"]
    name = slug(repo.replace("/", "-"), 80)
    root = mirror_root()
    target, stage = root / name, root / f".{name}.new"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    _extract_tarball(client.raw_read(f"/repos/{repo}/tarball/{sha}"), stage)
    kept, paths = 0, []
    for file in sorted(stage.rglob("*")):
        if not file.is_file():
            continue
        rel = file.relative_to(stage).as_posix()
        if any(re.search(pattern, rel, re.I) for pattern in MIRROR_SKIP) or file.stat().st_size > MAX_FILE_BYTES * 8:
            file.unlink()  # secrets, state, large blobs never reach the agent-readable mirror
            continue
        kept += 1
        paths.append(rel)
    (stage / ".rg-mirror.json").write_text(json.dumps({"repo": repo, "branch": base, "commit": sha,
                                                         "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")
    if target.exists():
        shutil.rmtree(target)
    os.replace(stage, target)
    kinds = detect_iac(paths)
    body = (f"Connected through the RemediGenius GitHub App. Fixes for resources deployed from this repository become pull requests from "
            f"`{client.policy['branch_prefix']}...` branches into `{base}`; a human reviewer approves and merges.\n\n"
            f"- Development branch: `{base}` (commit `{sha[:10]}`, mirrored read-only at `{target}`)\n"
            f"- Infrastructure code found (from file names): " + (", ".join(f"{k} in {', '.join(v[:5])}" for k, v in kinds.items()) or "none detected") +
            f"\n- Designated reviewers: {', '.join(client.policy.get('reviewers') or []) or 'not set'}\n"
            "\nThis page is kept up to date by the desk; edit the owner and notes in the Knowledge tab.")
    meta = {"type": "Repository", "title": repo, "description": f"IaC repository {repo} (development branch {base})",
            "remedigenius": {"repo": repo, "base": base, "commit": sha, "iac": sorted(kinds)}}
    try:
        knowledge.save(meta, body, "human:desk-github", path=f"repositories/{name}.md", replace=True)
        recorded = f"repositories/{name}.md"
    except Exception as exc:  # the mirror is useful even when the knowledge bundle is unavailable
        recorded = f"not recorded ({exc})"
    return {"repo": repo, "branch": base, "commit": sha, "files": kept, "iac": kinds, "mirror": str(target), "knowledge": recorded}


# ------------------------------------------------------------------ publish a proposal as a PR

def _safe_repo_path(path: str) -> str:
    clean = path.replace("\\", "/")
    if clean.startswith("/") or not clean or ".." in clean.split("/") or re.match(r"^[A-Za-z]:", clean) or any(re.search(p, clean, re.I) for p in FORBIDDEN_PATHS):
        raise Denied(f"{path!r} may not be changed by the runtime (workflows, CODEOWNERS, git metadata, state, keys and tfvars are protected)")
    return clean


def read_proposals(specs: list[str], proposals_dir: Path) -> dict[str, bytes]:
    """`proposal-file=repo/path` pairs; every proposal file must live under the proposals folder."""
    root = proposals_dir.resolve()
    files: dict[str, bytes] = {}
    if not specs or len(specs) > MAX_FILES:
        raise Denied(f"give between 1 and {MAX_FILES} files")
    for spec in specs:
        source, _, target = spec.partition("=")
        path = Path(source).expanduser().resolve()
        if root not in path.parents or not path.is_file():
            raise Denied(f"{source!r} is not a file under the proposals folder")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise Denied(f"{source!r} is larger than {MAX_FILE_BYTES // 1024} KB")
        files[_safe_repo_path(target or path.name)] = path.read_bytes()
    return files


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _extract_tarball(raw: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=__import__("io").BytesIO(raw), mode="r:gz") as tar:
        members = tar.getmembers()
        top = members[0].name.split("/")[0] if members else ""
        for m in members:
            parts = m.name.split("/", 1)
            if len(parts) < 2 or not m.isfile() or ".." in m.name or m.name.startswith("/"):
                continue
            target = (dest / parts[1]).resolve()
            if dest.resolve() not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = tar.extractfile(m)
            if handle is not None and m.size <= 5 * 1024 * 1024:
                target.write_bytes(handle.read())
        _ = top


def branch_name(prefix: str, ref: str, topic: str) -> str:
    return f"{prefix}{slug(topic or ref)}-{hashlib.sha1(ref.encode()).hexdigest()[:6]}"


def pr_body(finding: dict, files: list[str], validation: list[dict], evidence: str, change: str, effect: str, risk: str, rollback: str) -> str:
    def sanitize(text: str) -> str:
        return re.sub(r"\b\d{12}\b", "************", _redact(str(text or ""), []))
    rows = "\n".join(f"- `{v['check']}`: **{v['result']}**" + (f" ({sanitize(v['detail'])[:160]})" if v.get("detail") else "") for v in validation) or "- not validated"
    return (f"## Finding\n{sanitize(finding.get('title') or finding.get('ref'))}\n\nRef: `{sanitize(finding.get('ref'))}`\n\n"
            f"## Evidence\n{sanitize(evidence) or 'See the RemediGenius board.'}\n\n## Proposed change\n{sanitize(change)}\n\nFiles:\n" +
            "\n".join(f"- `{f}`" for f in files) + f"\n\n## Expected effect\n{sanitize(effect)}\n\n## Validation\n{rows}\n\n"
            f"## Operational risk\n{sanitize(risk)}\n\n## Rollback\n{sanitize(rollback)}\n\n---\n"
            "Opened by RemediGenius-CE as a bot. It never approves or merges: a human reviewer decides. Terraform validation checks syntax and "
            "provider schema only, not a plan.")


def publish(ref: str, files: dict[str, bytes], title: str = "", client: Client | None = None, validators=None, finding: dict | None = None,
            evidence: str = "", change: str = "", effect: str = "", risk: str = "", rollback: str = "", topic: str = "") -> dict:
    """Validate, push to the task's feature branch and open or update one PR into the development base."""
    client = client or Client()
    st = status(client, verify=True)  # protection is re-verified for every publish; a failed check denies the write
    if not st["writes_enabled"]:
        raise Denied(f"writes are not enabled ({st['state']}): {st['remedy']}")
    policy, repo = client.policy, client.policy["repo"]
    paths = {_safe_repo_path(p): d for p, d in files.items()}
    if len(paths) > MAX_FILES:
        raise Denied("too many files")
    branch = branch_name(policy["branch_prefix"], ref, topic or title)
    head_branch = urllib.parse.quote(branch, safe="/")
    base = client.call("GET", f"/repos/{repo}/branches/{urllib.parse.quote(policy['base'], safe='')}", write_enabled=False)
    if base is None:
        raise GitHubError(f"development branch {policy['base']!r} was not found")
    base_sha = base["commit"]["sha"]

    # 1. validate in a scratch copy with no credentials at all
    validation: list[dict] = []
    if validators is not False:
        run = validators or __import__("rgtriage.validators", fromlist=["validate_overlay"]).validate_overlay
        with tempfile.TemporaryDirectory(prefix="rg-github-") as scratch:
            tree_dir = Path(scratch) / "repo"
            tree_dir.mkdir()
            _extract_tarball(client.raw_read(f"/repos/{repo}/tarball/{base_sha}"), tree_dir)
            validation = run(tree_dir, paths)
    if any(v["result"] == "fail" for v in validation):
        return {"published": False, "reason": "validation failed; nothing was pushed", "validation": validation}

    # 2. reuse the task's branch if it is ours; never overwrite someone else's work
    existing = client.call("GET", f"/repos/{repo}/git/ref/heads/{head_branch}", write_enabled=False)
    parent = base_sha
    if existing:
        parent = existing["object"]["sha"]
        last = client.call("GET", f"/repos/{repo}/commits/{parent}", write_enabled=False) or {}
        author = ((last.get("author") or {}).get("login") or "")
        if author and author.lower() != f"{client.app.get('slug', '')}[bot]".lower():
            raise Denied(f"branch {branch} already has commits by {author}; refusing to build on or overwrite someone else's work")
    base_tree = (client.call("GET", f"/repos/{repo}/git/commits/{parent}", write_enabled=False) or {})["tree"]["sha"]
    entries = []
    for path, data in sorted(paths.items()):
        blob = client.call("POST", f"/repos/{repo}/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = client.call("POST", f"/repos/{repo}/git/trees", {"base_tree": base_tree, "tree": entries})
    pulls = client.call("GET", f"/repos/{repo}/pulls?head={urllib.parse.quote(repo.split('/')[0])}:{head_branch}&state=open") or []
    if existing and tree["sha"] == base_tree:
        return {"published": True, "changed": False, "branch": branch, "pr": (pulls[0]["html_url"] if pulls else None), "validation": validation,
                "note": "the branch already contains exactly these changes"}
    commit = client.call("POST", f"/repos/{repo}/git/commits", {"message": f"{title or 'RemediGenius fix'}\n\nRef: {ref}\nProposed by RemediGenius-CE; needs human review.",
                                                                   "tree": tree["sha"], "parents": [parent]})
    if existing:
        try:
            client.call("PATCH", f"/repos/{repo}/git/refs/heads/{head_branch}", {"sha": commit["sha"], "force": False})
        except GitHubError as exc:
            if exc.status in (409, 422):
                raise GitHubError(f"the branch moved while publishing (not a fast-forward). Nothing was overwritten; run publish again. {exc}", exc.status)
            raise
    else:
        client.call("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    body = pr_body(finding or {"ref": ref, "title": title}, sorted(paths), validation, evidence, change or title, effect, risk, rollback)
    if pulls:
        pr = client.call("PATCH", f"/repos/{repo}/pulls/{pulls[0]['number']}", {"title": title or pulls[0]["title"], "body": body})
        action = "updated"
    else:
        pr = client.call("POST", f"/repos/{repo}/pulls", {"title": title or f"RemediGenius fix for {ref}", "body": body, "head": branch, "base": policy["base"]})
        action = "opened"
        reviewers = [r for r in policy.get("reviewers", []) if "/" not in r]
        teams = [r.split("/", 1)[1] for r in policy.get("reviewers", []) if "/" in r]
        try:
            asks = {k: v for k, v in (("reviewers", reviewers), ("team_reviewers", teams)) if v}
            if asks:
                client.call("POST", f"/repos/{repo}/pulls/{pr['number']}/requested_reviewers", asks)
        except GitHubError:
            pass  # CODEOWNERS or the reviewers can still be asked on GitHub; the PR exists
    link_fix_record(ref, pr["html_url"])
    return {"published": True, "changed": True, "action": action, "branch": branch, "pr": pr["html_url"], "number": pr["number"], "validation": validation}


def link_fix_record(ref: str, url: str) -> bool:
    """Attach the PR to the remediation record (when the user decided to fix this finding)."""
    decisions = store.load_decisions()
    for key, decision in decisions.items():
        if ref in (key, decision.get("ref")) and decision.get("fix"):
            decision["fix"]["pr"] = url
            if decision["fix"].get("state", "decided") in ("decided", "stalled"):
                decision["fix"]["state"] = "pr"
            store._write(config.home() / "decisions.json", decisions)
            return True
    return False


def pr_status(number: int | None = None, branch: str = "", client: Client | None = None) -> dict:
    client = client or Client()
    st = status(client)
    if st["state"].startswith(("Disconnected", "Blocked")):
        raise Denied(f"{st['state']}: {st['remedy']}")
    repo = client.policy["repo"]
    if number is None:
        found = client.call("GET", f"/repos/{repo}/pulls?head={urllib.parse.quote(repo.split('/')[0])}:{urllib.parse.quote(branch, safe='/')}&state=all") or []
        if not found:
            return {"found": False}
        number = found[0]["number"]
    pr = client.call("GET", f"/repos/{repo}/pulls/{int(number)}")
    if not pr:
        return {"found": False}
    reviews = client.call("GET", f"/repos/{repo}/pulls/{int(number)}/reviews") or []
    latest: dict[str, str] = {}
    for r in reviews:
        if (r.get("user") or {}).get("type") == "User":
            latest[r["user"]["login"]] = r.get("state")
    sha = pr["head"]["sha"]
    runs = (client.call("GET", f"/repos/{repo}/commits/{sha}/check-runs") or {}).get("check_runs", [])
    combined = client.call("GET", f"/repos/{repo}/commits/{sha}/status") or {}
    return {"found": True, "number": pr["number"], "url": pr["html_url"], "state": "merged" if pr.get("merged") else pr["state"], "base": pr["base"]["ref"],
            "head": pr["head"]["ref"], "human_reviews": latest, "checks": {r["name"]: r.get("conclusion") or r.get("status") for r in runs},
            "status": combined.get("state"), "mergeable_state": pr.get("mergeable_state")}
