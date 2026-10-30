"""Dashboard tab backend: serve the board page and let a person refresh it.

Runs inside the dashboard process, which holds no AWS credentials. The page is the file `rgtriage board --html`
writes on every scan; a refresh is a `scan --quiet` request to the desk over its Unix socket, so the numbers come
from a real collection run, not from re-rendering the old snapshot.
"""
from __future__ import annotations

import json
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()
HERE = Path(__file__).resolve().parent
DEFAULTS = {"socket": "/run/rgtriage/rgtriage.sock", "board": "/data/rgtriage/board.html",
            "status": "/data/rgtriage/status.json"}
REFRESH = threading.Lock()

EMPTY = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>RemediGenius dashboard</title>
<style>body{margin:0;background:#faf9f6;color:#17171a;font:15px/1.55 system-ui,sans-serif;display:grid;
place-items:center;height:100vh}main{max-width:52ch;padding:24px}h1{font-size:20px;margin:0 0 8px}
p{color:#6b6b66}code{font:12px ui-monospace,monospace;background:#fff;border:1px solid #e4e2db;padding:1px 5px;border-radius:5px}</style>
</head><body><main><h1>No board yet</h1><p>The desk has not written a snapshot on this installation. Run
<code>rgtriage scan</code>, or press Refresh once the desk is reachable; the scan writes <code>board.html</code> and
this page appears.</p></main></body></html>"""


def _settings() -> dict:
    try:
        return json.loads((HERE.parent / "local.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _path(name: str) -> Path:
    return Path(_settings().get(name) or DEFAULTS[name])


def _desk(args: list[str], timeout: int = 900) -> str:
    path = _settings().get("socket") or DEFAULTS["socket"]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout + 30)
            conn.connect(path)
            conn.sendall(json.dumps({"args": args}).encode() + b"\n")
            chunks = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        reply = json.loads(b"".join(chunks))
    except (OSError, ValueError) as exc:
        raise HTTPException(503, f"the desk service is not reachable: {exc}") from None
    rc, out, err = reply.get("rc", 1), reply.get("stdout") or "", reply.get("stderr") or ""
    if rc != 0:
        message = (err or out).strip().splitlines()
        raise HTTPException(400, message[-1] if message else f"rgtriage {args[0]} failed")
    return out


def _status() -> dict:
    try:
        data = json.loads(_path("status").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"scanned_at": None, "age": "no scan yet", "summary": ""}
    scanned = data.get("scanned_at")
    age = "unknown age"
    try:
        when = datetime.fromisoformat(str(scanned).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        when = None
    if when:
        minutes = int((datetime.now(timezone.utc) - when).total_seconds() // 60)
        age = "just now" if minutes < 5 else f"{minutes}m ago" if minutes < 60 else f"{minutes // 60}h {minutes % 60}m ago"
    return {"scanned_at": scanned, "age": age, "summary": data.get("summary", "")}


@router.get("/status")
def status() -> dict:
    return _status()


@router.post("/refresh")
def refresh() -> dict:
    """Run every configured source, then let the page load the snapshot the scan wrote."""
    if not REFRESH.acquire(blocking=False):
        raise HTTPException(409, "a scan is already running")
    try:
        before = _status().get("scanned_at")
        _desk(["scan", "--quiet"], timeout=900)
        after = _status()
        if not after.get("scanned_at") or after.get("scanned_at") == before:
            raise HTTPException(500, "the scan finished but no new snapshot was written")
        return {"ok": True, **after}
    finally:
        REFRESH.release()


@router.get("/page", response_class=HTMLResponse)
def page() -> HTMLResponse:
    try:
        text = _path("board").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return HTMLResponse(EMPTY, status_code=404, headers={"Cache-Control": "no-store"})
    return HTMLResponse(text, headers={"Cache-Control": "no-store"})