"""Host-side rgtriage API on a Unix socket.

Used where the agent runs in a container that must not hold AWS credentials (the Spot
deployment): the Hermes plugin sends `{"args": [...]}` and this process runs the matching
rgtriage command with the host's read-only identity. Only triage subcommands are accepted.
"""
from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ALLOWED = {"digest", "scan", "list", "show", "fix", "decide", "aws", "validate", "doctor", "onboarding", "playbook", "report", "watch"}
MAX_REQUEST = 64 * 1024
MAX_OUTPUT = 400 * 1024
TIMEOUT = {"scan": 900, "watch": 900, "validate": 600}


CHECKPOINT = {"store": None, "homes": {}, "lock": threading.Lock()}
STATE_CHANGING = {"scan", "decide", "watch"}


def checkpoint_all(reason: str) -> None:
    """Copy every configured home to durable storage (skips unchanged homes)."""
    store = CHECKPOINT["store"]
    if store is None:
        return
    from . import durable
    with CHECKPOINT["lock"]:
        for name, home in CHECKPOINT["homes"].items():
            try:
                result = durable.checkpoint(home, name, store)
                if result["status"] == "SAVED":
                    print(f"checkpoint {name}: {result['files']} files ({reason})", flush=True)
                elif result["status"] == "INCOMPLETE":
                    print(f"checkpoint {name} skipped ({reason}): {result['failed']}", flush=True)
                elif result["status"] == "DIVERGED":
                    print(f"checkpoint {name} REFUSED: {result['note']}", flush=True)
            except Exception as exc:  # keep serving; report and retry next cycle
                print(f"checkpoint {name} failed ({reason}): {exc}", flush=True)


def _checkpoint_loop(every: int) -> None:
    while True:
        time.sleep(every)
        checkpoint_all("interval")


def _spot_notice() -> bool:
    try:
        token = urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"}), timeout=2).read().decode()
        urllib.request.urlopen(urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/spot/instance-action",
            headers={"X-aws-ec2-metadata-token": token}), timeout=2)
        return True  # 200 = AWS has scheduled this Spot instance for interruption
    except Exception:
        return False


def _spot_watch() -> None:
    while not _spot_notice():
        time.sleep(5)
    print("Spot interruption notice: saving state now", flush=True)
    checkpoint_all("spot-interruption")


def execute(args: list) -> dict:
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        return {"rc": 2, "stdout": "", "stderr": "request must be {\"args\": [\"subcommand\", ...]}"}
    if args[0] not in ALLOWED:
        return {"rc": 2, "stdout": "", "stderr": f"subcommand {args[0]!r} is not available over the socket"}
    try:
        proc = subprocess.run([sys.executable, "-m", "rgtriage", *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TIMEOUT.get(args[0], 300), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except subprocess.TimeoutExpired:
        return {"rc": 124, "stdout": "", "stderr": f"rgtriage {args[0]} timed out"}
    if proc.returncode == 0 and args[0] in STATE_CHANGING:
        threading.Thread(target=checkpoint_all, args=(args[0],), daemon=True).start()
    return {"rc": proc.returncode, "stdout": proc.stdout[-MAX_OUTPUT:], "stderr": proc.stderr[-4000:]}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        raw = self.rfile.readline(MAX_REQUEST + 1)
        try:
            if len(raw) > MAX_REQUEST:
                raise ValueError("request too large")
            reply = execute(json.loads(raw).get("args"))
        except (ValueError, AttributeError) as exc:
            reply = {"rc": 2, "stdout": "", "stderr": f"bad request: {exc}"}
        self.wfile.write(json.dumps(reply).encode() + b"\n")


if hasattr(socketserver, "UnixStreamServer"):  # Linux/macOS; the desk service never runs on Windows
    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True


def _scan_loop(hours: float) -> None:
    time.sleep(180)  # let the service settle after boot, then scan on a fixed cadence
    while True:
        result = execute(["scan", "--quiet"])
        print(f"scheduled scan: exit {result['rc']}", flush=True)
        time.sleep(hours * 3600)


def serve(path: str, mode: int = 0o660, durable_url: str = "", homes: dict | None = None,
          every: int = 120, spot: bool = False, scan_every_hours: float = 0) -> None:
    if scan_every_hours:
        threading.Thread(target=_scan_loop, args=(scan_every_hours,), daemon=True).start()
    if durable_url:
        from . import durable
        CHECKPOINT["store"], CHECKPOINT["homes"] = durable.backend(durable_url), dict(homes or {})
        threading.Thread(target=_checkpoint_loop, args=(every,), daemon=True).start()
        if spot:
            threading.Thread(target=_spot_watch, daemon=True).start()
    sock = Path(path)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()
    with Server(str(sock), Handler) as server:
        os.chmod(sock, mode)
        print(f"rgtriage API listening on {sock}", flush=True)
        server.serve_forever()


def request(path: str, args: list, timeout: float = 960) -> dict:
    """Client used by the Hermes plugin and the cron watch script."""
    import socket

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(json.dumps({"args": args}).encode() + b"\n")
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return json.loads(b"".join(chunks))
