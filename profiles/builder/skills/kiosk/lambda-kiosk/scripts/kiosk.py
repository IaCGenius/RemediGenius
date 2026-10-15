#!/usr/bin/env python3
"""kiosk: build, test, deploy, promote, run and reuse Lambda functions through a lambda-kiosk.

    kiosk doctor [--e2e]            rights, config, layers; --e2e builds and runs a hello function end to end
    kiosk setup                     download the kiosk's pinned layers (runtime + test) for local tests
    kiosk search [WORDS]            find existing functions (reuse before you build)
    kiosk show NAME                 one function: versions, aliases, gate results, canary, runs
    kiosk new NAME --kit KIT        scaffold from a kit (hello, processor, python-blank) into /opt/data/work/kiosk/NAME
    kiosk sdk SERVICE [OPERATION]   pinned AWS SDK docs, offline: operations, input/output shapes, paginators
    kiosk test DIR                  the gate's static checks + the function's tests, locally, with the pinned layers
    kiosk submit DIR                bundle -> gate (checks, sandbox tests, signing, deploy as alias dev); prints verdict
    kiosk promote NAME VERSION      canary run, then live (policy auto); --stage live|rollback|retire
    kiosk run NAME --items FILE|--item JSON [--alias live] [--concurrency N]
    kiosk logs NAME [--minutes 60]  the function's CloudWatch logs (your own functions only)
    kiosk outputs NAME [RUN_ID]     list or print a run's outputs
    kiosk receipt RUN_ID            a run's receipt

Credentials: /opt/data/kiosk/<agent>/credentials, refreshed by the host every 40 minutes. Never print them.
Exit code 0 = PASS / SUCCEEDED, 1 = refused or failed (read the reasons and the fix hints), 2 = usage or platform.
"""
import argparse
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
KITS = SKILL / "kits"
WORK = Path(os.environ.get("KIOSK_WORK", "/opt/data/work/kiosk"))
BASE = Path(os.environ.get("KIOSK_HOME", "/opt/data/kiosk"))


