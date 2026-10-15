"""Kiosk gate: the only code that may create or change functions. Called by the gate, promote and run
state machines, one action per call:

  validate     caps, freeze switch, static checks (kiosk_runtime.rules), version immutability
  test         run the bundle's tests in the sandbox function (no network, no rights)
  sign         start an AWS Signer job      sign_status   poll it
  deploy       create or update the function, publish a version, point alias `dev` at it
  refuse       record a refusal (from a state machine Catch) and return the verdict
  promote      stage canary | live | rollback | retire
  resolve_run  check a run request, pick the target alias       receipt   record the run, auto-rollback

Refusals raise `Refused` (state machines catch it: a refusal is a normal answer, not an alert).
Anything else is a platform fault: the execution fails and EventBridge alerts the admin.
Counters (caps) live in S3 under events/<date>/<agent>/; the limits come from the kiosk config,
which only Terraform writes.
"""
import base64
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from kiosk_runtime import rules

BUCKET = os.environ["KIOSK_BUCKET"]
CONFIG_PARAM = os.environ["KIOSK_CONFIG_PARAM"]
FROZEN_PARAM = os.environ["KIOSK_FROZEN_PARAM"]
SANDBOX_FN = os.environ["KIOSK_SANDBOX_FN"]
SIGNING_PROFILE = os.environ["KIOSK_SIGNING_PROFILE"]
ALERT_TOPIC = os.environ.get("KIOSK_ALERT_TOPIC", "")
KEY = re.compile(r"^incoming/([a-z0-9-]+)/([a-z0-9-]+)/(\d+\.\d+\.\d+)/bundle\.zip$")
_cfg = None
_c = {}


class Refused(Exception):
    """A policy answer: the request is not allowed as it stands. Message is JSON."""


class PlatformError(Exception):
    """Something in the kiosk itself broke. The execution fails and the admin is alerted."""


def refuse(code, message, **extra):
    raise Refused(json.dumps({"code": code, "message": message, **extra}, default=str))


def aws(name):
    if name not in _c:
        _c[name] = boto3.client(name, config=Config(retries={"mode": "adaptive", "total_max_attempts": 6}))
    return _c[name]


def cfg():
    global _cfg
    if _cfg is None:
        _cfg = json.loads(aws("ssm").get_parameter(Name=CONFIG_PARAM)["Parameter"]["Value"])
    return _cfg


def frozen():
    return aws("ssm").get_parameter(Name=FROZEN_PARAM)["Parameter"]["Value"].strip().lower() == "true"


def now():
    return datetime.now(timezone.utc)


def iso():
    return now().strftime("%Y-%m-%dT%H:%M:%SZ")


def fn_name(agent, name):
    return f"{cfg()['function_prefix']}{agent}-{name}"


# ------------------------------------------------------------------ S3 helpers: registry and events
def s3_json(key, default=None):
    try:
        return json.loads(aws("s3").get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return default
        raise


def put_json(key, obj):
    aws("s3").put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj, indent=1, default=str).encode(),
                         ContentType="application/json")


def registry(agent, name):
    return s3_json(f"registry/{agent}/{name}.json") or {
        "name": name, "agent": agent, "function": fn_name(agent, name), "state": "new", "versions": {},
        "aliases": {}, "live_history": [], "runs": {"count": 0, "failed": 0}, "created": iso()}


def save_registry(reg):
    reg["updated"] = iso()
    put_json(f"registry/{reg['agent']}/{reg['name']}.json", reg)


def record_event(agent, action, name="-", version="-", **detail):
    ts = now().strftime("%H%M%S%f")
    put_json(f"events/{now():%Y-%m-%d}/{agent}/{ts}_{action}_{name}_{version}.json",
             {"at": iso(), "agent": agent, "action": action, "name": name, "version": version, **detail})


