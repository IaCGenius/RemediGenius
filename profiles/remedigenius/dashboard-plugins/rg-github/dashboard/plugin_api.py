"""GitHub tab backend for RemediGenius Community Edition (RemediGenius-CE).

Runs inside the Hermes dashboard process, which holds no GitHub key, token or AWS credential. Every step (connect, install check, repository and
branch choice, configuration, verification, refresh, disconnect) is a request to the desk over its Unix socket, which does the work next to the
key. The setup operations are accepted by the desk only with the operator token, a file the host writes at boot that this process reads; the
agent's own tool never sends it and has no way to call these routes (they are behind the dashboard login, and the agent has no HTTP tool).
"""
from __future__ import annotations

import json
import re
import socket
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter()
HERE = Path(__file__).resolve().parent
CALLBACK_PATH = "/api/plugins/rg-github/callback"
PAGE_PATH = "/github"
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,100}$")
ORG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
REVIEWER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}(/[A-Za-z0-9][A-Za-z0-9_.-]{0,99})?$")
SAFE_ERROR = re.compile(r"(-----BEGIN[^-]*-----|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})")


def _settings() -> dict:
    try:
        return json.loads((HERE.parent / "local.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _token() -> str:
    path = _settings().get("operator_token_file")
    try:
        return Path(path).read_text(encoding="utf-8").strip() if path else ""
    except OSError:
        return ""


def _clean(message: str) -> str:
    """One readable line, with the desk's wrapper text removed and anything that looks like a secret redacted."""
    line = (message or "").strip().splitlines()[-1] if (message or "").strip() else "the desk did not answer"
    line = line.replace("DENIED (nothing was sent to GitHub): ", "")
    return SAFE_ERROR.sub("[redacted]", line)[:400]


def _desk(args: list[str], timeout: int = 120) -> str:
    settings = _settings()
    if not settings.get("socket"):
        raise HTTPException(503, "GitHub setup is available on the Spot deployment only (it needs the desk service)")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(settings["socket"])
            conn.sendall(json.dumps({"args": args, "operator": _token()}).encode() + b"\n")
            chunks = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        reply = json.loads(b"".join(chunks))
    except (OSError, ValueError, AttributeError) as exc:
        raise HTTPException(503, f"the desk service is not reachable: {type(exc).__name__}") from None
    if reply.get("rc") != 0:
        raise HTTPException(400, _clean(reply.get("stderr") or reply.get("stdout") or ""))
    return reply.get("stdout") or ""


def _desk_json(args: list[str], timeout: int = 120):
    out = _desk(args, timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise HTTPException(500, "unexpected answer from the desk") from None


def _origin(request: Request) -> str:
    """Where the browser reached this console (the SSM tunnel address): GitHub is told to come back here. The desk accepts only loopback
    addresses (or origins the operator listed), so a forged Host header cannot send GitHub's code anywhere else."""
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def _check(pattern: re.Pattern, value: str, what: str) -> str:
    value = (value or "").strip()
    if not pattern.match(value):
        raise HTTPException(400, f"{what} is not valid")
    return value


# ------------------------------------------------------------------ routes

@router.get("/status")
def status():
    """The four states, the connected identity, repository, branches, reviewers and each protection check."""
    return _desk_json(["github", "status", "--json"])


class Begin(BaseModel):
    org: str = ""
    reconnect: bool = False


@router.post("/begin")
def begin(body: Begin, request: Request):
    """Step 1: what the browser must post to GitHub to create the App (or, if the App already exists, where to install it)."""
    origin = _origin(request)
    args = ["github", "web-begin", "--redirect", origin + CALLBACK_PATH, "--setup-url", origin + PAGE_PATH]
    if body.org.strip():
        args += ["--org", _check(ORG, body.org, "the organization name")]
    if body.reconnect:
        args.append("--reconnect")
    return _desk_json(args)


@router.get("/callback")
def callback(code: str = "", state: str = ""):
    """Step 2: GitHub sends the browser here after "Create GitHub App". The desk checks the state it issued and finishes; we go back to the page."""
    try:
        _desk_json(["github", "web-finish", "--code", code[:200], "--state", state[:200]])
        return RedirectResponse(PAGE_PATH + "?step=install", status_code=303)
    except HTTPException as exc:
        return RedirectResponse(PAGE_PATH + "?error=" + urllib.parse.quote(_clean(str(exc.detail))[:300]), status_code=303)


@router.get("/install")
def install():
    """Has the App been installed yet? The page asks every few seconds while the person installs it on GitHub."""
    return _desk_json(["github", "web-install", "--json"])


@router.get("/repos")
def repos():
    return _desk_json(["github", "web-repos", "--json"])


@router.get("/branches")
def branches(repo: str = ""):
    return _desk_json(["github", "web-branches", "--repo", _check(REPO, repo, "the repository")])


class Configure(BaseModel):
    repo: str
    base: str
    reviewers: list[str]


@router.post("/configure")
def configure(body: Configure):
    """Save the repository, development branch and reviewers, then check the repository and its protections (writes are enabled only if they pass)."""
    if not 1 <= len(body.reviewers) <= 10:
        raise HTTPException(400, "give between one and ten human reviewers")
    args = ["github", "configure", "--json", "--repo", _check(REPO, body.repo, "the repository"), "--base", _check(BRANCH, body.base, "the development branch")]
    for name in body.reviewers:
        args += ["--reviewer", _check(REVIEWER, name, f"reviewer {name!r}")]
    return _desk_json(args, timeout=240)


@router.post("/verify")
def verify():
    return _desk_json(["github", "verify", "--json"], timeout=240)


@router.post("/refresh")
def refresh():
    return _desk_json(["github", "refresh", "--json"], timeout=240)


class Disconnect(BaseModel):
    keep_installation: bool = False


@router.post("/disconnect")
def disconnect(body: Disconnect):
    args = ["github", "disconnect", "--json"] + (["--keep-installation"] if body.keep_installation else [])
    return _desk_json(args)