def die(msg, code=2):
    print(f"kiosk: {msg}", file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------------ identity, config, clients
def agent_dir():
    if os.environ.get("KIOSK_AGENT"):
        return BASE / os.environ["KIOSK_AGENT"]
    dirs = [d for d in BASE.glob("*") if (d / "kiosk.env").exists()] if BASE.exists() else []
    if len(dirs) != 1:
        die(f"no kiosk credentials under {BASE} (the host writes them; is this profile registered in the kiosk?)")
    return dirs[0]


def env():
    d = agent_dir()
    vals = dict(line.strip().split("=", 1) for line in (d / "kiosk.env").read_text().splitlines() if "=" in line)
    return d, vals


_session = None


def session():
    global _session
    if _session is None:
        d, vals = env()
        os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(d / "credentials")
        os.environ["AWS_CONFIG_FILE"] = os.devnull
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
            os.environ.pop(k, None)
        import boto3
        _session = boto3.Session(profile_name="kiosk", region_name=vals["AWS_REGION"])
    return _session


def client(name):
    from botocore.config import Config
    return session().client(name, config=Config(retries={"mode": "adaptive", "total_max_attempts": 5}))


_cfg = None


def cfg():
    global _cfg
    if _cfg is None:
        _, vals = env()
        _cfg = json.loads(client("ssm").get_parameter(Name=f"/kiosk/{vals['KIOSK_NAME']}/config")["Parameter"]["Value"])
        _cfg["_agent"] = vals["KIOSK_AGENT"]
    return _cfg


def agent():
    return cfg()["_agent"]


# ------------------------------------------------------------------ layers (pinned runtime + pytest), downloaded once per version
def layer_dir(kind):
    arn = cfg()["layers"][kind]
    d = BASE / ".layers" / re.sub(r"[^A-Za-z0-9]+", "_", arn.split(":layer:")[1])
    if not (d / "python").exists():
        url = client("lambda").get_layer_version_by_arn(Arn=arn)["Content"]["Location"]
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        tmp = d.with_suffix(".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        shutil.rmtree(d, ignore_errors=True)
        tmp.rename(d)
    return d / "python"


def rules():
    path = layer_dir("runtime") / "kiosk_runtime" / "rules.py"
    spec = importlib.util.spec_from_file_location("kiosk_rules", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_dir(d):
    d = Path(d)
    skip = {"__pycache__", ".pytest_cache", "out", ".junit.xml"}
    files = {}
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d)
        if p.is_file() and not (set(rel.parts) & skip) and not rel.name.endswith(".pyc") and not rel.name.startswith("."):
            files[rel.as_posix()] = p.read_bytes()
    return files


# ------------------------------------------------------------------ state machines
def start(machine, payload, name_hint):
    arn = cfg()["state_machines"][machine]
    ex_name = re.sub(r"[^A-Za-z0-9_-]", "-", f"{agent()}-{name_hint}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}")[:80]
    ex = client("stepfunctions").start_execution(stateMachineArn=arn, name=ex_name, input=json.dumps(payload))
    return wait(ex["executionArn"])


def wait(execution_arn, timeout_s=900):
    sfn, t0 = client("stepfunctions"), time.time()
    while True:
        d = sfn.describe_execution(executionArn=execution_arn)
        if d["status"] != "RUNNING":
            break
        if time.time() - t0 > timeout_s:
            die(f"still running after {timeout_s}s: {execution_arn}")
        time.sleep(4)
    if d["status"] != "SUCCEEDED":
        print(json.dumps({"verdict": "PLATFORM_ERROR", "status": d["status"], "error": d.get("error"),
                          "cause": (d.get("cause") or "")[:1500], "execution": execution_arn}, indent=1))
        print("kiosk: the kiosk itself failed (not your code). The admin was alerted. Do not retry in a loop.",
              file=sys.stderr)
        sys.exit(2)
    return json.loads(d.get("output") or "{}")


def show_verdict(out):
    print(json.dumps(out, indent=1, default=str))
    ok = out.get("verdict") == "PASS" or out.get("status") == "SUCCEEDED"
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ commands
def cmd_setup(a):
    for k in ("runtime", "test"):
        print(f"{k} layer: {layer_dir(k)}")


def cmd_search(a):
    s3, words = client("s3"), [w.lower() for w in a.words]
    rows, token = [], None
    while True:
        kw = {"Bucket": cfg()["bucket"], "Prefix": "registry/"}
        if token:
            kw["ContinuationToken"] = token
        page = s3.list_objects_v2(**kw)
        for o in page.get("Contents", []):
            r = json.loads(s3.get_object(Bucket=cfg()["bucket"], Key=o["Key"])["Body"].read())
            text = json.dumps([r.get("name"), r.get("description"), r.get("tags"), r.get("kit")]).lower()
            if all(w in text for w in words):
                rows.append(r)
        if not page.get("IsTruncated"):
            break
        token = page["NextContinuationToken"]
    if not rows:
        print("no matching functions: build one (kiosk new NAME --kit KIT)")
    for r in rows:
        print(f"{r['agent']}/{r['name']}  state={r.get('state')}  live={r['aliases'].get('live')}  "
              f"dev={r['aliases'].get('dev')}  kit={r.get('kit')}  runs={r['runs'].get('count')}  - {r.get('description', '')}")


def registry(name, who=None):
    try:
        return json.loads(client("s3").get_object(Bucket=cfg()["bucket"], Key=f"registry/{who or agent()}/{name}.json")["Body"].read())
    except client("s3").exceptions.NoSuchKey:
        die(f"{name} is not in the registry (kiosk search)", 1)


def cmd_show(a):
    r = registry(a.name, a.agent)
    for v in r.get("versions", {}).values():
        v.pop("manifest", None) if not a.full else None
    print(json.dumps(r, indent=1, default=str))


def cmd_new(a):
    src = KITS / a.kit
    if not src.exists():
        die(f"kit {a.kit!r}: one of {sorted(p.name for p in KITS.iterdir())}")
    if not re.match(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$", a.name):
        die("name: 3-40 chars, lowercase letters, digits, dashes, start with a letter")
    dest = Path(a.dir) if a.dir else WORK / a.name
    if dest.exists() and any(dest.iterdir()):
        die(f"{dest} exists and is not empty")
    shutil.copytree(src, dest, dirs_exist_ok=True)
    for p in dest.rglob("*"):
        if p.is_file():
            p.write_text(p.read_text().replace("{{name}}", a.name))
    print(f"created {dest} from kit {a.kit}. Next: edit handler.py and tests/, then kiosk test {dest}")


def cmd_sdk(a):
    from botocore.loaders import Loader
    data = layer_dir("runtime") / "botocore" / "data"
    loader = Loader(extra_search_paths=[str(data)], include_default_search_paths=False)
    try:
        model = loader.load_service_model(a.service, "service-2")
    except Exception:
        die(f"unknown service {a.service!r}; examples: s3, ec2, iam, lambda, dynamodb")
    try:
        pag = loader.load_service_model(a.service, "paginators-1").get("pagination", {})
    except Exception:
        pag = {}
    strip = lambda t: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t or "")).strip()
    ops = model["operations"]
    if not a.operation:
        print(f"{a.service} (botocore {loader_version(data)}): {len(ops)} operations; * = paginated")
        for n in sorted(ops):
            if not a.grep or a.grep.lower() in n.lower():
                print(f"  {'*' if n in pag else ' '} {n}")
        return
    op = ops.get(a.operation) or die(f"{a.operation!r} not in {a.service}")
    shapes = model["shapes"]

    def tree(name, depth=0, seen=()):
        s = shapes[name]
        pad = "  " * (depth + 1)
        if s["type"] == "structure":
            req = set(s.get("required", []))
            for m, ref in s.get("members", {}).items():
                print(f"{pad}{m}{' (required)' if m in req else ''}: {shapes[ref['shape']]['type']} [{ref['shape']}]")
                if depth < a.depth and ref["shape"] not in seen:
                    tree(ref["shape"], depth + 1, seen + (ref["shape"],))
        elif s["type"] == "list" and depth < a.depth:
            tree(s["member"]["shape"], depth, seen)
    print(f"{a.service}.{a.operation}  ->  boto3: client('{a.service}').{snake(a.operation)}(...)")
    print(f"doc: {strip(op.get('documentation'))[:900]}")
    if a.operation in pag:
        print(f"paginator: {json.dumps(pag[a.operation])}")
    for side in ("input", "output"):
        if side in op:
            print(f"{side}: {op[side]['shape']}")
            tree(op[side]["shape"])
    errs = [e["shape"] for e in op.get("errors", [])]
    if errs:
        print(f"errors: {', '.join(errs)}")


def loader_version(data):
    m = list(data.parent.parent.glob("botocore-*.dist-info"))
    return m[0].name.split("-")[1] if m else "?"


def snake(name):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)).lower()