def count_events(agent, action, name=None, version=None):
    n, token = 0, None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": f"events/{now():%Y-%m-%d}/{agent}/"}
        if token:
            kw["ContinuationToken"] = token
        page = aws("s3").list_objects_v2(**kw)
        for o in page.get("Contents", []):
            parts = o["Key"].rsplit("/", 1)[-1][:-5].split("_")
            if len(parts) == 4 and parts[1] == action and name in (None, parts[2]) and version in (None, parts[3]):
                n += 1
        if not page.get("IsTruncated"):
            return n
        token = page["NextContinuationToken"]


def alert(subject, body):
    if ALERT_TOPIC:
        aws("sns").publish(TopicArn=ALERT_TOPIC, Subject=f"[kiosk {cfg()['name']}] {subject}"[:99],
                           Message=json.dumps(body, indent=1, default=str))


def agent_cfg(agent):
    a = cfg()["agents"].get(agent)
    if not a:
        refuse("AGENT_UNKNOWN", f"agent {agent!r} is not registered in this kiosk", fix="the owner adds agents in Terraform")
    return a


def parse_key(key):
    m = KEY.match(key or "")
    if not m:
        refuse("BUNDLE_KEY_INVALID", f"{key!r}", fix="submit with kiosk submit (incoming/<agent>/<name>/<version>/bundle.zip)")
    return m.groups()


# ------------------------------------------------------------------ gate: validate
def validate(ev):
    agent, name, version = parse_key(ev["bundle_key"])
    a, c = agent_cfg(agent), cfg()
    lim = c["limits"]
    if frozen():
        refuse("FROZEN", "the kiosk is frozen by the admin: no submissions or promotions", fix="wait for the admin")
    if count_events(agent, "submit") >= lim["submissions_per_agent_per_day"]:
        refuse("CAP_AGENT_SUBMISSIONS", f"{lim['submissions_per_agent_per_day']} submissions today already",
               fix="stop and report to the owner; the counter resets at 00:00 UTC")
    if count_events(agent, "submit", name, version) >= lim["submissions_per_version_per_day"]:
        refuse("CAP_VERSION_SUBMISSIONS", f"{name} {version}: {lim['submissions_per_version_per_day']} submissions today",
               fix="stop: escalate with the last refusal (do not bump the version to get around the cap)")
    record_event(agent, "submit", name, version)
    data = aws("s3").get_object(Bucket=BUCKET, Key=ev["bundle_key"])["Body"].read()
    try:
        files = rules.read_zip(data, lim["bundle_bytes"])
    except (ValueError, Exception) as e:  # noqa: BLE001 - any unreadable bundle is a refusal
        refuse("BUNDLE_INVALID", str(e)[:300], fix="build the bundle with kiosk submit")
    reg = registry(agent, name)
    old = reg["versions"].get(version, {})
    if old.get("gate", {}).get("status") == "PASS":
        refuse("VERSION_EXISTS", f"{name} {version} already passed the gate; versions are immutable",
               fix="bump the version in manifest.json")
    prev_tests = max([v.get("gate", {}).get("test_count", 0) for v in reg["versions"].values()
                      if v.get("gate", {}).get("status") == "PASS"] or [0])
    manifest, report, problems = rules.check_bundle(files, lim, c["kits"], a["classes"], prev_tests, c["compute"])
    if manifest and not problems and (manifest["name"] != name or manifest["version"] != version):
        problems.append(rules.problem("NAME_MISMATCH", "manifest name/version differ from the submitted key",
                                      "submit with kiosk submit from the function's folder", "manifest.json"))
    if problems:
        refuse("STATIC_CHECKS", f"{len(problems)} problem(s)", problems=problems[:30])
    return {"agent": agent, "name": name, "version": version, "sha256": rules.sha256(data),
            "manifest": manifest, "test_count": report["test_count"]}


