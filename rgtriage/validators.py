"""Deterministic checks for a proposed change, run on a scratch copy of the repository with no credentials.

What runs, per kind of file:

  Terraform (*.tf)       terraform init (no backend) + validate + fmt -check, tflint (core rules) on the changed files
  CloudFormation         cfn-lint on the changed templates (YAML or JSON that declare AWS resources)
  other YAML / JSON      a parse check

Each result is {check, result, detail} with result pass | fail | warn | skipped. A missing tool is `skipped` and says so: the change
is then **not** validated by that tool, and the PR says it. `fail` blocks publishing; `warn` (formatting, linter advice) does not.
Nothing here plans or applies.

Isolation. These tools execute code from the repository being checked (Terraform providers, linters), so they must never run in a
process that can read the GitHub App key. On the Spot the desk therefore sends the files to a separate validation service
(`rgtriage serve-validate`, its own OS user with no access to the key, the policy or the instance credentials) and gets the results back.
`RGVALIDATE_SOCKET` names that service; when it is set a missing or failing service **fails the validation closed** and never falls back
to running the tools in the caller. Without it (a workstation, where GitHub publishing is disabled) the tools run locally.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path

TIMEOUT = 600
MAX_TREE_BYTES = 64 * 1024 * 1024
MAX_TREE_FILES = 20000
MAX_MODULE_FILE_BYTES = 5 * 1024 * 1024
SECRET_ENV = re.compile(r"^(AWS_|GITHUB_|GH_|RGGITHUB_|RGVALIDATE_|MODEL_API_KEY|.*(TOKEN|SECRET|PASSWORD|PRIVATE_KEY)).*", re.I)
MODULE_SKIP = (".terraform", ".git")
MODULE_SKIP_PATTERNS = (r"\.tfstate", r"\.tfvars(\.json)?$", r"(^|/)\.env", r"\.pem$", r"\.key$", r"(^|/)id_(rsa|ed25519)")


def find_tool(name: str) -> str | None:
    """A tool on PATH, or next to this interpreter (pip puts cfn-lint in the venv's bin, which a systemd service does not have on PATH)."""
    return shutil.which(name) or shutil.which(name, path=str(Path(sys.executable).parent))


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.match(k)}
    env.update(TF_IN_AUTOMATION="1", TF_INPUT="0", CHECKPOINT_DISABLE="1", NO_COLOR="1")
    return env


# ------------------------------------------------------------------ safe paths

def safe_relative(rel: str) -> str:
    """A repository-relative path that cannot leave its folder: no absolute or drive paths, no `..`, no empty or dot segments."""
    text = str(rel).replace("\\", "/")
    if (not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text) or re.search(r"[\x00-\x1f]", text)
            or any(seg in ("", ".", "..") for seg in text.split("/"))):
        raise ValueError(f"{rel!r} is not a safe relative path")
    return text


def safe_join(root: Path, rel: str) -> Path:
    """`root / rel` that is guaranteed to stay inside `root`: resolved path inside it, and no symlink anywhere along the way."""
    root = root.resolve()
    target = root
    for part in safe_relative(rel).split("/"):
        target = target / part
        if target.is_symlink():
            raise ValueError(f"{rel!r} passes through a symbolic link")
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{rel!r} resolves outside the scratch folder")
    return target


def _skip_module_file(rel: str) -> bool:
    return any(part in MODULE_SKIP for part in rel.split("/")) or any(re.search(p, rel, re.I) for p in MODULE_SKIP_PATTERNS)


def snapshot_dir(root: Path) -> dict[str, bytes]:
    """The regular files of a folder as {relative path: bytes}. Symbolic links, state, tfvars, keys and .terraform are left out."""
    files, total = {}, 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file() or _skip_module_file(rel):
            continue
        if path.stat().st_size > MAX_MODULE_FILE_BYTES:
            continue
        total += path.stat().st_size
        if total > MAX_TREE_BYTES or len(files) >= MAX_TREE_FILES:
            raise ValueError("the folder is too large to validate")
        files[rel] = path.read_bytes()
    return files