def local_checks(d):
    r, c = rules(), cfg()
    files = read_dir(d)
    a = c["agents"][agent()]
    manifest, report, problems = r.check_bundle(files, c["limits"], c["kits"], a["classes"], 0, c["compute"])
    return files, manifest, report, problems


def cmd_test(a):
    d = Path(a.dir)
    files, manifest, report, problems = local_checks(d)
    if problems:
        print(json.dumps({"verdict": "FAIL", "stage": "static checks", "problems": problems}, indent=1))
        sys.exit(1)
    pyp = os.pathsep.join([str(d), str(layer_dir("runtime")), str(layer_dir("test"))])
    e = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    e.update(PYTHONPATH=pyp, AWS_ACCESS_KEY_ID="testing", AWS_SECRET_ACCESS_KEY="testing",
             AWS_SESSION_TOKEN="testing", AWS_DEFAULT_REGION="us-east-1", AWS_ENDPOINT_URL="http://127.0.0.1:9",
             AWS_MAX_ATTEMPTS="1", AWS_SHARED_CREDENTIALS_FILE=os.devnull, AWS_CONFIG_FILE=os.devnull,
             KIOSK_AGENT=agent(), KIOSK_FUNCTION=manifest["name"], KIOSK_VERSION=manifest["version"],
             KIOSK_BUCKET="local", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=d, env=e,
                       capture_output=True, text=True, timeout=300)
    tail = (p.stdout + p.stderr)[-3000:]
    verdict = "PASS" if p.returncode == 0 else "FAIL"
    print(json.dumps({"verdict": verdict, "stage": "tests", "tests": report["test_count"], "name": manifest["name"],
                      "version": manifest["version"], "output": tail}, indent=1))
    sys.exit(0 if verdict == "PASS" else 1)


def cmd_submit(a):
    d = Path(a.dir)
    files, manifest, report, problems = local_checks(d)
    if problems:
        print(json.dumps({"verdict": "FAIL", "stage": "local static checks (not submitted)", "problems": problems}, indent=1))
        sys.exit(1)
    data = rules().make_zip(files)
    key = f"incoming/{agent()}/{manifest['name']}/{manifest['version']}/bundle.zip"
    client("s3").put_object(Bucket=cfg()["bucket"], Key=key, Body=data)
    print(f"submitted {manifest['name']} {manifest['version']} ({len(data)} bytes); gate running...", file=sys.stderr)
    show_verdict(start("gate", {"bundle_key": key}, f"{manifest['name']}-{manifest['version']}"))


