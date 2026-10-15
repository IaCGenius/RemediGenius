"""Static checks on a function bundle. One source of truth: the gate runs them in Lambda, `kiosk test`
runs the same file on the agent's side (downloaded inside the runtime layer). Standard library only.

Every problem carries a code, the file, a message and a `fix` hint, so an agent can repair its
bundle without guessing.
"""
import ast
import hashlib
import io
import json
import re
import zipfile

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
NAME = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$")
ALLOWED_EXT = {".py", ".json", ".md", ".txt"}
REQUIRED = ("name", "version", "description", "kit", "class", "compute", "memory_mb", "timeout_s",
            "concurrency", "canary_input")
FORBIDDEN_IMPORTS = {"subprocess", "socket", "ctypes", "multiprocessing", "pty", "telnetlib", "ftplib",
                     "smtplib", "socketserver", "http.server", "xmlrpc.server", "asyncio.subprocess"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint"}
FORBIDDEN_OS = re.compile(r"^(system|popen|exec\w*|spawn\w*|fork\w*|kill\w*|putenv)$")


def problem(code, message, fix, file=""):
    return {"code": code, "file": file, "message": message, "fix": fix}


# ------------------------------------------------------------------ zip
def read_zip(data, max_bytes):
    """bytes -> {path: bytes}. Refuses unsafe paths, links and oversized bundles."""
    if len(data) > max_bytes:
        raise ValueError(f"bundle is {len(data)} bytes, limit {max_bytes}")
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        total = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not PATH.match(name) or ".." in name.split("/"):
                raise ValueError(f"unsafe path in bundle: {name!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"symlink in bundle: {name!r}")
            total += info.file_size
            if total > max_bytes * 4:
                raise ValueError("bundle expands beyond 4x its limit")
            files[name] = z.read(info)
    return files


def make_zip(files):
    """{path: bytes} -> deterministic zip bytes (sorted, fixed timestamps), same hash every time."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[name])
    return buf.getvalue()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ python scan
def scan_python(path, source):
    """Forbidden imports and calls. Returns (problems, number of test functions)."""
    out, tests = [], 0
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        return [problem("SYNTAX_ERROR", f"line {e.lineno}: {e.msg}", "fix the Python syntax", path)], 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
        else:
            mods = []
        for m in mods:
            if m in FORBIDDEN_IMPORTS or m.split(".")[0] in FORBIDDEN_IMPORTS:
                out.append(problem("FORBIDDEN_IMPORT", f"line {node.lineno}: import {m}",
                                   "remove it; functions may not start processes or open raw network sockets", path))
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in FORBIDDEN_CALLS:
                out.append(problem("FORBIDDEN_CALL", f"line {node.lineno}: {f.id}()",
                                   "remove dynamic code execution", path))
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "os"
                    and FORBIDDEN_OS.match(f.attr)):
                out.append(problem("FORBIDDEN_CALL", f"line {node.lineno}: os.{f.attr}()",
                                   "remove process control calls", path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            tests += 1
    return out, tests


def has_handle(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == "handle" and len(n.args.args) == 2 for n in tree.body)


# ------------------------------------------------------------------ the bundle
def check_bundle(files, limits, kits, classes, previous_tests=0, compute_enabled=("lambda",)):
    """Returns (manifest or None, report, problems). No problems = the bundle may go to the sandbox."""
    probs, report = [], {"files": sorted(files), "test_count": 0}
    raw = files.get("manifest.json")
    if raw is None:
        return None, report, [problem("MANIFEST_MISSING", "no manifest.json at the bundle root",
                                      "start from a kit: kiosk new <name> --kit hello")]
    try:
        m = json.loads(raw)
        assert isinstance(m, dict)
    except (ValueError, AssertionError):
        return None, report, [problem("MANIFEST_INVALID_JSON", "manifest.json is not a JSON object",
                                      "fix the JSON", "manifest.json")]
    for k in REQUIRED:
        if k not in m:
            probs.append(problem("MANIFEST_FIELD_MISSING", f"missing field {k}", f"add {k} (see the kit's manifest)",
                                 "manifest.json"))
    if probs:
        return m, report, probs

    def bad(code, msg, fix):
        probs.append(problem(code, msg, fix, "manifest.json"))

    if not NAME.match(str(m["name"])):
        bad("NAME_INVALID", f"name {m['name']!r}", "3-40 chars: lowercase letters, digits, dashes; start with a letter")
    if not SEMVER.match(str(m["version"])):
        bad("VERSION_INVALID", f"version {m['version']!r}", "use MAJOR.MINOR.PATCH, e.g. 0.1.0")
    if not str(m["description"]).strip() or len(str(m["description"])) > 300:
        bad("DESCRIPTION_INVALID", "description empty or over 300 chars", "one sentence: what it does")
    if m["kit"] not in kits:
        bad("KIT_UNKNOWN", f"kit {m['kit']!r}", f"one of {sorted(kits)}")
    if m["class"] not in classes:
        bad("CLASS_NOT_ALLOWED", f"class {m['class']!r} is not allowed for this agent",
            f"one of {sorted(classes)}; a new class needs the owner")
    if m["compute"] not in compute_enabled:
        bad("COMPUTE_NOT_ENABLED", f"compute {m['compute']!r}", f"this kiosk runs {list(compute_enabled)}")
    for field, lim, lo in (("memory_mb", "memory_mb", 128), ("timeout_s", "timeout_s", 3),
                           ("concurrency", "concurrency", 1)):
        v = m[field]
        if not isinstance(v, int) or v < lo or v > limits[lim]:
            bad("LIMIT_EXCEEDED", f"{field}={v!r}", f"an integer from {lo} to {limits[lim]}")
    if not isinstance(m["canary_input"], dict):
        bad("CANARY_INPUT_INVALID", "canary_input must be a JSON object",
            "give a small real input the canary run can use")
    env = m.get("env", {})
    if not isinstance(env, dict) or len(env) > 10:
        bad("ENV_INVALID", "env must be an object with at most 10 entries", "fix env")
    else:
        for k, v in env.items():
            if not ENV_KEY.match(k) or k.startswith(("AWS_", "KIOSK_", "LAMBDA_", "_")):
                bad("ENV_INVALID", f"env key {k!r}", "UPPER_CASE, not starting with AWS_, KIOSK_, LAMBDA_")
            if not isinstance(v, str) or len(v) > 256:
                bad("ENV_INVALID", f"env {k}: value must be a string up to 256 chars", "fix the value")
            elif re.search(r"(?i)(AKIA|ASIA)[A-Z0-9]{16}|PRIVATE KEY", v):
                bad("SECRET_IN_ENV", f"env {k} looks like a secret", "never put secrets in a function")

    for path, data in files.items():
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        if ext not in ALLOWED_EXT:
            probs.append(problem("FILE_TYPE_NOT_ALLOWED", f"{path}", f"only {sorted(ALLOWED_EXT)}", path))
            continue
        if ext == ".py":
            try:
                src = data.decode("utf-8")
            except UnicodeDecodeError:
                probs.append(problem("ENCODING", "not UTF-8", "save as UTF-8", path))
                continue
            p, t = scan_python(path, src)
            probs += p
            if path.startswith("tests/"):
                report["test_count"] += t
    if "handler.py" not in files:
        probs.append(problem("HANDLER_MISSING", "no handler.py at the bundle root", "add handler.py with handle(unit, ctx)"))
    elif not has_handle(files["handler.py"].decode("utf-8", "replace")):
        probs.append(problem("HANDLE_FUNCTION_MISSING", "handler.py has no top-level def handle(unit, ctx)",
                             "define handle(unit, ctx) returning {'status': ..., 'summary': {...}}", "handler.py"))
    if not any(p.startswith("tests/test_") and p.endswith(".py") for p in files) or report["test_count"] == 0:
        probs.append(problem("TESTS_MISSING", "no test functions in tests/test_*.py",
                             "add tests that call kiosk_runtime.testing.run(handler.handle, unit)"))
    elif report["test_count"] < previous_tests:
        probs.append(problem("TESTS_REDUCED", f"{report['test_count']} tests, the last passing version had {previous_tests}",
                             "keep or add tests; removing tests needs the owner"))
    return m, report, probs