def write_tree(files: dict[str, bytes], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        target = safe_join(dest, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def pack(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for rel, data in sorted(files.items()):
            info = tarfile.TarInfo(safe_relative(rel))
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def unpack(blob: bytes, dest: Path) -> list[str]:
    """Extract only regular files with safe names; anything else (links, devices, odd names, too many or too large) rejects the archive."""
    names, total = [], 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        members = tar.getmembers()
        if len(members) > MAX_TREE_FILES:
            raise ValueError("too many files")
        for m in members:
            if not m.isfile():
                raise ValueError(f"{m.name!r} is not a regular file")
            total += m.size
            if total > MAX_TREE_BYTES:
                raise ValueError("archive is too large")
            target = safe_join(dest, m.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = tar.extractfile(m)
            target.write_bytes(handle.read() if handle else b"")
            names.append(safe_relative(m.name))
    return names


# ------------------------------------------------------------------ the checks

def _run(cmd: list[str], cwd: Path, env: dict) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {TIMEOUT}s"
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _row(check: str, result: str, detail: str = "") -> dict:
    return {"check": check, "result": result, "detail": detail[-600:]}


def is_cloudformation(path: str, text: str) -> bool:
    return path.lower().endswith((".yaml", ".yml", ".json", ".template")) and ("AWSTemplateFormatVersion" in text or
                                                                              (re.search(r"^Resources\s*:", text, re.M) and "AWS::" in text) or
                                                                              ('"Resources"' in text and "AWS::" in text))


def validate_tree(tree: Path, changed: list[str], which=find_tool) -> list[dict]:
    """Run the checks for the files in `changed` (paths relative to `tree`, which already contains them)."""
    env, results = clean_env(), []
    changed = sorted(safe_relative(p) for p in changed)
    tf = [p for p in changed if p.endswith(".tf")]
    if tf:
        terraform, tflint = which("terraform"), which("tflint")
        for folder in sorted({str(Path(p).parent).replace("\\", "/") for p in tf}):
            module, label = tree / folder, f"terraform {folder or '.'}"
            if not terraform:
                results.append(_row(label, "skipped", "terraform is not installed: this change was NOT validated by Terraform"))
                continue
            rc, out = _run([terraform, "init", "-backend=false", "-input=false", "-no-color"], module, env)
            if rc != 0:
                results.append(_row(f"{label} init", "fail", out))
                continue
            rc, out = _run([terraform, "validate", "-no-color"], module, env)
            results.append(_row(f"{label} validate", "pass" if rc == 0 else "fail", "" if rc == 0 else out))
            files = [Path(p).name for p in tf if str(Path(p).parent).replace("\\", "/") == folder]
            rc, out = _run([terraform, "fmt", "-check", "-diff", "-no-color", *files], module, env)
            results.append(_row(f"{label} fmt", "pass" if rc == 0 else "warn", "" if rc == 0 else "formatting differs from `terraform fmt`\n" + out))
            if not tflint:
                results.append(_row(f"{label} tflint", "skipped", "tflint is not installed"))
            else:
                args = [tflint, "--no-color", "--format=compact"] + [f"--filter={f}" for f in files]
                rc, out = _run(args, module, env)
                results.append(_row(f"{label} tflint", "pass" if rc == 0 else "warn", "" if rc == 0 else out))

    texts = {p: (tree / p).read_bytes().decode("utf-8", "replace") for p in changed if not p.endswith(".tf") and (tree / p).is_file()}
    cfn = [p for p in changed if p in texts and is_cloudformation(p, texts[p])]
    for rel in cfn:
        linter = which("cfn-lint")
        if not linter:
            results.append(_row(f"cfn-lint {rel}", "skipped", "cfn-lint is not installed: this template was NOT linted"))
            continue
        rc, out = _run([linter, "--format", "parseable", rel], tree, env)
        results.append(_row(f"cfn-lint {rel}", "pass" if rc == 0 else ("fail" if rc & 2 else "warn"), "" if rc == 0 else out))

    for rel in changed:
        if rel in cfn or rel.endswith(".tf") or rel not in texts:
            continue
        text = texts[rel]
        if rel.lower().endswith(".json"):
            try:
                json.loads(text)
                results.append(_row(f"json {rel}", "pass"))
            except ValueError as exc:
                results.append(_row(f"json {rel}", "fail", str(exc)))
        elif rel.lower().endswith((".yaml", ".yml")):
            try:
                import yaml
                list(yaml.safe_load_all(text))
                results.append(_row(f"yaml {rel}", "pass"))
            except Exception as exc:
                results.append(_row(f"yaml {rel}", "fail", str(exc)[:300]))
    if not results:
        results.append(_row("validation", "skipped", "no Terraform, CloudFormation, JSON or YAML file in this change: not validated"))
    return results


def validate_overlay(tree: Path, changes: dict[str, bytes], which=find_tool) -> list[dict]:
    """Write the proposed files over `tree` (inside it, never through a link) and check them."""
    results = []
    for rel, data in changes.items():
        try:
            target = safe_join(tree, rel)
        except ValueError as exc:
            results.append(_row(f"path {rel}", "fail", str(exc)))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if results:
        return results
    return validate_tree(tree, list(changes), which)


def terraform_module(tree: Path, which=find_tool) -> tuple[bool, list[str]]:
    """init (no backend) + validate + fmt of a Terraform folder, as the lines `rgtriage validate` prints. Never plans or applies."""
    terraform = which("terraform")
    if not terraform:
        return False, ["terraform is not installed; cannot validate. Ask the operator to run `terraform validate`."]
    env = clean_env()
    if env.get("TF_PLUGIN_CACHE_DIR"):  # reuse downloaded providers across validations
        Path(env["TF_PLUGIN_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    lines, ok = [], True
    for label, cmd in (("init", [terraform, "init", "-backend=false", "-input=false", "-no-color"]),
                       ("validate", [terraform, "validate", "-no-color"]),
                       ("fmt", [terraform, "fmt", "-check", "-diff", "-no-color"])):
        rc, text = _run(cmd, tree, env)
        if label == "init" and rc == 0:
            lines.append("init: ok (no backend, providers downloaded)")
            continue
        status = "ok" if rc == 0 else ("formatting differences" if label == "fmt" else "FAILED")
        ok = ok and (rc == 0 or label == "fmt")
        lines.append(f"{label}: {status}")
        if text and (rc != 0 or label == "validate"):
            lines.append(text[-3000:])
        if label == "init" and rc != 0:
            break
    lines.append("Result: " + ("VALID — syntax and provider schema check passed (this is not a plan; review `terraform plan` before applying)."
                              if ok else "NOT VALID — fix the errors above and validate again."))
    return ok, lines


def available(which=find_tool) -> dict:
    """Which deterministic tools this desk can run (reported by `rgtriage github status` and doctor)."""
    return {name: bool(which(name)) for name in ("terraform", "tflint", "cfn-lint")}


# ------------------------------------------------------------------ isolation: the validation service

def socket_path() -> str:
    return os.environ.get("RGVALIDATE_SOCKET", "")


def isolated() -> bool:
    return bool(socket_path())


def _call_service(path: str, header: dict, files: dict[str, bytes], timeout: float = TIMEOUT * 3) -> dict:
    blob = pack(files)
    header = dict(header, size=len(blob))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(path)
            conn.sendall(json.dumps(header).encode() + b"\n" + blob)
            conn.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except (OSError, ValueError, AttributeError) as exc:  # fail closed (also where Unix sockets do not exist): never run the tools in the caller
        return {"error": f"the validation service is unavailable ({type(exc).__name__}); nothing was validated"}


def check_tree(files: dict[str, bytes], changed: list[str]) -> list[dict]:
    """Checks for `changed` inside the full candidate tree `files`: in the validation service when configured, else locally."""
    if isolated():
        reply = _call_service(socket_path(), {"kind": "tree", "changed": changed}, files)
        if "results" in reply:
            return reply["results"]
        return [_row("validation service", "fail", reply.get("error", "no answer"))]
    with tempfile.TemporaryDirectory(prefix="rg-validate-") as scratch:
        write_tree(files, Path(scratch) / "tree")
        return validate_tree(Path(scratch) / "tree", changed)


def check_module(files: dict[str, bytes]) -> tuple[bool, list[str]]:
    if isolated():
        reply = _call_service(socket_path(), {"kind": "module"}, files)
        if "lines" in reply:
            return bool(reply.get("ok")), reply["lines"]
        return False, [f"validation did not run: {reply.get('error', 'no answer')}"]
    with tempfile.TemporaryDirectory(prefix="rg-validate-") as scratch:
        write_tree(files, Path(scratch) / "module")
        return terraform_module(Path(scratch) / "module")


def handle_request(header: dict, blob: bytes, scratch_root: str | None = None) -> dict:
    """What the validation service does with one request. Runs with no access to credentials, in a throwaway folder."""
    kind = header.get("kind")
    if kind == "ping":
        return {"ok": True, "tools": available()}
    if kind not in ("tree", "module"):
        return {"error": "unknown request"}
    try:
        with tempfile.TemporaryDirectory(prefix="rgv-", dir=scratch_root) as scratch:
            tree = Path(scratch) / "tree"
            tree.mkdir()
            unpack(blob, tree)
            if kind == "tree":
                changed = header.get("changed")
                if not isinstance(changed, list) or not all(isinstance(c, str) for c in changed):
                    return {"error": "changed must be a list of paths"}
                return {"results": validate_tree(tree, changed)}
            ok, lines = terraform_module(tree)
            return {"ok": ok, "lines": lines}
    except (ValueError, tarfile.TarError, OSError) as exc:
        return {"error": f"rejected: {exc}"}


if hasattr(socketserver, "UnixStreamServer"):
    class _Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(60)
            try:
                header = json.loads(self.rfile.readline(65536))
                size = int(header.get("size", -1))
                if not 0 <= size <= MAX_TREE_BYTES:
                    raise ValueError("bad size")
                blob = self.rfile.read(size)
                if len(blob) != size:
                    raise ValueError("short upload")
            except (ValueError, OSError, TypeError):
                reply = {"error": "bad request"}
            else:
                self.request.settimeout(None)
                with self.server.slots:
                    reply = handle_request(header, blob, self.server.scratch)
            try:
                self.wfile.write(json.dumps(reply).encode() + b"\n")
            except OSError:
                pass

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True


def serve(path: str, scratch: str | None = None, workers: int = 2, mode: int = 0o660, group: int | None = None) -> None:
    """Run the validation service on a Unix socket (its own OS user; see deploy/aws-single/host.py)."""
    sock = Path(path)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()
    with Server(str(sock), _Handler) as server:
        server.slots = threading.Semaphore(workers)
        server.scratch = scratch
        os.chmod(sock, mode)
        if group is not None:
            os.chown(sock, -1, group)
        print(f"rgtriage validation service listening on {sock}", flush=True)
        server.serve_forever()


def ping() -> dict:
    """Is the validation service reachable (and which tools does it have)? {} when it is not configured, {'error': ...} when it is down."""
    if not isolated():
        return {}
    return _call_service(socket_path(), {"kind": "ping"}, {}, timeout=10)