def cmd_promote(a):
    show_verdict(start("promote", {"agent": agent(), "name": a.name, "version": a.version or "", "stage": a.stage,
                                   "reason": a.reason or ""}, f"{a.name}-{a.stage}"))


def cmd_run(a):
    if a.items:
        items = json.loads(Path(a.items).read_text())
    elif a.item is not None:
        items = [json.loads(a.item)]
    else:
        die("give --items FILE (JSON list) or --item JSON")
    out = start("run", {"agent": agent(), "name": a.name, "alias": a.alias, "items": items,
                        "concurrency": a.concurrency}, f"{a.name}-run")
    print(json.dumps(out, indent=1, default=str))
    sys.exit(0 if out.get("status") == "SUCCEEDED" else 1)


def cmd_logs(a):
    logs = client("logs")
    group = f"/aws/lambda/{cfg()['function_prefix']}{agent()}-{a.name}"
    since = int((time.time() - a.minutes * 60) * 1000)
    kw = {"logGroupName": group, "startTime": since, "limit": 200}
    if a.filter:
        kw["filterPattern"] = a.filter
    try:
        for e in logs.filter_log_events(**kw).get("events", []):
            print(f"{datetime.fromtimestamp(e['timestamp'] / 1000, timezone.utc):%H:%M:%S} {e['message'].rstrip()}")
    except logs.exceptions.ResourceNotFoundException:
        die(f"no logs yet for {a.name}")


def cmd_outputs(a):
    s3, b = client("s3"), cfg()["bucket"]
    prefix = f"outputs/{agent()}/{a.name}/" + (f"{a.run_id}/" if a.run_id else "")
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=b, Prefix=prefix).get("Contents", [])]
    if a.run_id and a.cat:  # one folder per unit: <run_id>/<unit_index>/<name>
        for k in keys:
            print(f"== {k}\n{s3.get_object(Bucket=b, Key=k)['Body'].read().decode()[:20000]}")
    else:
        print("\n".join(keys) or "no outputs")


def cmd_receipt(a):
    print(client("s3").get_object(Bucket=cfg()["bucket"], Key=f"runs/{a.run_id}.json")["Body"].read().decode())


def cmd_doctor(a):
    checks = []

    def check(name, fn, expect_denied=False):
        try:
            detail = fn()
            checks.append((name, "FAIL" if expect_denied else "PASS", "allowed" if expect_denied else (detail or "")))
        except Exception as e:  # noqa: BLE001
            denied = "AccessDenied" in type(e).__name__ or "AccessDenied" in str(e) or "not authorized" in str(e)
            ok = expect_denied and denied
            checks.append((name, "PASS" if ok else "FAIL", "denied as expected" if ok else f"{type(e).__name__}: {str(e)[:160]}"))

    check("credentials", lambda: client("sts").get_caller_identity()["Arn"].split("/")[-2])
    check("config", lambda: f"kiosk {cfg()['name']}, agent {agent()}, classes {cfg()['agents'][agent()]['classes']}")
    check("frozen switch", lambda: client("ssm").get_parameter(Name=f"/kiosk/{cfg()['name']}/frozen")["Parameter"]["Value"])
    check("runtime layer", lambda: str(layer_dir("runtime")))
    check("test layer", lambda: str(layer_dir("test")))
    check("registry readable", lambda: f"{client('s3').list_objects_v2(Bucket=cfg()['bucket'], Prefix='registry/').get('KeyCount', 0)} entries")
    check("cannot write the registry", lambda: client("s3").put_object(Bucket=cfg()["bucket"], Key="registry/doctor.json", Body=b"{}"), True)
    check("cannot create functions", lambda: client("lambda").create_function(
        FunctionName="kiosk-doctor-probe", Role="arn:aws:iam::000000000000:role/x", Code={"ZipFile": b"x"},
        Runtime="python3.13", Handler="x.y"), True)
    check("cannot invoke functions directly", lambda: client("lambda").invoke(FunctionName=f"{cfg()['function_prefix']}{agent()}-x"), True)
    check("cannot touch IAM", lambda: client("iam").list_roles(MaxItems=1), True)
    if a.e2e:
        def e2e():
            name, ver = "doctor-hello", f"0.0.{datetime.now(timezone.utc):%y%m%d%H%M}"
            d = WORK / f".doctor-{ver}"
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(KITS / "hello", d)
            m = json.loads((d / "manifest.json").read_text().replace("{{name}}", name))
            m["version"] = ver
            (d / "manifest.json").write_text(json.dumps(m, indent=1))
            for p in d.rglob("*.py"):
                p.write_text(p.read_text().replace("{{name}}", name))
            files = read_dir(d)
            key = f"incoming/{agent()}/{name}/{ver}/bundle.zip"
            client("s3").put_object(Bucket=cfg()["bucket"], Key=key, Body=rules().make_zip(files))
            v = start("gate", {"bundle_key": key}, f"{name}-{ver}")
            assert v.get("verdict") == "PASS", v
            p = start("promote", {"agent": agent(), "name": name, "version": ver, "stage": "canary"}, f"{name}-canary")
            assert p.get("verdict") == "PASS", p
            r = start("run", {"agent": agent(), "name": name, "alias": "live", "items": [{"who": "doctor"}]}, f"{name}-run")
            assert r.get("status") == "SUCCEEDED", r
            shutil.rmtree(d, ignore_errors=True)
            return f"{name} {ver}: gate PASS, canary {p.get('canary', {}).get('status')}, run {r['status']}"
        check("end to end (hello)", e2e)
    width = max(len(c[0]) for c in checks)
    for n, st, detail in checks:
        print(f"{st:4}  {n:<{width}}  {detail}")
    failed = [c for c in checks if c[1] != "PASS"]
    print(f"doctor: {len(checks) - len(failed)}/{len(checks)} PASS")
    sys.exit(1 if failed else 0)