# ------------------------------------------------------------------ gate: test in the sandbox
def test(ev):
    v = ev["validate"]
    data = aws("s3").get_object(Bucket=BUCKET, Key=ev["bundle_key"])["Body"].read()
    r = aws("lambda").invoke(FunctionName=SANDBOX_FN, Payload=json.dumps(
        {"bundle_b64": base64.b64encode(data).decode(), "agent": v["agent"], "name": v["name"],
         "version": v["version"]}).encode())
    out = json.loads(r["Payload"].read() or b"{}")
    if r.get("FunctionError"):
        refuse("SANDBOX_ERROR", "the tests crashed the sandbox (timeout, memory or import at module level)",
               detail=str(out)[:1500], fix="run kiosk test locally; keep tests fast and offline")
    if out.get("failed") or out.get("errors") or out.get("passed", 0) < 1:
        refuse("TESTS_FAILED", f"passed {out.get('passed')}, failed {out.get('failed')}, errors {out.get('errors')}",
               tail=out.get("tail", "")[-2500:], fix="fix the code or the test; run kiosk test until it passes")
    return {k: out.get(k) for k in ("passed", "failed", "errors", "skipped", "duration_s")}


# ------------------------------------------------------------------ gate: sign
def sign(ev):
    v = ev["validate"]
    key = f"bundles/{v['agent']}/{v['name']}/{v['version']}.zip"
    copied = aws("s3").copy_object(Bucket=BUCKET, Key=key, CopySource={"Bucket": BUCKET, "Key": ev["bundle_key"]})
    job = aws("signer").start_signing_job(
        source={"s3": {"bucketName": BUCKET, "key": key, "version": copied["VersionId"]}},
        destination={"s3": {"bucketName": BUCKET, "prefix": f"signed/{v['agent']}/{v['name']}/{v['version']}-"}},
        profileName=SIGNING_PROFILE)
    return {"job_id": job["jobId"], "attempts": 0}


def sign_status(ev):
    d = aws("signer").describe_signing_job(jobId=ev["job_id"])
    attempts = int(ev.get("attempts", 0)) + 1
    if d["status"] == "Failed":
        raise PlatformError(f"signing job {ev['job_id']} failed: {d.get('statusReason', '')}")
    if d["status"] != "Succeeded" and attempts > 60:
        raise PlatformError(f"signing job {ev['job_id']} still {d['status']} after 5 minutes")
    signed = d.get("signedObject", {}).get("s3", {}).get("key", "") if d["status"] == "Succeeded" else ""
    return {"job_id": ev["job_id"], "status": d["status"], "signed_key": signed, "attempts": attempts}


# ------------------------------------------------------------------ gate: deploy
def set_alias(fn, alias, version):
    lam = aws("lambda")
    try:
        lam.update_alias(FunctionName=fn, Name=alias, FunctionVersion=version)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        lam.create_alias(FunctionName=fn, Name=alias, FunctionVersion=version)


def ensure_log_group(fn):
    logs, group = aws("logs"), f"/aws/lambda/{fn}"
    try:
        logs.create_log_group(logGroupName=group)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
            raise
    logs.put_retention_policy(logGroupName=group, retentionInDays=cfg()["log_retention_days"])


