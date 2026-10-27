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
import hmac
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
from . import validators as _validators

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
# Reading branch protection and rulesets needs Administration: read. Only the verification token carries it, and never Administration: write.
VERIFY_PERMISSIONS = {**READ_PERMISSIONS, "administration": "read"}
WRITE_PERMISSIONS = {"contents": "write", "pull_requests": "write", "metadata": "read"}
TOKEN_PERMISSIONS = {"read": READ_PERMISSIONS, "write": WRITE_PERMISSIONS, "verify": VERIFY_PERMISSIONS}
APP_PERMISSIONS = {"contents": "write", "pull_requests": "write", "checks": "read", "statuses": "read",
                   "administration": "read", "metadata": "read"}
OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
REVIEWER_USER = OWNER
REVIEWER_TEAM = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
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


proposals_dir = config.proposals_dir  # shared with `rgtriage validate`


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
    owner = repo.split("/")[0].lower()
    for entry in policy.get("reviewers") or []:
        entry = str(entry)
        if "/" in entry:
            org, _, team = entry.partition("/")
            if not re.fullmatch(REVIEWER_TEAM, entry):
                problems.append(f"reviewer team {entry!r} must look like org/team-slug")
            elif org.lower() != owner:
                problems.append(f"reviewer team {entry!r} must belong to the repository's organization ({owner})")
        elif not re.fullmatch(REVIEWER_USER, entry):
            problems.append(f"reviewer {entry!r} is not a valid GitHub login")
    prefix = str(policy.get("branch_prefix") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*/", prefix) or is_protected(prefix.rstrip("/")):
        problems.append("branch_prefix must be a folder-style prefix such as feature/remedigenius/")
    if prefix and base and (base.startswith(prefix) or prefix.startswith(base + "/")):
        problems.append("branch_prefix must not contain the base branch")
    return problems


def split_reviewers(policy: dict) -> tuple[set[str], set[str]]:
    """Designated reviewers as two lowercase allowlists: user logins, and team slugs (the part after `org/`, org = the repository owner)."""
    owner = str(policy.get("repo") or "").split("/")[0].lower()
    users = {str(r).lower() for r in policy.get("reviewers") or [] if "/" not in str(r)}
    teams = {str(r).partition("/")[2].lower() for r in policy.get("reviewers") or [] if "/" in str(r) and str(r).partition("/")[0].lower() == owner}
    return users, teams


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
        self.users, self.teams = split_reviewers(policy)

    def _branch_ok(self, ref: str) -> bool:
        """A full branch name inside the feature prefix, spelled with safe characters only (no encodings, spaces, dot segments or .lock)."""
        if not ref.startswith(self.prefix) or len(ref) <= len(self.prefix) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", ref):
            return False
        segments = ref.split("/")
        return all(seg and not seg.startswith(".") and not seg.endswith(".lock") for seg in segments) and ".." not in ref and not ref.endswith(".")

    def check(self, method: str, path: str, body: dict | None = None, write_enabled: bool = True) -> None:
        method = method.upper()
        if "?" in path:
            path = path.split("?", 1)[0]
        raw = path
        path = urllib.parse.unquote(path)
        # The decoded text is what is checked and the original is what is sent, so they must mean the same thing: no double
        # encoding, no control characters, spaces or backslashes, no empty or dot segments.
        if ("%" in path or re.search(r"[\x00-\x20\x7f\\]", path) or "//" in path or not path.startswith("/")
                or any(seg in (".", "..") for seg in path.split("/")) or any(seg in (".", "..") for seg in raw.split("/"))):
            raise Denied("the request path is not in canonical form")
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
                users, teams = {n.lower() for n in body.get("reviewers") or []}, {n.lower() for n in body.get("team_reviewers") or []}
                if (not (users or teams) or users - self.users or teams - self.teams or set(body) - {"reviewers", "team_reviewers"}
                        or any("/" in n for n in teams)):
                    raise Denied("reviewers must be among the designated human reviewers (users by login, teams by slug within the repository's organization)")
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
        body = {"permissions": TOKEN_PERMISSIONS[kind]}
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
        kind = token_kind(method, path)
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


def token_kind(method: str, path: str) -> str:
    """Which narrowed token a request needs: writes get contents+PR write; protection reads get Administration: read; the rest read-only."""
    if method.upper() != "GET":
        return "write"
    return "verify" if re.search(r"/(branches/[^/]+/protection|rulesets)$", path.split("?", 1)[0]) else "read"


def _explain(status: int, raw: bytes, doing: str) -> str:
    try:
        message = json.loads(raw).get("message", "")
    except (ValueError, AttributeError):
        message = raw.decode("utf-8", "replace")[:200]
    hints = {0: "GitHub could not be reached (network or timeout)", 401: "credentials were rejected or expired: reconnect with `rgtriage github connect`",
             403: "GitHub refused (missing permission, organization approval pending, rate limit or the App was suspended)",
             404: "not found, or the App cannot see it (is the repository selected in the App installation?)",
             409: "conflict (the branch changed)", 429: "rate limit reached; wait and retry", 422: "GitHub rejected the request (for example a non-fast-forward branch update)"}
    hint = hints.get(status) or ("GitHub had a temporary server error; retry in a minute" if status >= 500 else "error")
    return f"GitHub {doing} failed ({status}): {hint}. {message}".strip()


# ------------------------------------------------------------------ protection check

def protection_check(client: Client) -> dict:
    """Read what protects the development base and the production branch. Never assumes; unknown is reported as unknown."""
    policy, checks, permission_problem = client.policy, [], False
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
        classic, denied = _read_protection(client, f"/repos/{repo}/branches/{urllib.parse.quote(branch, safe='')}/protection")
        if denied:
            permission_problem = True
            checks.append((f"{role} protection readable", "fail", f"{branch}: " + PERMISSION_REMEDY))
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
            rulesets, denied = _read_protection(client, f"/repos/{repo}/rulesets", empty=[])
            if denied and not permission_problem:
                permission_problem = True
                checks.append((f"{role} rulesets readable", "fail", PERMISSION_REMEDY))
            bypass = [a for r in rulesets for a in r.get("bypass_actors") or [] if a.get("actor_type") in ("Integration", "OrganizationAdmin", "RepositoryRole")]
            if bypass:
                checks.append((f"{role} bypass list", "warn", "rulesets list bypass actors; confirm the agent App is not among them"))
    ok = all(c[1] != "fail" for c in checks)
    return {"ok": ok, "permission_problem": permission_problem, "checks": [{"check": c, "result": r, "detail": d} for c, r, d in checks],
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "default_branch": default}


PERMISSION_REMEDY = ("the App cannot read branch protection: it needs 'Administration: read'. Approve the App's updated permissions "
                     "(GitHub: Settings, Applications, Installed GitHub Apps, Configure) or reconnect, then run `rgtriage github verify`.")


def _read_protection(client: Client, path: str, empty=None):
    """(data, permission_denied). A 404 means nothing exists there; a 403 is a permission problem and is never read as 'no protection'."""
    try:
        return client.call("GET", path, write_enabled=False) or ({} if empty is None else empty), False
    except GitHubError as exc:
        if exc.status == 403:
            return ({} if empty is None else empty), True
        raise


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
        out["remedy"] = ("Open the GitHub tab in the console and click Connect GitHub. (Command line instead: `sudo rgdesk github setup` on the instance, or from your "
                         "computer `python tools/github_connect_spot.py --stack <name>`.)")
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
    if check.get("permission_problem"):
        out["remedy"] = "Permissions, not protection: " + PERMISSION_REMEDY
        return out
    out["remedy"] = ("Fix on GitHub (a repository administrator can apply the rulesets in deploy/github), then run `rgtriage github verify`: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed)) if failed else (
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

def manifest(name: str, redirect_url: str, homepage: str, setup_url: str = "") -> dict:
    data = {"name": name, "url": homepage, "redirect_url": redirect_url, "public": False, "default_permissions": APP_PERMISSIONS,
            "default_events": [], "description": "RemediGenius-CE: proposes IaC fixes as pull requests into a development branch. Never merges or approves."}
    if setup_url:
        data["setup_url"] = setup_url
    return data


def app_install_url(slug_: str) -> str:
    return f"https://github.com/apps/{slug_}/installations/new"


def create_app_from_code(code: str, owner: str = "", post=None) -> str:
    """Exchange GitHub's one-time manifest code for the App, save its key and identity (0600, desk-only) and return the App's slug.
    Used by the command line and the web console alike. Every failure is a GitHubError with a sanitized, actionable message and leaves
    nothing half-saved; the message never contains the key or the code."""
    post = post or _http
    try:
        status_, _, raw = post("POST", f"{API}/app-manifests/{code}/conversions", {"Accept": "application/vnd.github+json", "User-Agent": "RemediGenius-CE"}, None)
    except (urllib.error.URLError, TimeoutError, OSError, GitHubError) as exc:
        raise GitHubError(f"could not reach GitHub to finish creating the App ({type(exc).__name__}); nothing was saved, connect again") from None
    if status_ != 201:
        raise GitHubError(_redact(_explain(status_, raw, "creating the App from the manifest"), []))
    try:
        data = json.loads(raw)
        app_id, app_slug, pem = int(data["id"]), str(data["slug"]), str(data["pem"])
        if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", app_slug) or not pem.startswith("-----BEGIN"):
            raise ValueError("unexpected shape")
    except (ValueError, KeyError, TypeError):
        raise GitHubError("GitHub's answer was not what a created App looks like, so nothing was saved. If an App named RemediGenius-CE-... "
                          "was created, delete it at https://github.com/settings/apps and connect again") from None
    try:
        _write_private(key_path(), pem)
        _write_private(home() / "app.json", json.dumps({"app_id": app_id, "slug": app_slug, "owner": (data.get("owner") or {}).get("login", owner or "personal"),
                                                        "html_url": data.get("html_url")}, indent=1))
    except OSError as exc:
        for name in ("app.pem", "app.json"):
            try:
                (home() / name).unlink(missing_ok=True)  # leave no half-saved connection behind
            except OSError:
                pass
        raise GitHubError(f"the App '{app_slug}' was created, but its key could not be saved ({exc.strerror or type(exc).__name__}). Delete the App at "
                          f"https://github.com/settings/apps/{app_slug}/advanced and connect again") from None
    return app_slug


def plan_connection(reconnect: bool = False, transport=None) -> dict:
    """What `connect` should do given what became of any existing App: create | resume | healthy | unreachable (see probe_connection)."""
    existing = load_app()
    if not (existing.get("app_id") and key_path().is_file()):
        return {"action": "create", "message": ""}
    verdict = probe_connection(existing, transport)
    if verdict["state"] == "unreachable":
        return {"action": "unreachable", "detail": verdict["detail"]}
    if verdict["state"] == "healthy" and not reconnect:
        return {"action": "healthy", "app": existing}
    if verdict["state"] in ("not_installed", "reinstalled") and not reconnect:
        return {"action": "resume", "app": existing, "message": "The App exists on GitHub but is not installed" +
                (" any more" if existing.get("installation_id") else "") + "; resuming at the install step."}
    message = ("The App no longer exists on GitHub (deleted, or its key was rejected): creating a replacement. Its old installation went away with it."
               if verdict["state"] == "app_gone" else
               "Creating a new App as asked; the previous App and its installation stay on GitHub until you remove them.")
    return {"action": "create", "message": message, "forget": True}


def _already_connected(app: dict) -> Denied:
    return Denied(f"GitHub is already connected (App {app.get('slug')}). To replace it, run `rgtriage github disconnect` first, or "
                  "`rgtriage github connect --reconnect` to create a new App (the old App and its installation stay on GitHub until you remove them).")


# ---------------------------------------------------------------- the web console flow (the browser does what the CLI's local page does)

PENDING_TTL = 3600
CALLBACK_PATH = "/api/plugins/rg-github/callback"
PAGE_PATH = "/github"


def allowed_origin(origin: str) -> bool:
    """The web console may only receive GitHub's redirect at a loopback address (the SSM tunnel) or an origin the operator listed in
    RGGITHUB_ALLOWED_ORIGINS: GitHub's one-time code must never be sent to a host the operator did not choose."""
    parsed = urllib.parse.urlparse(origin)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/"):
        return False
    base = f"{parsed.scheme}://{parsed.netloc}"
    listed = [o.strip().rstrip("/") for o in os.environ.get("RGGITHUB_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return parsed.hostname in ("127.0.0.1", "localhost", "::1") or base in listed


def _check_return_urls(redirect_url: str, setup_url: str) -> None:
    red, setup = urllib.parse.urlparse(redirect_url), urllib.parse.urlparse(setup_url)
    origin = f"{red.scheme}://{red.netloc}"
    if (not allowed_origin(origin) or red.path != CALLBACK_PATH or red.query or red.fragment or f"{setup.scheme}://{setup.netloc}" != origin
            or setup.path != PAGE_PATH or setup.fragment):
        raise Denied("the return addresses must be this console's own loopback address (or an origin in RGGITHUB_ALLOWED_ORIGINS) and its GitHub page")


def begin_connect(redirect_url: str, setup_url: str, owner: str = "", reconnect: bool = False, transport=None) -> dict:
    """Step 1 of connecting from the console: returns what the browser posts to GitHub. Nothing secret leaves the desk."""
    _check_return_urls(redirect_url, setup_url)
    if owner and not re.fullmatch(OWNER, owner):
        raise Denied("the organization name is not valid")
    plan = plan_connection(reconnect, transport)
    if plan["action"] == "unreachable":
        raise GitHubError(f"cannot check the existing connection ({plan['detail']}); fix the network and try again")
    if plan["action"] == "healthy":
        raise _already_connected(plan["app"])
    if plan["action"] == "resume":
        app = plan["app"]
        app.pop("installation_id", None)
        app.pop("installed_on", None)
        _write_private(home() / "app.json", json.dumps(app, indent=1))
        return {"resume": True, "message": plan["message"], "slug": app["slug"], "install_url": app_install_url(app["slug"])}
    if plan.get("forget"):
        forget_connection()
    state = secrets.token_urlsafe(24)
    name = f"RemediGenius-CE-{secrets.token_hex(3)}"
    _write_private(home() / "pending.json", json.dumps({"state_sha256": hashlib.sha256(state.encode()).hexdigest(), "owner": owner, "created": time.time(),
                                                        "redirect_url": redirect_url}))
    target = f"https://github.com/organizations/{urllib.parse.quote(owner)}/settings/apps/new" if owner else "https://github.com/settings/apps/new"
    return {"resume": False, "message": plan.get("message", ""), "target": f"{target}?state={state}",
            "manifest": manifest(name, redirect_url, "https://github.com/IaCGenius/RemediGenius", setup_url)}


def finish_connect(code: str, state: str, transport=None) -> dict:
    """Step 2: GitHub sent the browser back with a code. The state must be the one issued by step 1 (once, within an hour)."""
    pending = _read_json(home() / "pending.json")
    (home() / "pending.json").unlink(missing_ok=True)  # single use, whatever happens next
    expected = pending.get("state_sha256", "")
    if (not expected or not hmac.compare_digest(expected, hashlib.sha256(str(state).encode()).hexdigest())
            or time.time() - float(pending.get("created", 0)) > PENDING_TTL):
        raise Denied("this connection attempt expired or did not start here; start again with Connect GitHub")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", str(code)):
        raise Denied("GitHub did not send a valid code; start again")
    slug_ = create_app_from_code(code, pending.get("owner", ""), transport)
    return {"slug": slug_, "install_url": app_install_url(slug_)}


def install_status(transport=None, sign=None) -> dict:
    """Is the App installed yet? When it is, remember the installation. Called repeatedly by the console while the person installs."""
    app = load_app()
    if not (app.get("app_id") and key_path().is_file()):
        return {"app": False, "installed": False}
    client = Client({}, app, transport=transport, sign=sign)
    status_, _, raw = client._raw("GET", "/app/installations", client.jwt(), None)
    if status_ != 200:
        raise GitHubError(_redact(_explain(status_, raw, "checking the installation"), []), status_)
    installs = json.loads(raw)
    if not installs:
        return {"app": True, "installed": False, "slug": app["slug"], "install_url": app_install_url(app["slug"])}
    if app.get("installation_id") not in [i["id"] for i in installs]:
        app["installation_id"], app["installed_on"] = installs[0]["id"], (installs[0].get("account") or {}).get("login")
        _write_private(home() / "app.json", json.dumps(app, indent=1))
    return {"app": True, "installed": True, "slug": app["slug"], "account": app.get("installed_on")}


def web_repos(transport=None, sign=None) -> dict:
    return {"repos": installation_repos(load_app(), transport, sign)}


def web_branches(repo: str, transport=None, sign=None) -> dict:
    app = load_app()
    if repo.lower() not in {r.lower() for r in installation_repos(app, transport, sign)}:
        raise Denied(f"{repo} is not selected in the App installation")
    branches, default = candidate_bases(repo, app, transport, sign)
    return {"branches": branches, "default": default, "suggested": "dev" if "dev" in branches else (branches[0] if len(branches) == 1 else ""),
            "admin_command": admin_branch_command(repo, "dev", default or "main") if not branches else ""}


def connect(owner: str = "", port: int = 8743, open_browser: bool = True, timeout: int = 900, transport=None, say=print,
            reconnect: bool = False) -> dict:
    """Create the App through GitHub's manifest flow and wait for the installation. Runs on the host; the browser reaches
    http://localhost:<port> directly (or through an SSM port forward on Spot)."""
    plan = plan_connection(reconnect, transport)
    if plan["action"] == "unreachable":
        raise GitHubError(f"cannot check the existing connection ({plan['detail']}); fix the network and run connect again")
    if plan["action"] == "healthy":
        raise _already_connected(plan["app"])
    if plan["action"] == "resume":
        say(plan["message"])
        existing = plan["app"]
        existing.pop("installation_id", None)
        existing.pop("installed_on", None)
        _write_private(home() / "app.json", json.dumps(existing, indent=1))
        return wait_for_installation(existing, timeout, transport=transport, say=say)
    if plan.get("message"):
        say(plan["message"])
    if plan.get("forget"):
        forget_connection()
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

        def _fail(self, message: str, code: int = 502):
            result["error"] = message
            done.set()
            try:
                self._page("The connection could not be completed. The reason is shown in the terminal where you ran connect.", code)
            except OSError:
                pass

        def _created(self, query):
            if query.get("state", [""])[0] != state:
                return self._page("State mismatch: start again from the terminal.", 400)
            code = query.get("code", [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", code):
                return self._page("Missing code.", 400)
            try:
                app_slug = create_app_from_code(code, owner, post)
            except GitHubError as exc:
                return self._fail(str(exc))
            result["created"] = app_slug
            done.set()
            return self._page(f"The App was created. Next: <a href=\"https://github.com/apps/{html.escape(app_slug)}/installations/new\">install it</a> "
                              f"and select only the repository RemediGenius may use. You can close this tab afterwards.")

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == "/":
                return self._page(form)
            if url.path == "/created":
                try:
                    return self._created(query)
                except Exception as exc:  # never leave the waiting command hanging: report what failed, without detail that could hold a secret
                    return self._fail(f"the App callback failed unexpectedly ({type(exc).__name__}); nothing is connected, run connect again")
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
    return wait_for_installation(load_app(), timeout, transport=transport, say=say)


def probe_connection(app: dict, transport=None) -> dict:
    """Ask GitHub what became of this App: healthy | not_installed | reinstalled | app_gone | unreachable (with the reason)."""
    client = Client({}, app, transport=transport)
    try:
        status_, _, raw = client._raw("GET", "/app/installations", client.jwt(), None)
    except GitHubError as exc:  # the key file cannot sign: it is not a working App key any more
        return {"state": "app_gone", "detail": str(exc)}
    if status_ == 401:
        return {"state": "app_gone", "detail": "GitHub rejected the App's key"}
    if status_ != 200:
        return {"state": "unreachable", "detail": _redact(_explain(status_, raw, "checking the App"), [])}
    try:
        ids = [i["id"] for i in json.loads(raw)]
    except (ValueError, KeyError, TypeError):
        return {"state": "unreachable", "detail": "unexpected answer from GitHub"}
    if app.get("installation_id") in ids:
        return {"state": "healthy", "detail": ""}
    return {"state": "reinstalled" if ids else "not_installed", "detail": ""}


def forget_connection() -> None:
    """Delete the local App identity (a replacement is about to be created). Writes stay off until the new App is verified."""
    for name in ("app.pem", "app.json"):
        (home() / name).unlink(missing_ok=True)
    policy = load_policy()
    if policy:
        policy["writes_enabled"] = False
        policy.pop("protection", None)
        _write_private(home() / "policy.json", json.dumps(policy, indent=1))


def wait_for_installation(app: dict, timeout: int, transport=None, say=print) -> dict:
    """Poll GitHub until the App is installed somewhere, then remember the installation."""
    say(f"App: {app['slug']}. Install it and select ONLY the repository RemediGenius may use: https://github.com/apps/{app['slug']}/installations/new")
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
        elif status_ == 401:
            raise GitHubError(_explain(status_, raw, "reading the App's installations"), status_)
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


GEN_START, GEN_END = "<!-- rg-generated:start -->", "<!-- rg-generated:end -->"
NOTES_STUB = "## Notes\n\n_Add the owning team and context here. The desk only rewrites the generated block above and never touches text outside it._"


def merge_repository_page(existing, repo: str, base: str, generated: str, facts: dict) -> tuple[dict, str, str]:
    """The Repository concept after a refresh: generated facts are replaced, everything a person wrote or reviewed is kept.

    A new page gets a generated block and a notes section. An existing page keeps its title, description, owner, notes, review history
    and any other field; only the block between the markers (and the `remedigenius` facts) change. If the page has no markers (an earlier
    version, or a person rewrote it), the block is appended and nothing is removed. Review: when the repository, the development
    branch or the kind of IaC changes, `stale_after` is set to now so the page shows as stale in the Knowledge tab and a person
    re-confirms it, with their earlier review history intact; a new commit alone does not."""
    block = f"{GEN_START}\n{generated}\n{GEN_END}"
    if existing is None or existing.error:
        meta = {"type": "Repository", "title": repo, "description": f"IaC repository {repo} (development branch {base})", "remedigenius": facts}
        return meta, f"{block}\n\n{NOTES_STUB}\n", "created"
    meta, body = dict(existing.meta), existing.body
    previous = meta.get("remedigenius") if isinstance(meta.get("remedigenius"), dict) else {}
    meta["remedigenius"] = {**previous, **facts}
    if GEN_START in body and GEN_END in body:
        head, _, rest = body.partition(GEN_START)
        _, _, tail = rest.partition(GEN_END)
        body = f"{head}{block}{tail}"
    else:
        body = f"{body.rstrip()}\n\n{block}\n"
    material = [k for k in ("repo", "base", "iac") if previous and previous.get(k) != facts.get(k)]
    note = "updated"
    if material:
        meta["stale_after"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta["remedigenius"]["review_note"] = f"{', '.join(material)} changed on {meta['stale_after'][:10]}: please re-confirm this page"
        note = "updated, needs re-confirmation (" + ", ".join(material) + " changed)"
    return meta, body, note


def record_repository(name: str, repo: str, base: str, generated: str, facts: dict) -> str:
    path = f"repositories/{name}.md"
    bundle = knowledge.bundle()
    try:
        existing = bundle.read(path) if bundle.path_of(path).exists() else None
    except Exception:
        existing = None
    meta, body, note = merge_repository_page(existing, repo, base, generated, facts)
    knowledge.save(meta, body, "human:desk-github", path=path, replace=True)
    return f"{path} ({note})"


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
    generated = (f"Connected through the RemediGenius GitHub App. Fixes for resources deployed from this repository become pull requests from "
                 f"`{client.policy['branch_prefix']}...` branches into `{base}`; a human reviewer approves and merges.\n\n"
                 f"- Development branch: `{base}` (commit `{sha[:10]}`, mirrored read-only at `{target}`)\n"
                 f"- Infrastructure code found (from file names): " + (", ".join(f"{k} in {', '.join(v[:5])}" for k, v in kinds.items()) or "none detected") +
                 f"\n- Designated reviewers: {', '.join(client.policy.get('reviewers') or []) or 'not set'}")
    facts = {"repo": repo, "base": base, "commit": sha, "iac": sorted(kinds)}
    try:
        recorded = record_repository(name, repo, base, generated, facts)
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


def branch_name(prefix: str, ref: str, topic: str = "") -> str:
    """One branch per remediation task, from the finding ref only (immutable). Title and topic are presentation and never change it."""
    return f"{prefix}fix-{slug(ref, 40)}"


def clean_text(text, limit: int = 4000) -> str:
    """Text the agent wrote, made safe to publish: no 12-digit account ids, no tokens, and no @mentions that would notify people."""
    text = _redact(str(text or ""), [])
    text = re.sub(r"\b\d{12}\b", "************", text)
    text = re.sub(r"(?<![\w`])@(?=[A-Za-z0-9])", "@\u200b", text)
    return text[:limit]


def pr_body(finding: dict, files: list[str], validation: list[dict], evidence: str, change: str, effect: str, risk: str, rollback: str,
            validated_on: str = "") -> str:
    sanitize = clean_text
    rows = "\n".join(f"- `{v['check']}`: **{v['result']}**" + (f" ({sanitize(v['detail'])[:160]})" if v.get("detail") else "") for v in validation) or "- not validated"
    return (f"## Finding\n{sanitize(finding.get('title') or finding.get('ref'))}\n\nRef: `{sanitize(finding.get('ref'))}`\n\n"
            f"## Evidence\n{sanitize(evidence) or 'See the RemediGenius board.'}\n\n## Proposed change\n{sanitize(change)}\n\nFiles:\n" +
            "\n".join(f"- `{f}`" for f in files) + f"\n\n## Expected effect\n{sanitize(effect)}\n\n## Validation\n{rows}\n\n"
            f"## Operational risk\n{sanitize(risk)}\n\n## Rollback\n{sanitize(rollback)}\n\n---\n"
            "Opened by RemediGenius-CE as a bot. It never approves or merges: a human reviewer decides. Terraform validation checks syntax and "
            "provider schema only, not a plan.")


def _default_validate(tree: Path, paths: dict[str, bytes]) -> list[dict]:
    """Check the candidate tree (the parent commit's files with the proposal applied) in the isolated validation service."""
    files = _validators.snapshot_dir(tree)
    files.update(paths)
    return _validators.check_tree(files, sorted(paths))


def _prs_for(client: Client, repo: str, branch: str) -> list[dict]:
    owner = repo.split("/")[0]
    return client.call("GET", f"/repos/{repo}/pulls?head={urllib.parse.quote(owner)}:{urllib.parse.quote(branch, safe='/')}&state=all&per_page=50") or []


def _require_workflow_pr(client: Client, pr: dict, repo: str, branch: str) -> None:
    """An existing PR is only updated when it is still exactly what this workflow opened: same repository, our head, the development base."""
    base = (client.policy or {}).get("base")
    problems = []
    if (pr.get("base") or {}).get("ref") != base:
        problems.append(f"targets {(pr.get('base') or {}).get('ref')!r} instead of the development branch {base!r}")
    for side, expected in (("base", repo), ("head", repo)):
        full = ((pr.get(side) or {}).get("repo") or {}).get("full_name")
        if full and full.lower() != repo.lower():
            problems.append(f"its {side} is in {full}, not {repo}")
    if (pr.get("head") or {}).get("ref") != branch:
        problems.append(f"its head is {(pr.get('head') or {}).get('ref')!r}, not {branch!r}")
    if problems:
        raise Denied(f"existing PR #{pr.get('number')} {'; '.join(problems)}. Nothing was pushed or changed: close it, or point it back at "
                     f"{base!r}, then publish again")


def _task_branch(client: Client, repo: str, ref: str) -> tuple[str, dict | None]:
    """The branch and open PR for this task. A PR that was merged earlier starts a numbered follow-up branch (`-r2`, `-r3`);
    one that was closed without merging is simply replaced by a new PR from the same branch."""
    stable = branch_name(client.policy["branch_prefix"], ref)
    branch = stable
    for generation in range(2, 12):
        prs = _prs_for(client, repo, branch)
        open_ = [pr for pr in prs if pr.get("state") == "open"]
        if len(open_) > 1:
            raise Denied(f"more than one open PR from {branch}: " + ", ".join(f"#{pr['number']}" for pr in open_) + "; close the extra ones first")
        if open_:
            _require_workflow_pr(client, open_[0], repo, branch)
            return branch, open_[0]
        if any(pr.get("merged_at") for pr in prs):
            branch = f"{stable}-r{generation}"
            continue
        return branch, None
    raise Denied("too many earlier merged PRs for this finding; ask a person to look at it")


def _reviewer_requests(client: Client, pr: dict) -> dict:
    """The reviewers still to ask: designated users and team slugs not already requested on the PR."""
    users, teams = split_reviewers(client.policy)
    have_users = {(u.get("login") or "").lower() for u in pr.get("requested_reviewers") or []}
    have_teams = {(t.get("slug") or "").lower() for t in pr.get("requested_teams") or []}
    asks = {"reviewers": sorted(users - have_users), "team_reviewers": sorted(teams - have_teams)}
    return {k: v for k, v in asks.items() if v}


def publish(ref: str, files: dict[str, bytes], title: str = "", client: Client | None = None, validators=None, finding: dict | None = None,
            evidence: str = "", change: str = "", effect: str = "", risk: str = "", rollback: str = "", topic: str = "") -> dict:
    """Validate, push to the task's feature branch and open or update ONE PR into the development base.

    Order matters: the existing PR and branch are resolved and checked first (nothing is changed if they are not what this workflow
    created), the validated tree is exactly parent commit + proposal, and every later step is safe to repeat, so a retry after a partial
    failure finishes the job without a second commit or PR."""
    client = client or Client()
    st = status(client, verify=True)  # protection is re-verified for every publish; a failed check denies the write
    if not st["writes_enabled"]:
        raise Denied(f"writes are not enabled ({st['state']}): {st['remedy']}")
    if validators is None and not _validators.isolated():
        raise Denied("validation isolation is not configured (RGVALIDATE_SOCKET): the checks run untrusted tools and must not run next to the GitHub key")
    run_validators = _default_validate if validators is None else validators
    policy, repo = client.policy, client.policy["repo"]
    paths = {_safe_repo_path(p): d for p, d in files.items()}
    if len(paths) > MAX_FILES:
        raise Denied("too many files")
    warnings: list[str] = []

    # 1. resolve and check the existing PR and branch before any change
    branch, open_pr = _task_branch(client, repo, ref)
    quoted = urllib.parse.quote(branch, safe="/")
    base = client.call("GET", f"/repos/{repo}/branches/{urllib.parse.quote(policy['base'], safe='')}", write_enabled=False)
    if base is None:
        raise GitHubError(f"development branch {policy['base']!r} was not found")
    base_sha = base["commit"]["sha"]
    existing = client.call("GET", f"/repos/{repo}/git/ref/heads/{quoted}", write_enabled=False)
    if open_pr and not existing:
        raise GitHubError(f"PR #{open_pr['number']} is open but its branch {branch} was not found; ask a person to look at it")
    parent = existing["object"]["sha"] if existing else base_sha
    if existing:
        last = client.call("GET", f"/repos/{repo}/commits/{parent}", write_enabled=False) or {}
        author = ((last.get("author") or {}).get("login") or "")
        if author and author.lower() != f"{client.app.get('slug', '')}[bot]".lower():
            raise Denied(f"branch {branch} already has commits by {author}; refusing to build on or overwrite someone else's work")
    parent_tree = (client.call("GET", f"/repos/{repo}/git/commits/{parent}", write_enabled=False) or {})["tree"]["sha"]

    # 2. validate exactly what will be committed: the parent commit's files with the proposal applied, with no credentials in reach
    validation: list[dict] = []
    if run_validators is not False:
        with tempfile.TemporaryDirectory(prefix="rg-github-") as scratch:
            tree_dir = Path(scratch) / "repo"
            tree_dir.mkdir()
            _extract_tarball(client.raw_read(f"/repos/{repo}/tarball/{parent}"), tree_dir)
            validation = run_validators(tree_dir, paths)
    validated_on = f"{parent[:10]} ({'the branch head' if existing else 'the development branch'})"
    if any(v["result"] == "fail" for v in validation):
        return {"published": False, "reason": "validation failed; nothing was pushed", "validation": validation, "validated_on": validated_on}

    # 3. build the commit; an unchanged tree only skips the commit and ref update, never the PR
    entries = []
    for path, data in sorted(paths.items()):
        blob = client.call("POST", f"/repos/{repo}/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    tree = client.call("POST", f"/repos/{repo}/git/trees", {"base_tree": parent_tree, "tree": entries})
    new_commit = None
    if tree["sha"] == parent_tree:
        if not existing:
            return {"published": False, "reason": "the proposal changes nothing compared with the development branch; nothing was pushed",
                    "validation": validation, "validated_on": validated_on}
    else:
        clean_title = clean_text(title, 200).replace("\n", " ").strip()
        commit = client.call("POST", f"/repos/{repo}/git/commits", {
            "message": f"{clean_title or 'RemediGenius fix'}\n\nRef: {clean_text(ref, 40)}\nProposed by RemediGenius-CE; needs human review.",
            "tree": tree["sha"], "parents": [parent]})
        if existing:
            try:
                client.call("PATCH", f"/repos/{repo}/git/refs/heads/{quoted}", {"sha": commit["sha"], "force": False})
            except GitHubError as exc:
                if exc.status in (409, 422):
                    raise GitHubError(f"the branch moved while publishing (not a fast-forward). Nothing was overwritten; run publish again. {exc}", exc.status)
                raise
        else:
            client.call("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
        new_commit = commit["sha"]

    # 4. the PR, the reviewers and the remediation record, each safe to repeat
    body = pr_body(finding or {"ref": ref, "title": title}, sorted(paths), validation, evidence, change or title, effect, risk, rollback, validated_on)
    pr_title = clean_text(title, 200).replace("\n", " ").strip()
    try:
        if open_pr:
            pr = client.call("PATCH", f"/repos/{repo}/pulls/{open_pr['number']}", {"title": pr_title or open_pr["title"], "body": body})
            action = "updated" if new_commit else "unchanged"
            pr = {**open_pr, **(pr or {})}
        else:
            pr = client.call("POST", f"/repos/{repo}/pulls", {"title": pr_title or f"RemediGenius fix for {clean_text(ref, 40)}", "body": body, "head": branch,
                                                              "base": policy["base"]})
            action = "opened"
    except GitHubError as exc:
        return {"published": False, "partial": True, "branch": branch, "commit": new_commit or parent, "validation": validation, "validated_on": validated_on,
                "reason": f"the branch {branch} has the change but the pull request could not be created or updated ({exc}). Run publish again to finish; "
                          "the commit will not be repeated"}
    asks = _reviewer_requests(client, pr)
    if asks:
        try:
            client.call("POST", f"/repos/{repo}/pulls/{pr['number']}/requested_reviewers", asks)
        except (GitHubError, Denied) as exc:
            warnings.append(f"reviewers were not requested ({exc}); ask them on GitHub, or run publish again")
    linked = link_fix_record(ref, pr["html_url"])
    if not linked:
        warnings.append("no fix record for this finding yet: record `decide status=fixing` with this PR so the desk tracks it")
    return {"published": True, "changed": new_commit is not None, "action": action, "branch": branch, "pr": pr["html_url"], "number": pr["number"],
            "commit": new_commit, "validation": validation, "validated_on": validated_on, "warnings": warnings, "linked_fix_record": linked}


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


# ------------------------------------------------------------------ guided setup (one command, safe to repeat)

def prerequisites(transport=None) -> list[dict]:
    """What must be true before setup can work. Each row: {check, ok, blocking, detail, remedy}."""
    rows = []

    def add(check, ok, detail="", remedy="", blocking=True):
        rows.append({"check": check, "ok": bool(ok), "blocking": blocking, "detail": detail, "remedy": remedy})
    isolated_home = bool(os.environ.get("RGGITHUB_HOME"))
    add("key folder isolated from the agent", isolated_home, os.environ.get("RGGITHUB_HOME", "RGGITHUB_HOME is not set"),
        "" if isolated_home else ISOLATION_REMEDY)
    if isolated_home:
        try:
            probe = home(create=True) / ".write-test"
            probe.write_text("x")
            probe.unlink()
            add("key folder writable", True, str(home()))
        except OSError as exc:
            add("key folder writable", False, str(exc), "Run this command as the desk user: `sudo rgdesk github setup`.")
    add("openssl available (signs the App token)", shutil.which("openssl"), shutil.which("openssl") or "not found", "Install openssl.")
    pong = _validators.ping()
    add("validation service reachable (keeps untrusted tools away from the key)", bool(pong.get("ok")),
        "running" if pong.get("ok") else (pong.get("error") or "RGVALIDATE_SOCKET is not set"),
        "Check `systemctl status remedigenius-validate` on the instance.")
    try:
        status_, _, _ = (transport or _http)("GET", f"{API}/", {"Accept": "application/vnd.github+json", "User-Agent": "RemediGenius-CE"}, None)
        reached = status_ == 200
        add("github.com API reachable", reached, f"HTTP {status_}", "The instance needs outbound HTTPS to api.github.com.")
    except (urllib.error.URLError, OSError, GitHubError) as exc:
        add("github.com API reachable", False, type(exc).__name__, "The instance needs outbound HTTPS to api.github.com.")
    tools = _validators.available()
    for name, present in tools.items():
        add(f"{name} installed", present, "yes" if present else "missing: changes touching those files are reported as NOT validated", blocking=False)
    return rows


def installation_repos(app: dict, transport=None, sign=None) -> list[str]:
    """The repositories the operator selected when installing the App (operator-only: this is how setup offers a choice)."""
    client = Client({}, app, transport=transport, sign=sign)
    installation = app.get("installation_id")
    if not installation:
        raise GitHubError("the App is not installed yet")
    jwt = client.jwt()
    status_, _, raw = client._raw("POST", f"/app/installations/{int(installation)}/access_tokens", jwt, {"permissions": READ_PERMISSIONS})
    if status_ != 201:
        raise GitHubError(_redact(_explain(status_, raw, "minting an installation token"), [jwt]), status_)
    token = json.loads(raw)["token"]
    status_, _, raw = client._raw("GET", "/installation/repositories", token, None)
    if status_ != 200:
        raise GitHubError(_redact(_explain(status_, raw, "listing the selected repositories"), [token]), status_)
    return sorted(r["full_name"] for r in json.loads(raw).get("repositories", []))


def candidate_bases(repo: str, app: dict, transport=None, sign=None) -> tuple[list[str], str]:
    """(branches that could be the development base, the default branch)."""
    probe = {"repo": repo, "base": "setup-probe", "branch_prefix": DEFAULT_PREFIX, "reviewers": []}
    client = Client(probe, app, transport=transport, sign=sign)
    default = (client.call("GET", f"/repos/{repo}", write_enabled=False) or {}).get("default_branch", "")
    branches = client.call("GET", f"/repos/{repo}/branches?per_page=100", write_enabled=False) or []
    names = [b["name"] for b in branches if not is_protected(b["name"], default)]
    return sorted(names), default


def admin_branch_command(repo: str, base: str, default: str) -> str:
    return f"gh api repos/{repo}/git/refs -f ref=refs/heads/{base} -f sha=$(gh api repos/{repo}/commits/{default} --jq .sha)"


def setup(repo: str = "", base: str = "", reviewers: list[str] | None = None, org: str = "", port: int = 8743, ask=input, say=print,
          transport=None, sign=None, timeout: int = 900, interactive: bool = True, open_browser: bool = False, reconnect: bool = False) -> dict:
    """One guided command: prerequisites, connect (or resume), repository, development branch, reviewers, protection check, next step.

    Every step looks at the real state first, so an interrupted setup is simply run again. Finishing is NOT the same as working:
    the last lines say whether PRs can be created and, if not, exactly what is missing."""
    say("RemediGenius GitHub setup\n")
    say("1. Prerequisites")
    rows = prerequisites(transport)
    for row in rows:
        say(f"   [{'ok' if row['ok'] else ('MISSING' if row['blocking'] else 'warn')}] {row['check']}" + (f": {row['detail']}" if row["detail"] else ""))
    blockers = [r for r in rows if r["blocking"] and not r["ok"]]
    if blockers:
        for row in blockers:
            say(f"   -> {row['remedy']}")
        return {"state": "Blocked", "step": "prerequisites", "next": blockers[0]["remedy"]}

    say("\n2. GitHub App")
    app = load_app()
    if reconnect or not (app.get("app_id") and key_path().is_file()) or not app.get("installation_id"):
        result = connect(owner=org, port=port, open_browser=open_browser, timeout=timeout, transport=transport, say=lambda m: say("   " + m),
                         reconnect=reconnect)
        say(f"   Connected: App {result['app']} installed on {result['account']}.")
        app = load_app()
    else:
        verdict = probe_connection(app, transport)
        if verdict["state"] != "healthy":
            say(f"   The saved connection is not healthy ({verdict['state']}); reconnecting.")
            result = connect(owner=org, port=port, open_browser=open_browser, timeout=timeout, transport=transport, say=lambda m: say("   " + m),
                             reconnect=False)
            app = load_app()
        else:
            say(f"   Already connected: {app.get('slug')}[bot] (installed on {app.get('installed_on') or 'your selection'}).")

    say("\n3. Repository (only the repositories you selected when installing the App are offered)")
    repos = installation_repos(app, transport, sign)
    if not repos:
        raise GitHubError("the App is installed on no repository. Choose repositories at https://github.com/settings/installations and run setup again.")
    if not repo:
        if len(repos) == 1:
            repo = repos[0]
            say(f"   Only one repository is selected: {repo}")
        elif interactive:
            for i, name in enumerate(repos, 1):
                say(f"   {i}. {name}")
            repo = repos[int(ask("   Number of the repository to use: ").strip()) - 1]
        else:
            raise Denied("several repositories are selected; pass --repo OWNER/NAME")
    if repo.lower() not in {r.lower() for r in repos}:
        raise Denied(f"{repo} is not selected in the App installation (selected: {', '.join(repos)})")

    say("\n4. Development branch (pull requests go here; never your production branch)")
    branches, default = candidate_bases(repo, app, transport, sign)
    if not base:
        suggestion = "dev" if "dev" in branches else (branches[0] if len(branches) == 1 else "")
        if not branches:
            command = admin_branch_command(repo, "dev", default or "main")
            say(f"   {repo} has no development branch yet (only {default or 'the default branch'}). A repository administrator must create one, with their own login:\n"
                f"       {command}\n   Then run setup again.")
            return {"state": "Blocked", "step": "development branch", "next": command}
        if interactive:
            say("   Branches: " + ", ".join(branches))
            base = ask(f"   Development branch [{suggestion}]: ").strip() or suggestion
        else:
            base = suggestion
        if not base:
            raise Denied("several branches could be the base; pass --base NAME")
    if base not in branches:
        if is_protected(base, default):
            raise Denied(f"{base!r} is a production or default branch and can never be the development base")
        raise Denied(f"branch {base!r} does not exist in {repo}; existing candidates: {', '.join(branches) or 'none'}")

    say("\n5. Human reviewers (people or an org/team who approve and merge; bots are refused)")
    names = list(reviewers or [])
    if not names and interactive:
        names = [n.strip() for n in ask("   GitHub login(s) or org/team, comma separated: ").split(",") if n.strip()]
    if not names:
        raise Denied("at least one human reviewer is required; pass --reviewer LOGIN")

    say("\n6. Checking the repository and its protections")
    final = configure(repo, base, DEFAULT_PREFIX, names, transport=transport, sign=sign)
    for c in (final.get("protection") or {}).get("checks", []):
        say(f"   [{c['result']}] {c['check']}: {c['detail']}")
    say(f"\nResult: {final['state']}. Writes enabled: {'yes' if final['writes_enabled'] else 'no'}.")
    if final.get("repository"):
        say(f"   Repository knowledge: {final['repository'].get('knowledge') or final['repository'].get('note')}")
    if final["writes_enabled"]:
        say("   Next: ask the agent for a fix and approve the pull request; run `rgtriage github status` any time. "
            "Setup finishing is not proof of a working flow: the first PR is the real test.")
    else:
        say(f"   Next step: {final['remedy']}")
    return final


# ------------------------------------------------------------------ proof that GitHub itself rejects what the adapter never sends

def probe_protections(client: Client, confirm_repo: str, say=print) -> dict:
    """Operator-only evidence run. Using the App's own write token and deliberately bypassing the adapter's gate, attempt the operations the
    adapter never sends, and record whether GitHub rejects them. Every attempt is expected to be REJECTED; any acceptance is a FAIL
    (and, because the attempts are real, may have changed the repository: run this only against a disposable repository).

    It refuses to run unless the operator names the repository, the configured policy matches it, and the protection check passes."""
    policy = client.policy
    if not policy.get("repo") or confirm_repo.lower() != policy["repo"].lower():
        raise Denied("pass --confirm-disposable OWNER/REPO with the configured repository to confirm this is a disposable test repository")
    check = protection_check(client)
    if not check["ok"]:
        raise Denied("the protection check does not pass, so these probes would not be safe to run; fix the protections and run `verify` first")
    repo, base, default = policy["repo"], policy["base"], check["default_branch"]
    token = client.token("write")
    results: list[dict] = []

    def attempt(name: str, method: str, path: str, body: dict | None, expect: str):
        status_, _, raw = client._raw(method, path, token, body)
        try:
            message = json.loads(raw).get("message", "") if raw else ""
        except ValueError:
            message = ""
        rejected = status_ in (403, 405, 409, 422) or (method == "DELETE" and status_ not in (204,))
        results.append({"attempt": name, "expected": expect, "http": status_, "github_said": _redact(message, [token])[:140], "result": "REJECTED (pass)" if rejected else "ACCEPTED (FAIL)"})
        say(f"   [{'pass' if rejected else 'FAIL'}] {name}: HTTP {status_} {message[:100]}")

    heads = {b: (client.call("GET", f"/repos/{repo}/branches/{urllib.parse.quote(b, safe='')}", write_enabled=False) or {}).get("commit", {}).get("sha")
             for b in (default, base)}
    if not all(heads.values()):
        raise GitHubError("could not read the branch heads")
    tree = client.call("GET", f"/repos/{repo}/git/commits/{heads[base]}", write_enabled=False)["tree"]["sha"]
    probe_commit = {}
    for branch in (default, base):  # a real commit object on top of each branch, created with the allowed object API; moving the branch to it is the attack
        made = client.call("POST", f"/repos/{repo}/git/commits", {"message": "probe: must never reach this branch", "tree": tree, "parents": [heads[branch]]})
        probe_commit[branch] = made["sha"]
    for branch in (default, base):
        quoted = urllib.parse.quote(branch, safe="/")
        attempt(f"update {branch} directly (ref update, as `git push HEAD:{branch}` does)", "PATCH", f"/repos/{repo}/git/refs/heads/{quoted}",
                {"sha": probe_commit[branch], "force": False}, "rejected by the ruleset: a reviewed PR is required")
        attempt(f"force-push {branch} to another commit", "PATCH", f"/repos/{repo}/git/refs/heads/{quoted}",
                {"sha": heads[base if branch == default else default], "force": True}, "rejected: non-fast-forward is blocked")
        attempt(f"delete {branch}", "DELETE", f"/repos/{repo}/git/refs/heads/{quoted}", None, "rejected: deletion is blocked")
    prs = client.call("GET", f"/repos/{repo}/pulls?state=open&base={urllib.parse.quote(base)}&per_page=20") or []
    mine = [pr for pr in prs if str((pr.get("head") or {}).get("ref", "")).startswith(policy["branch_prefix"])]
    if mine:
        pr = client.call("GET", f"/repos/{repo}/pulls/{mine[0]['number']}") or {}
        if pr.get("mergeable_state") in ("blocked", "behind", "dirty", "unstable"):
            attempt(f"merge PR #{pr['number']} with the App token while it is blocked", "PUT", f"/repos/{repo}/pulls/{pr['number']}/merge",
                    {"merge_method": "squash"}, "rejected: required reviews and checks are not satisfied")
        else:
            say(f"   [skipped] merge probe: PR #{pr.get('number')} reports {pr.get('mergeable_state')!r}; it is not blocked, so a merge attempt would not be safe")
            results.append({"attempt": "merge probe", "expected": "n/a", "http": 0, "github_said": f"skipped: PR is {pr.get('mergeable_state')}", "result": "SKIPPED (not run)"})
    else:
        say("   [skipped] merge probe: no open RemediGenius PR to try it on (publish one first)")
        results.append({"attempt": "merge probe", "expected": "n/a", "http": 0, "github_said": "skipped: no open PR", "result": "SKIPPED (not run)"})
    failed = [r for r in results if r["result"].startswith("ACCEPTED")]
    return {"repo": repo, "ok": not failed, "results": results,
            "note": "FAIL means GitHub accepted an operation that protections should block: restore the repository and fix the rulesets" if failed else
                    "GitHub rejected every attempted operation (skipped probes were not run and are not counted as passed)"}