def pinned_python():
    """The agent's terminal may run a bare python3 without boto3. Re-run under the Hermes interpreter, whose
    boto3/botocore match the kiosk's runtime layer, instead of installing anything."""
    try:
        import botocore  # noqa: F401
        return
    except ImportError:
        pass
    # a venv's python3 is a symlink to the same binary, so compare by path and guard against a loop
    if not os.environ.get("KIOSK_REEXEC"):
        for exe in (os.environ.get("KIOSK_PYTHON", ""), "/opt/hermes/.venv/bin/python3"):
            if exe and os.path.exists(exe) and exe != sys.executable:
                os.environ["KIOSK_REEXEC"] = "1"
                os.execv(exe, [exe, *sys.argv])
    die("boto3/botocore not found. Do not install SDKs or create venvs: run kiosk.py with "
        "/opt/hermes/.venv/bin/python3 or set KIOSK_PYTHON to an interpreter that has them.")


def main():
    pinned_python()
    ap = argparse.ArgumentParser(prog="kiosk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("doctor"); p.add_argument("--e2e", action="store_true"); p.set_defaults(f=cmd_doctor)
    sub.add_parser("setup").set_defaults(f=cmd_setup)
    p = sub.add_parser("search"); p.add_argument("words", nargs="*"); p.set_defaults(f=cmd_search)
    p = sub.add_parser("show"); p.add_argument("name"); p.add_argument("--agent"); p.add_argument("--full", action="store_true"); p.set_defaults(f=cmd_show)
    p = sub.add_parser("new"); p.add_argument("name"); p.add_argument("--kit", required=True); p.add_argument("--dir"); p.set_defaults(f=cmd_new)
    p = sub.add_parser("sdk"); p.add_argument("service"); p.add_argument("operation", nargs="?")
    p.add_argument("--grep"); p.add_argument("--depth", type=int, default=1); p.set_defaults(f=cmd_sdk)
    p = sub.add_parser("test"); p.add_argument("dir"); p.set_defaults(f=cmd_test)
    p = sub.add_parser("submit"); p.add_argument("dir"); p.set_defaults(f=cmd_submit)
    p = sub.add_parser("promote"); p.add_argument("name"); p.add_argument("version", nargs="?")
    p.add_argument("--stage", default="canary", choices=["canary", "live", "rollback", "retire"]); p.add_argument("--reason")
    p.set_defaults(f=cmd_promote)
    p = sub.add_parser("run"); p.add_argument("name"); p.add_argument("--items"); p.add_argument("--item")
    p.add_argument("--alias", default="live", choices=["live", "canary", "dev"]); p.add_argument("--concurrency", type=int, default=1)
    p.set_defaults(f=cmd_run)
    p = sub.add_parser("logs"); p.add_argument("name"); p.add_argument("--minutes", type=int, default=60); p.add_argument("--filter")
    p.set_defaults(f=cmd_logs)
    p = sub.add_parser("outputs"); p.add_argument("name"); p.add_argument("run_id", nargs="?"); p.add_argument("--cat", action="store_true")
    p.set_defaults(f=cmd_outputs)
    p = sub.add_parser("receipt"); p.add_argument("run_id"); p.set_defaults(f=cmd_receipt)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