def deploy(ev):
    v, t, c = ev["validate"], ev["test"], cfg()
    m, agent, name, version = v["manifest"], v["agent"], v["name"], v["version"]
    fn, lam = fn_name(agent, name), aws("lambda")
    role = c["classes"][m["class"]]["role_arns"].get(agent)
    if not role:
        refuse("CLASS_NOT_ALLOWED", f"no {m['class']} role for agent {agent}")
    ensure_log_group(fn)
    env = {**m.get("env", {}), "KIOSK_AGENT": agent, "KIOSK_FUNCTION": name, "KIOSK_VERSION": version,
           "KIOSK_BUCKET": BUCKET}
    conf = dict(Role=role, Handler="kiosk_runtime.entry.main", Runtime=c["runtime"], Timeout=m["timeout_s"],
                MemorySize=m["memory_mb"], Layers=[c["layers"]["runtime"]], Environment={"Variables": env},
                Description=f"{version}: {m['description']}"[:256])
    code = {"S3Bucket": BUCKET, "S3Key": ev["signed_key"]}
    try:
        lam.get_function_configuration(FunctionName=fn)
        exists = True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        exists = False
    if not exists:
        lam.create_function(FunctionName=fn, Code=code, CodeSigningConfigArn=c["code_signing_config"],
                            Architectures=["x86_64"], Publish=False,
                            Tags={"kiosk": c["name"], "agent": agent, "function": name}, **conf)
        lam.get_waiter("function_active_v2").wait(FunctionName=fn)
    else:
        lam.update_function_configuration(FunctionName=fn, **conf)
        lam.get_waiter("function_updated_v2").wait(FunctionName=fn)
        lam.update_function_code(FunctionName=fn, **code)
        lam.get_waiter("function_updated_v2").wait(FunctionName=fn)
    published = lam.publish_version(FunctionName=fn, Description=version)
    lam.put_function_concurrency(FunctionName=fn, ReservedConcurrentExecutions=m["concurrency"])
    set_alias(fn, "dev", published["Version"])
    reg = registry(agent, name)
    reg.update(function=fn, function_arn=published["FunctionArn"].rsplit(":", 1)[0], kit=m["kit"],
               cls=m["class"], description=m["description"], tags=m.get("tags", {}),
               state=reg["state"] if reg["state"] in ("live", "canary") else "dev")
    reg["aliases"]["dev"] = version
    reg["versions"][version] = {
        "lambda_version": published["Version"], "sha256": v["sha256"], "signed_key": ev["signed_key"],
        "gate": {"status": "PASS", "at": iso(), "test_count": v["test_count"], "tests": t},
        "manifest": m, "canary": None}
    save_registry(reg)
    record_event(agent, "deploy", name, version, lambda_version=published["Version"])
    return {"verdict": "PASS", "agent": agent, "name": name, "version": version,
            "lambda_version": published["Version"], "function": fn, "tests": t,
            "next": f"kiosk promote {name} {version}"}


# ------------------------------------------------------------------ refusals (from a Catch)
def refuse_action(ev):
    err = ev.get("error") or {}
    try:
        cause = json.loads(err.get("Cause") or "{}")
        detail = json.loads(cause.get("errorMessage") or "{}")
    except ValueError:
        detail = {"code": err.get("Error", "UNKNOWN"), "message": str(err.get("Cause", ""))[:500]}
    verdict = {"verdict": "FAIL", **detail}
    key = ev.get("bundle_key") or ""
    m = KEY.match(key)
    if m:
        agent, name, version = m.groups()
        if agent in cfg()["agents"]:
            reg = registry(agent, name)
            if reg["versions"].get(version, {}).get("gate", {}).get("status") != "PASS":
                reg["versions"][version] = {"gate": {"status": "FAIL", "at": iso(), "code": detail.get("code"),
                                                     "message": detail.get("message")}}
                save_registry(reg)
            record_event(agent, "refuse", name, version, code=detail.get("code"))
        verdict.update(agent=agent, name=name, version=version)
    return verdict


# ------------------------------------------------------------------ promote: canary | live | rollback | retire
def invoke_alias(fn, alias, unit, run_id):
    r = aws("lambda").invoke(FunctionName=f"{fn}:{alias}",
                             Payload=json.dumps({"kiosk": {"run_id": run_id}, "unit": unit}).encode())
    body = json.loads(r["Payload"].read() or b"{}")
    if r.get("FunctionError"):
        return {"status": "FAILED", "error": str(body.get("errorMessage", body))[:500]}
    return body


def go_live(reg, version):
    fn, prev = reg["function"], reg["aliases"].get("live")
    set_alias(fn, "live", reg["versions"][version]["lambda_version"])
    if prev and prev != version:
        reg["live_history"].append(prev)
    reg["aliases"]["live"] = version
    reg["state"] = "live"
    reg["live_runs"] = {"version": version, "statuses": []}
    reg["versions"][version]["live_at"] = iso()


def promote(ev):
    inp = ev["input"]
    agent, name, stage = inp.get("agent", ""), inp.get("name", ""), inp.get("stage", "canary")
    a, lim = agent_cfg(agent), cfg()["limits"]
    reg = s3_json(f"registry/{agent}/{name}.json")
    if not reg:
        refuse("UNKNOWN_FUNCTION", f"{agent}/{name} is not in the registry", fix="kiosk search")
    fn = reg["function"]
    if stage == "rollback":
        if not reg["live_history"]:
            refuse("NO_PREVIOUS_VERSION", "nothing to roll back to")
        prev = reg["live_history"].pop()
        bad_version = reg["aliases"].get("live")
        set_alias(fn, "live", reg["versions"][prev]["lambda_version"])
        reg["aliases"]["live"], reg["live_runs"] = prev, {"version": prev, "statuses": []}
        save_registry(reg)
        record_event(agent, "rollback", name, prev, from_version=bad_version, reason=inp.get("reason", "requested"))
        alert(f"rolled back {name} to {prev}", {"agent": agent, "from": bad_version, "reason": inp.get("reason")})
        return {"verdict": "PASS", "stage": "rollback", "live": prev, "from": bad_version}
    if stage == "retire":
        aws("lambda").put_function_concurrency(FunctionName=fn, ReservedConcurrentExecutions=0)
        reg["state"], reg["retired_at"] = "retired", iso()
        save_registry(reg)
        record_event(agent, "retire", name)
        return {"verdict": "PASS", "stage": "retire", "name": name}
    if frozen():
        refuse("FROZEN", "the kiosk is frozen by the admin", fix="wait for the admin")
    if count_events(agent, "promote") >= lim["promotions_per_agent_per_day"]:
        refuse("CAP_PROMOTIONS", f"{lim['promotions_per_agent_per_day']} promotions today already",
               fix="stop and report to the owner")
    version = inp.get("version", "")
    v = reg["versions"].get(version)
    if not v or v.get("gate", {}).get("status") != "PASS":
        refuse("NOT_GATED", f"{name} {version} has not passed the gate", fix="kiosk submit first")
    if reg["state"] == "retired":
        refuse("RETIRED", f"{name} is retired")
    record_event(agent, "promote", name, version, stage=stage)
    if stage == "canary":
        set_alias(fn, "canary", v["lambda_version"])
        reg["aliases"]["canary"] = version
        env = invoke_alias(fn, "canary", v["manifest"]["canary_input"], f"canary-{version}")
        v["canary"] = {"status": env.get("status"), "at": iso(), "duration_ms": env.get("duration_ms"),
                       "error": env.get("error"), "summary": env.get("summary")}
        if env.get("status") != "SUCCEEDED":
            save_registry(reg)
            refuse("CANARY_FAILED", f"canary run returned {env.get('status')}", envelope=env,
                   fix="read kiosk logs, fix, bump the version, submit again; live is unchanged")
        if a.get("policy") == "auto":
            go_live(reg, version)
        else:
            reg["state"] = "canary"
            reg["pending_approval"] = version
        save_registry(reg)
        return {"verdict": "PASS", "stage": "canary", "canary": v["canary"], "live": reg["aliases"].get("live"),
                "waiting_for_owner": a.get("policy") != "auto"}
    if stage == "live":
        if (v.get("canary") or {}).get("status") != "SUCCEEDED":
            refuse("CANARY_REQUIRED", f"{name} {version} has no successful canary", fix=f"kiosk promote {name} {version}")
        if a.get("policy") != "auto" and inp.get("approved_by") != "owner":
            refuse("OWNER_APPROVAL_REQUIRED", "this agent's promotions need the owner")
        go_live(reg, version)
        reg.pop("pending_approval", None)
        save_registry(reg)
        return {"verdict": "PASS", "stage": "live", "live": version}
    refuse("STAGE_INVALID", f"stage {stage!r}", fix="canary, live, rollback or retire")


# ------------------------------------------------------------------ run: resolve + receipt
def resolve_run(ev):
    inp, lim = ev["input"], cfg()["limits"]
    agent, name, alias = inp.get("agent", ""), inp.get("name", ""), inp.get("alias", "live")
    agent_cfg(agent)
    reg = s3_json(f"registry/{agent}/{name}.json")
    if not reg or reg.get("state") == "retired":
        refuse("UNKNOWN_FUNCTION", f"{agent}/{name} is unknown or retired", fix="kiosk search")
    if alias not in ("live", "canary", "dev") or not reg["aliases"].get(alias):
        refuse("ALIAS_NOT_SET", f"{name} has no {alias} version", fix="promote first, or run --alias dev")
    if frozen() and alias != "live":
        refuse("FROZEN", "frozen kiosk: only live versions run")
    if count_events(agent, "run") >= lim["runs_per_agent_per_day"]:
        refuse("CAP_RUNS", f"{lim['runs_per_agent_per_day']} runs today already", fix="stop and report to the owner")
    items = inp.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= lim["items_per_run"]:
        refuse("ITEMS_INVALID", f"items must be a list of 1 to {lim['items_per_run']} units")
    for i, it in enumerate(items):
        if len(json.dumps(it)) > lim["item_bytes"]:
            refuse("ITEM_TOO_LARGE", f"item {i} over {lim['item_bytes']} bytes", fix="pass S3 keys, not data")
    version = reg["aliases"][alias]
    manifest_conc = reg["versions"][version]["manifest"]["concurrency"]
    conc = max(1, min(int(inp.get("concurrency", 1)), manifest_conc, lim["concurrency"]))
    run_id = f"{now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    record_event(agent, "run", name, version, run_id=run_id, items=len(items))
    return {"run_id": run_id, "agent": agent, "name": name, "alias": alias, "version": version,
            "target": f"{reg['function_arn']}:{alias}", "items": items, "concurrency": conc}


def receipt(ev):
    run, results = ev["run"], ev.get("results", [])
    units, statuses = [], []
    for i, r in enumerate(results):
        env = r.get("payload") if isinstance(r, dict) and "payload" in r else r
        env = env if isinstance(env, dict) else {"status": "FAILED", "error": str(env)[:300]}
        st = env.get("status", "FAILED")
        statuses.append(st)
        units.append({"i": i, "status": st, "outputs": env.get("outputs", [])[:20],
                      "duration_ms": env.get("duration_ms"), "error": (env.get("error") or env.get("cause") or "")[:300],
                      "summary": env.get("summary", {})})
    ok = statuses.count("SUCCEEDED")
    status = "SUCCEEDED" if ok == len(statuses) else ("FAILED" if statuses.count("FAILED") == len(statuses) else "PARTIAL")
    rec = {"run_id": run["run_id"], "agent": run["agent"], "name": run["name"], "alias": run["alias"],
           "version": run["version"], "status": status, "units": len(units), "succeeded": ok,
           "failed": statuses.count("FAILED"), "partial": statuses.count("PARTIAL"), "finished": iso(),
           "results": units}
    put_json(f"runs/{run['run_id']}.json", rec)
    reg = registry(run["agent"], run["name"])
    reg["runs"]["count"] += 1
    reg["runs"]["failed"] += 0 if status == "SUCCEEDED" else 1
    reg["runs"]["last"] = {"run_id": run["run_id"], "status": status, "at": rec["finished"]}
    lr = reg.get("live_runs") or {}
    if run["alias"] == "live" and lr.get("version") == run["version"]:
        lr["statuses"].append(status)
        first = lr["statuses"][:3]
        if len(first) <= 3 and first.count("SUCCEEDED") < len(first) and len(first) - first.count("SUCCEEDED") >= 2 \
                and reg["live_history"]:
            save_registry(reg)
            rb = promote({"input": {"agent": run["agent"], "name": run["name"], "stage": "rollback",
                                    "reason": f"2 of the first {len(first)} live runs of {run['version']} failed"}})
            rec["rolled_back"] = rb
            put_json(f"runs/{run['run_id']}.json", rec)
            return {k: rec[k] for k in rec if k != "results"} | {"results": units[:20]}
    save_registry(reg)
    return {k: rec[k] for k in rec if k != "results"} | {"results": units[:20]}


ACTIONS = {"validate": validate, "test": test, "sign": sign, "sign_status": sign_status, "deploy": deploy,
           "refuse": refuse_action, "promote": promote, "resolve_run": resolve_run, "receipt": receipt}


def handler(event, context):
    return ACTIONS[event["action"]](event)
