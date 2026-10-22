"""rgtriage: read-only AWS security triage for people and for the Hermes agent.

  rgtriage init                 create ~/.rgtriage/triage.yaml from your current AWS identity
  rgtriage doctor               check access and which security sources are enabled
  rgtriage scan                 collect + prioritize; prints the attention board
  rgtriage digest               print the latest attention board without rescanning
  rgtriage list / show REF      browse the prioritized queue
  rgtriage fix REF --iac PATH   locate the deploying IaC and load the remediation playbook
  rgtriage decide REF STATUS    record acknowledged / fixing / accepted_risk / false_positive / resolved
  rgtriage watch                scan and print only new urgent findings (for schedules)
  rgtriage aws SVC OP           one guarded read-only AWS API call for investigation
  rgtriage onboarding           which accounts are covered and the one-time setup for the rest
  rgtriage knowledge [VIEW]     the desk's knowledge (OKF bundle): overview, search, show, for REF, gaps, review
  rgtriage knowledge-edit ...   change the knowledge (dashboard Knowledge tab and operators; never the agent)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from . import __version__, accounts, aws, collect, config, digest, iac, knowledge, okf, playbooks, prioritize, store

PRIORITY_ORDER = ("P1", "P2", "P3", "P4")


def _out(text: str = "") -> None:
    print(text)


def _json(data) -> None:
    print(json.dumps(data, indent=1, default=str))


def _latest_or_exit() -> dict:
    scan = store.load_latest()
    if not scan:
        sys.exit("No scan yet. Run: rgtriage scan")
    return scan


def _ref_or_exit(scan: dict, ref: str) -> dict:
    finding = store.find(scan, ref)
    if not finding:
        sys.exit(f"No unique finding matches {ref!r}. Use a ref from `rgtriage list`.")
    return finding


def _age(scan: dict) -> str:
    then = datetime.fromisoformat(scan["scanned_at"].replace("Z", "+00:00"))
    minutes = int((datetime.now(timezone.utc) - then).total_seconds() // 60)
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h"


# ------------------------------------------------------------------ commands

def cmd_init(args):
    path = config.config_path()
    if path.exists() and not args.force:
        sys.exit(f"{path} already exists (use --force to overwrite)")
    session = aws.guarded(__import__("boto3").Session(profile_name=args.profile or None))
    identity = session.client("sts").get_caller_identity()
    region = args.region or session.region_name or "us-east-1"
    config.write_example(path, name=args.name or f"aws-{identity['Account']}", region=region,
                         account_id=identity["Account"], profile=args.profile or "default")
    _out(f"Wrote {path} for account {identity['Account']} ({identity['Arn']}) in {region}.")
    _out("Next: edit criticality/goals/iac_paths if you like, then run `rgtriage doctor` and `rgtriage scan`.")


def cmd_doctor(args):
    profile = config.load()
    profile["max_findings_per_source"] = 1
    _out(f"Triage profile: {config.config_path()}  (state: {config.home()})")
    for account in profile["accounts"]:
        try:
            session = aws.session_for(account)
            ident = session.client("sts").get_caller_identity()
            _out(f"- account {account['name']}: {ident['Account']} as {ident['Arn']}  regions {', '.join(account['regions'])}")
        except (ClientError, BotoCoreError) as exc:
            _out(f"- account {account['name']}: CANNOT AUTHENTICATE — {exc}")
    _, coverage = collect.collect(profile)
    _out("\nSource status (one-page probe):")
    for c in sorted(coverage, key=lambda c: (c["account"], c["source"], c["region"])):
        note = f"  {c.get('note', '')[:140]}" if c["status"] != "ok" else ""
        _out(f"  {c['status']:<12} {c['source']:<15} {c['account']}/{c['region']}{note}")
    advice = []
    statuses = {(c["source"], c["status"]) for c in coverage}
    if ("securityhub", "ok") not in statuses:
        advice.append("Enable Security Hub (CSPM) with AWS Foundational Security Best Practices: it is the main posture source.")
    if ("guardduty", "ok") not in statuses:
        advice.append("Enable GuardDuty: without it there is no threat detection.")
    if any(c["status"] == "denied" for c in coverage):
        advice.append("Some reads were denied: attach the AWS managed policy SecurityAudit to the reading identity/role.")
    if ("inspector", "ok") not in statuses:
        advice.append("Inspector is off: no vulnerability findings for EC2/ECR/Lambda.")
    for path in profile.get("iac_paths", []):
        try:
            idx = iac.build([path]).summary()
            _out(f"\nIaC {path}: {idx['resources']} resources {idx['by_tool']}, {idx['state_ids']} state ids")
        except FileNotFoundError as exc:
            advice.append(str(exc))
    if advice:
        _out("\nRecommendations:")
        for a in advice:
            _out(f"  - {a}")


def run_scan(sources=None, progress=None) -> dict:
    profile = config.load()
    try:
        onboarding = accounts.discover(profile, store.load_onboarding())
    except Exception as exc:  # onboarding must never stop the configured accounts from being scanned
        onboarding = {"mode": "unknown", "admin": {}, "notes": [f"account discovery failed: {type(exc).__name__}: {exc}"[:240]]}
    findings, coverage = collect.collect(profile, sources, progress, skip=accounts.skip_pairs(onboarding))
    try:
        knowledge.ensure()
        known = knowledge.effective()
    except Exception as exc:  # unreadable knowledge must never stop a scan; the board says why
        known = {"error": f"{type(exc).__name__}: {exc}"[:240]}
    findings, _ = prioritize.prioritize(findings, profile, store.load_decisions(), known)
    scan = {
        "version": __version__, "scanned_at": collect.now_iso(),
        "profile": {"name": profile["name"], "accounts": [{"name": a["name"], "account_id": a.get("account_id"),
                    "criticality": a["criticality"]} for a in profile["accounts"]], "goals": [g.get("text") for g in profile["goals"]]},
        "findings": findings, "coverage": coverage, "onboarding": onboarding,
    }
    store.save_onboarding(onboarding, profile)
    store.mark_changes(scan)
    try:
        scan["knowledge"] = knowledge.scan_summary(scan, known) if "error" not in known else {"error": known["error"]}
    except Exception as exc:
        scan["knowledge"] = {"error": f"{type(exc).__name__}: {exc}"[:240]}
    scan["issues"] = prioritize.build_issues(findings)  # before capping, so issue counts cover every finding read
    store.cap_findings(scan, int(profile["max_stored_findings"]))
    store.save_scan(scan)
    write_outputs(scan)
    return scan


def write_outputs(scan: dict) -> None:
    """Pre-rendered views so the Hermes hook never has to load or rank the full scan."""
    home = config.home()
    (home / "digest.md").write_text(digest.markdown(scan), encoding="utf-8")
    (home / "board.md").write_text(digest.markdown(scan, limit=6), encoding="utf-8")
    (home / "report.html").write_text(digest.html_report(scan), encoding="utf-8")
    store._write(home / "status.json", {"scanned_at": scan["scanned_at"], "summary": digest.summary_line(scan),
                                        "changes": {k: v for k, v in scan["changes"].items() if k != "no_longer_active"}})


def cmd_scan(args):
    def progress(entry):
        if not args.quiet:
            print(f"  {entry['status']:<11} {entry['source']:<15} {entry['account']}/{entry['region']} ({entry['count']})", file=sys.stderr)
    scan = run_scan(args.sources.split(",") if args.sources else None, progress)
    if args.json:
        _json({"summary": digest.summary_line(scan), "changes": scan["changes"], "issues": scan["issues"][:args.limit]})
    elif not args.quiet:
        _out(digest.markdown(scan, limit=args.limit))
        _out(f"\nFull report: {config.home() / 'report.html'}")


def cmd_digest(args):
    scan = _latest_or_exit()
    _out(digest.markdown(scan, limit=args.limit, include_low=args.all))
    _out(f"\n(scan is {_age(scan)} old — `rgtriage scan` to refresh)")


def cmd_list(args):
    scan = _latest_or_exit()
    rows = scan["findings"]
    if args.priority:
        wanted = set(args.priority.upper().split(","))
        rows = [f for f in rows if f["priority"] in wanted]
    if args.source:
        rows = [f for f in rows if args.source.lower() in (f["source"], f["product"].lower())]
    if args.category:
        rows = [f for f in rows if f["category"] == args.category]
    if args.account:
        rows = [f for f in rows if args.account in (f["account"],)]
    if not args.all:
        rows = [f for f in rows if prioritize.is_open(f)]
    if args.issues:
        issues = [i for i in scan["issues"] if (not args.priority or i["priority"] in args.priority.upper().split(","))]
        if args.json:
            return _json(issues[:args.limit])
        for i in issues[:args.limit]:
            _out(f"{i['priority']} {i['score']:>3}  {i['top_key']}  {i['title'][:80]}  [{i['finding_count']} findings, {i['resource_count']} resources]")
        return
    if args.json:
        return _json(rows[:args.limit])
    for f in rows[:args.limit]:
        new = "NEW " if f.get("new") else ""
        _out(f"{f['priority']} {f['score']:>3}  {f['key']}  {new}{f['product']}/{f['severity']}  {f['title'][:70]}  "
             f"→ {f['resource'].get('name') or f['resource'].get('id')} ({f['account']}/{f['region']})")
    if len(rows) > args.limit:
        _out(f"... {len(rows) - args.limit} more (--limit)")


def cmd_show(args):
    scan = _latest_or_exit()
    f = _ref_or_exit(scan, args.ref)
    if args.json:
        return _json(f)
    _out(f"# {f['title']}")
    _out(f"Ref {f['key']} · {f['priority']} (score {f['score']}) · {f['product']} severity {f['severity']} · {f['category']}")
    _out(f"Account {f['account']} · region {f['region']} · first seen {f.get('first_seen')} · last seen {f.get('last_seen')}")
    _out(f"Evidence basis: stored scan from {scan.get('scanned_at')} UTC; the title and severity are the source's or the "
         "desk's classification, not live AWS state. Verify the claim with a live read before concluding.")
    if f.get("control_id") or f.get("type"):
        _out(f"Control/type: {f.get('control_id') or ''} {f.get('type') or ''}".strip())
    r = f["resource"]
    _out(f"Resource: {r.get('type')} {r.get('id')}" + (f" tags={json.dumps(r.get('tags'))}" if r.get("tags") else ""))
    if f.get("description"):
        _out(f"\n{f['description']}")
    _out("\nWhy this priority:")
    for reason in f["reasons"]:
        _out(f"  - {reason}")
    for key in ("actor", "access", "packages", "image", "standards"):
        if f["context"].get(key):
            _out(f"{key.capitalize()}: {json.dumps(f['context'][key], default=str)}")
    if f.get("related"):
        _out("Related findings on the same resource: " + ", ".join(f["related"]))
    key = prioritize.group_key(f)
    siblings = [m for m in scan["findings"] if m["key"] != f["key"] and prioritize.group_key(m) == key]
    if siblings:  # one issue, several resources: each has its own ref, priority and decision
        _out("Same issue on other resources (show their ref for that resource):")
        for m in sorted(siblings, key=lambda m: -m["score"])[:10]:
            decision = (m.get("decision") or {}).get("status") or ("accepted_risk" if m.get("accepted") else "")
            _out(f"  - {m['resource'].get('name') or m['resource'].get('id')} ({m['account']}/{m['region']}) ref {m['key']} "
                 f"{m['priority']}" + (f" · decision {decision}" if decision else ""))
        if len(siblings) > 10:
            _out(f"  ... {len(siblings) - 10} more (`list all=true`)")
    if f.get("owner"):
        _out(f"Owner: {f['owner']['title']} (knowledge {f['owner']['path']})")
    if f.get("decision"):
        _out(f"Decision: {json.dumps(f['decision'])}")
    if f.get("knowledge"):
        _out("Knowledge used: " + ", ".join(f["knowledge"]) + "  (`rgtriage knowledge show PATH`)")
    if f["remediation"].get("text") or f["remediation"].get("url"):
        _out(f"\nAWS remediation: {f['remediation'].get('text', '')} {f['remediation'].get('url', '')}")
    _out(f"Console: {f.get('console_url')}")
    _out(f"Playbooks: {', '.join(playbooks.select(f))}  (`rgtriage fix {f['key']}`)")
    try:
        practices = knowledge.practices_for(f.get("control_id") or "", knowledge.bundle().concepts())
    except Exception:  # knowledge is context; never block show on it
        practices = []
    for p in practices:
        _out(f"Security practice: {p.title} — {p.path}  (`rgtriage knowledge show {p.path}`)")
    from .improve import hints
    _out(hints.line(f, practices))


def cmd_fix(args):
    scan = _latest_or_exit()
    f = _ref_or_exit(scan, args.ref)
    paths = args.iac or config.load().get("iac_paths", [])
    _out(f"# Fix context for {f['key']}: {f['title']}")
    _out(f"{f['priority']} · {f['product']} {f['severity']} · control/type {f.get('control_id') or f.get('type')} · "
         f"resource {f['resource'].get('type')} `{f['resource'].get('id')}` · account {f['account']} / {f['region']}")
    if f["remediation"].get("url"):
        _out(f"AWS remediation doc: {f['remediation']['url']}")
    try:
        from .improve import hints
        _out(hints.line(f, knowledge.practices_for(f.get("control_id") or "", knowledge.bundle().concepts())))
    except Exception:  # guidance is a hint; never block the fix context on it
        pass
    _out("\n## Where it is defined in code")
    if not paths:
        _out("No IaC paths configured. Pass --iac PATH (repeatable) or add iac_paths to triage.yaml.")
    else:
        try:
            index = iac.build(paths)
        except FileNotFoundError as exc:
            sys.exit(str(exc))
        s = index.summary()
        _out(f"Indexed {s['resources']} IaC resources {s['by_tool']} under {', '.join(s['roots'])}.")
        matches = index.match(f)
        if not matches:
            _out("No IaC resource of this type found. The resource was likely created outside these repos "
                 "(console/CLI/another repo): fix it directly now and import it into IaC to prevent drift.")
        for n, m in enumerate(matches, 1):
            _out(f"\n### Candidate {n} — confidence {m['confidence']}: {m.get('address') or ''}")
            _out(f"Evidence: {m['why']}")
            if m.get("file"):
                _out(f"File: {m['file']}:{m['line']}" + (f"  (CDK construct {m['cdk_path']})" if m.get("cdk_path") else ""))
                if n <= args.excerpts:
                    _out("```\n" + iac.excerpt(m["file"], m["line"], m["end_line"]) + "\n```")
            if m.get("related"):
                _out("Related blocks that configure it: " + ", ".join(f"{r['address']} ({r['file']}:{r['line']})" for r in m["related"]))
    _out("\n## Remediation playbook")
    for name in playbooks.select(f):
        _out(playbooks.load(name))
    try:
        org = [k for k in knowledge.for_finding(f) if not knowledge.is_shipped(k["path"])]
    except Exception:  # knowledge is context here; never block the fix context on it
        org = []
    if org:
        _out("\n## Organization knowledge to respect")
        for k in org[:6]:
            _out(f"- {k['title']} ({k['type']}, {k['trust']}) — {k['path']}: {k['description']}  [{k['why']}]")
    _out("Rules: propose a minimal unified diff in the repo's existing style; state blast radius and rollback; "
         "the operator reviews and applies. This tool never changes code or cloud resources.")


def cmd_decide(args):
    scan = _latest_or_exit()
    f = _ref_or_exit(scan, args.ref)
    keys = [f["key"]]
    if args.issue:
        issue = next((i for i in scan["issues"] if f["key"] in i["finding_keys"]), None)
        keys = issue["finding_keys"] if issue else keys
    for key in keys:
        decision = store.save_decision(key, args.status, args.reason, args.by)
    for item in scan["findings"]:
        if item["key"] in keys:
            item["decision"] = decision
    for issue in scan["issues"]:
        if issue["top_key"] in keys:
            issue["decision"] = decision
    store.write_latest(scan)
    write_outputs(scan)
    _out(f"Recorded {args.status} for {len(keys)} finding(s): {args.reason}")


def cmd_report(args):
    scan = _latest_or_exit()
    path = config.home() / "report.html"
    path.write_text(digest.html_report(scan), encoding="utf-8")
    _out(str(path))
    if args.open:
        webbrowser.open(path.as_uri())


def cmd_watch(args):
    had_previous = store.load_latest() is not None
    scan = run_scan()
    threshold = PRIORITY_ORDER.index(args.min_priority)
    urgent = [f for f in scan["findings"] if f.get("new") and prioritize.is_open(f)
              and PRIORITY_ORDER.index(f["priority"]) <= threshold]
    if not had_previous:
        _out(digest.markdown(scan, limit=5))
        return
    onboarded = (scan.get("onboarding") or {}).get("newly_readable") or []
    if onboarded:
        _out(f"➕ Now reading {len(onboarded)} more account(s) through their read role: {', '.join(onboarded[:10])} "
             "(existing findings taken as the baseline)")
    if not urgent:
        return  # silent: nothing new that matters
    _out(f"🔔 {len(urgent)} new {'/'.join(PRIORITY_ORDER[:threshold + 1])} security finding(s) — {scan['profile']['name']}")
    for f in urgent[:10]:
        _out(f"- {f['priority']} {f['title'][:100]} — {f['product']} {f['severity']} on "
             f"{f['resource'].get('name') or f['resource'].get('id')} ({f['account']}/{f['region']}) ref {f['key']}")
    _out(f"Now: {digest.summary_line(scan)}. Ask the security desk: \"triage {urgent[0]['key']}\"")


# Reads that would put credentials into the conversation.
AWS_REFUSED = {"AssumeRole", "AssumeRoleWithSAML", "AssumeRoleWithWebIdentity", "GetSessionToken", "GetFederationToken"}
MORE_PAGES = ("NextToken", "nextToken", "Marker", "NextMarker", "NextPageToken", "nextPageToken")


def _aws_account(known: list[dict], wanted: str | None) -> dict:
    """The account an AWS read runs in. With several readable accounts the caller must name one: a silent default
    would attribute another account's configuration to the resource in question."""
    if wanted:
        account = next((a for a in known if wanted in (a["name"], a.get("account_id"))), None)
        if not account:
            sys.exit(f"Unknown account {wanted}. Readable accounts: "
                     + ", ".join(f"{a['name']} ({a.get('account_id') or '?'})" for a in known))
        return account
    if len(known) > 1:
        sys.exit("Several accounts are readable; pass account=<name or id> (use the finding's account): "
                 + ", ".join(f"{a['name']} ({a.get('account_id') or '?'})" for a in known))
    return known[0]


def evidence_header(service: str, op: str, params: dict, account: dict, region: str, observed: str,
                    result: dict | None, truncated: bool, recorded: bool = False) -> str:
    """One line that travels with every AWS read: what was asked, where, when, and whether the answer is complete."""
    import hashlib
    eid = hashlib.sha256(json.dumps([service, op, params, account.get("account_id"), region, observed],
                                    sort_keys=True, default=str).encode()).hexdigest()[:8]
    pages = [k for k in MORE_PAGES if (result or {}).get(k)] + (["IsTruncated"] if (result or {}).get("IsTruncated") else [])
    completeness = "truncated output" if truncated else (f"partial: more pages ({pages[0]})" if pages else "complete")
    kind = "evaluation (policy simulation/check, not observed configuration)" \
        if aws.snake_to_pascal(op) in aws.EVALUATIONS else "observed"
    where = f"account {account['name']} ({account.get('account_id') or '?'}) · region {region}"
    return (f"Evidence e-{eid} · {service}.{op} · {where} · {'recorded fixture' if recorded else 'observed ' + observed}"
            f" · {completeness} · {kind}")


def cmd_aws(args):
    profile = config.load()
    known = profile["accounts"] + store.discovered_accounts(profile)
    account = _aws_account(known, args.account)
    region = args.region or account["regions"][0]
    op = args.operation.replace("-", "_")
    name = aws.snake_to_pascal(op)
    if name in AWS_REFUSED:
        sys.exit(f"Refused: {op} returns credentials; the desk never handles credentials.")
    if not aws.is_read_operation(name):
        sys.exit(f"Refused: {op} is not a read-only operation (allowed prefixes: describe/get/list/batch_get/lookup/search, "
                 "plus the IAM policy simulator and Access Analyzer policy checks).")
    params = json.loads(args.params) if args.params else {}
    observed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recorded = os.environ.get("RGTRIAGE_EVAL_AWS")
    if recorded:  # offline evaluation: answer from the fixture's recorded responses; never reach AWS
        keyed = [re.split(r"[:/]", v)[-1] for v in params.values() if isinstance(v, str)][:1]  # RoleName or ARN tail
        candidates = [Path(recorded) / f"{args.service}.{op}.{k}.json" for k in keyed] + [Path(recorded) / f"{args.service}.{op}.json"]
        path = next((c for c in candidates if c.is_file()), None)
        if not path:
            return _out(f"No recorded response for {args.service} {op} in this evaluation fixture (treat as not available).")
        text = path.read_text(encoding="utf-8")
        try:
            result = json.loads(text)
        except ValueError:
            result = None
        if isinstance(result, dict) and result.get("Error"):  # a recorded AWS error, e.g. AccessDenied
            sys.exit(f"AWS error: {result['Error']}")
        truncated = len(text) > args.max_chars
        return _out(evidence_header(args.service, op, params, account, region, observed, result if isinstance(result, dict) else None,
                                    truncated, recorded=True) + "\n" + text[:args.max_chars])
    try:
        client = aws.client(aws.session_for(account, region), args.service, region)
        result = getattr(client, op)(**params)
    except AttributeError:
        sys.exit(f"{args.service} has no operation {op}")
    except (ClientError, BotoCoreError, aws.WriteBlocked) as exc:
        sys.exit(f"AWS error ({args.service}.{op} · account {account['name']} · region {region}): {exc}")
    result.pop("ResponseMetadata", None)
    text = json.dumps(result, indent=1, default=str)
    truncated = len(text) > args.max_chars
    if truncated:
        text = text[:args.max_chars] + f"\n... truncated ({len(text)} chars; narrow the query or raise --max-chars)"
    _out(evidence_header(args.service, op, params, account, region, observed, result, truncated) + "\n" + text)


def cmd_validate(args):
    """Overlay proposed files on a copy of a Terraform module and run init/validate/fmt. Never plans or applies."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    terraform = shutil.which("terraform")
    if not terraform:
        sys.exit("terraform is not on PATH; cannot validate. Ask the operator to run `terraform validate`.")
    module = Path(args.module).expanduser()
    if not module.is_dir():
        sys.exit(f"module folder not found: {module}")
    with tempfile.TemporaryDirectory(prefix="rgtriage-validate-") as tmp:
        work = Path(tmp) / "module"
        shutil.copytree(module, work, ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", ".git", "*.tfvars", "*.tfvars.json"))
        for spec in args.file:
            source, _, name = spec.partition("=")
            source_path = Path(source).expanduser()
            if not source_path.is_file():
                sys.exit(f"proposed file not found: {source_path}")
            shutil.copy2(source_path, work / (name or source_path.name))
        env = {k: v for k, v in __import__("os").environ.items() if not k.startswith("AWS_")}
        env["TF_IN_AUTOMATION"] = "1"
        if env.get("TF_PLUGIN_CACHE_DIR"):  # reuse downloaded providers across validations
            Path(env["TF_PLUGIN_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
        steps = [("init", [terraform, "init", "-backend=false", "-input=false", "-no-color"]),
                 ("validate", [terraform, "validate", "-no-color"]),
                 ("fmt", [terraform, "fmt", "-check", "-diff", "-no-color"])]
        ok = True
        for label, cmd in steps:
            proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            text = (proc.stdout + proc.stderr).strip()
            if label == "init" and proc.returncode == 0:
                _out("init: ok (no backend, providers downloaded)")
                continue
            status = "ok" if proc.returncode == 0 else ("formatting differences" if label == "fmt" else "FAILED")
            ok = ok and (proc.returncode == 0 or label == "fmt")
            _out(f"{label}: {status}")
            if text and (proc.returncode != 0 or label == "validate"):
                _out(text[-3000:])
            if label == "init" and proc.returncode != 0:
                break
    _out("Result: " + ("VALID — syntax and provider schema check passed (this is not a plan; review `terraform plan` before applying)."
                       if ok else "NOT VALID — fix the errors above and validate again."))


def cmd_serve(args):
    from . import durable, server
    try:
        print(f"knowledge: {json.dumps(knowledge.seed())}", flush=True)  # shipped concepts follow the installed version
    except Exception as exc:
        print(f"knowledge seed failed: {exc}", flush=True)
    server.serve(args.socket, durable_url=args.durable, homes=durable.parse_homes(args.home), every=args.every, spot=args.spot,
                 scan_every_hours=args.scan_every_hours)


def cmd_durable(args):
    from . import durable
    store = durable.backend(args.url)
    owner = tuple(int(x) for x in args.owner.split(":")) if args.owner else None
    for name, home in durable.parse_homes(args.home).items():
        result = durable.checkpoint(home, name, store, force=args.force) if args.action == "checkpoint" else durable.restore(home, name, store, owner)
        _out(json.dumps(result))


def cmd_onboarding(args):
    """Live onboarding check: organization, delegated administrator, which accounts are read and how to add the rest."""
    profile = config.load()
    report = accounts.discover(profile, store.load_onboarding())
    report["next_steps"] = accounts.next_steps(report)
    if args.json:
        return _json(report)
    _out(f"Desk identity (assumes member roles): {report['reader_arn'] or 'unknown'}")
    if report["mode"] == "organization":
        listing = {"organization": "all organization accounts",
                   "admin_members": "accounts known from delegated-administrator member lists"}.get(report["account_list"], "")
        _out(f"AWS Organization {report['organization_id']} · {report['known_accounts']} accounts known ({listing})")
    else:
        _out("Not part of an AWS Organization (or the organization is not readable).")
    for service in accounts.ADMIN_SERVICES:
        ids = report["admin"].get(service)
        _out(f"  {service:<12} " + (f"delegated administrator for {len(ids)} member accounts" if ids else "not administrator"))
    _out(f"Read fully ({len(report['full_read'])}): {', '.join(report['full_read']) or '-'}")
    _out(f"Findings only, no {report['member_role_name']} role ({len(report['findings_only'])}): "
         f"{', '.join(report['findings_only'][:20]) or '-'}")
    _out(f"Not covered ({len(report['not_covered'])}): {', '.join(report['not_covered'][:20]) or '-'}")
    for note in report["notes"]:
        _out(f"Note: {note}")
    if report["next_steps"]:
        _out("\nNext steps:")
        for n, step in enumerate(report["next_steps"], 1):
            _out(f"{n}. {step}")
    else:
        _out("\nEvery known account is read fully. New accounts are picked up automatically at the next scan.")


KNOWLEDGE_VIEWS = ("overview", "search", "show", "for", "gaps", "list", "graph", "validate", "review", "inspect", "log", "kinds")


def cmd_knowledge(args):
    """Read the desk's knowledge (OKF bundle). Never changes anything."""
    b = knowledge.ensure()
    view, arg = args.view, " ".join(args.arg).strip()
    if view in ("search", "show", "for", "inspect") and not arg:
        sys.exit(f"knowledge {view} needs {'a query' if view == 'search' else 'a finding ref' if view == 'for' else 'a path'}")
    concepts = b.concepts() if view not in ("review", "inspect", "kinds", "log") else []
    if view == "kinds":
        return _json({k: {"folder": v["folder"], "effect": v["effect"], "fields": v["fields"],
                          "affects_triage": k in knowledge.SCORING_KINDS} for k, v in knowledge.KINDS.items()})
    if view == "search":
        hits = okf.search(concepts, arg, limit=args.limit)
        if args.json:
            return _json(hits)
        for h in hits:
            _out(f"- {h['path']} ({h['type']}, {h['trust']}{', ' + h['status'] if h['status'] != 'stable' else ''}"
                 f"{', STALE' if h['stale'] else ''}) {h['title']}: {h['description']}\n  {h['snippet']}")
        return _out("" if hits else f"No concept matches {arg!r}. Try fewer words, or `rgtriage knowledge` for the index.")
    if view == "show":
        c = b.read(arg)
        data = {**c.summary(), "meta": c.meta, "body": c.body, "links": c.links, "backlinks": b.backlinks(c.path, concepts),
                "shipped": knowledge.is_shipped(c.path), "effect": knowledge.KINDS.get(c.type, {}).get("effect", ""),
                "affects_triage": c.type in knowledge.SCORING_KINDS and not knowledge.is_shipped(c.path),
                "raw": b.path_of(c.path).read_text(encoding="utf-8", errors="replace")}
        if args.json:
            return _json(data)
        _out(f"# {c.title}\n{c.path} · {c.type} · {data['trust']} · {data['status']}"
             f"{' · STALE since ' + str(c.meta.get('stale_after')) if data['stale'] else ''}"
             f"{' · shipped with RemediGenius-CE' if data['shipped'] else ''}")
        if c.error:
            return _out(f"Unreadable: {c.error}")
        if data["effect"]:
            _out(f"Effect on triage: {data['effect']}")
        ext = c.meta.get("remedigenius")
        if ext:
            _out(f"Settings: {json.dumps(ext, default=str)}")
        for s in c.meta.get("sources") or []:
            if isinstance(s, dict):
                _out(f"Source {s.get('id', '')}: {s.get('title', '')} {s.get('resource', '')}".rstrip())
        _out("\n" + c.body.strip())
        if data["links"] or data["backlinks"]:
            _out(f"\nLinks: {', '.join(data['links']) or '-'}\nLinked from: {', '.join(data['backlinks']) or '-'}")
        return
    if view == "for":
        scan = _latest_or_exit()
        items = knowledge.for_finding(_ref_or_exit(scan, arg), b)
        if args.json:
            return _json(items)
        for k in items:
            _out(f"- {k['path']} ({k['type']}, {k['trust']}): {k['title']} — {k['why']}")
        return
    if view == "gaps":
        gaps = knowledge.gaps(store.load_latest(), b)
        return _json(gaps) if args.json else _out("\n".join(f"- {g}" for g in gaps) or "No knowledge gaps found.")
    if view == "list":
        rows = [c.summary() for c in concepts if not args.type or c.type == args.type]
        return _json(rows) if args.json else _out("\n".join(f"{r['path']}  {r['type']}  {r['trust']}  {r['status']}" for r in rows))
    if view == "graph":
        return _json(b.graph(concepts))
    if view == "validate":
        issues = b.validate(concepts)
        if args.json:
            return _json({"concepts": len(concepts), "errors": sum(i["level"] == "error" for i in issues), "issues": issues})
        _out(f"{len(concepts)} concepts · {sum(i['level'] == 'error' for i in issues)} errors · "
             f"{sum(i['level'] == 'warning' for i in issues)} warnings")
        return _out("\n".join(f"{i['level']:<8} {i['path']}: {i['message']}" for i in issues))
    if view == "review":
        queue = knowledge.review_queue()
        if args.json:
            return _json({"root": str(knowledge.review_root()), "drafts": queue})
        return _out("\n".join(f"- {q['name']}: {q.get('type', '?')} {q.get('title', '')} → {q.get('target', q.get('error'))}"
                              for q in queue) or "The review queue is empty.")
    if view == "inspect":
        return _json(knowledge.inspect_file(arg))
    if view == "log":
        entries = b.log_entries(args.limit)
        return _json(entries) if args.json else _out("\n".join(f"{e['date']}  {e['text']}" for e in entries))
    summary = knowledge.summary(b, concepts)
    eff = knowledge.effective(b)
    if args.json:
        return _json({**summary, "applied": {k: len(eff[k]) for k in ("applications", "accounts", "exceptions", "goals")},
                      "gaps": knowledge.gaps(store.load_latest(), b), "kinds": list(knowledge.KINDS)})
    _out(f"Knowledge bundle (OKF {okf.OKF_VERSION}): {summary['bundle']}")
    _out(f"Organization: {summary['organization']} concepts {summary['by_type'] or ''} · {summary['human_reviewed']} human-reviewed"
         f" · {summary['drafts']} drafts · {len(summary['stale'])} stale")
    _out(f"Shipped with RemediGenius-CE: {summary['shipped']} concepts (remedigenius/: guides, source guides, playbooks)")
    _out(f"Changing priorities now: {len(eff['applications'])} applications, {len(eff['accounts'])} accounts, "
         f"{len(eff['exceptions'])} risk exceptions, {len(eff['goals'])} goals · review queue: {summary['review_queue']}")
    gaps = knowledge.gaps(store.load_latest(), b)
    if gaps:
        _out("Gaps:\n" + "\n".join(f"- {g}" for g in gaps[:5]))
    _out("Start with: remedigenius/guides/how-the-desk-works.md · remedigenius/guides/where-to-look.md · "
         "remedigenius/guides/organization-knowledge.md")
    index = b.root / "index.md"
    if index.exists():
        _out("\n" + okf.split(index.read_text(encoding="utf-8"))[1].strip())


DERIVED = ("knowledge", "owner", "expired_exception", "application")


def rescore() -> dict:
    """Re-rank the stored scan with the current knowledge and decisions; no AWS calls.

    Knowledge approved in the dashboard applies to the board at once instead of at the next scan.
    """
    scan = store.load_latest()
    if not scan:
        return {"findings": 0, "changed_priority": 0}
    profile = config.load()
    known = knowledge.effective()
    before = {f["key"]: f["priority"] for f in scan["findings"]}
    for f in scan["findings"]:
        for key in DERIVED:
            f.pop(key, None)
        if (f.get("decision") or {}).get("knowledge"):
            f.pop("decision")  # a risk exception's decision is re-derived from the current concept
    findings, issues = prioritize.prioritize(scan["findings"], profile, store.load_decisions(), known)
    if scan.get("stored_overflow"):
        # Issue counts were taken before storage was capped: keep them and refresh what the top finding says.
        tops = {f["key"]: f for f in findings}
        for issue in scan["issues"]:
            top = tops.get(issue["top_key"])
            if top:
                issue.update(priority=top["priority"], score=top["score"], reasons=top["reasons"], decision=top.get("decision"),
                             owner=top.get("owner"), knowledge=top.get("knowledge") or [])
        scan["issues"].sort(key=lambda i: (-i["score"], -i["finding_count"]))
    else:
        scan["issues"] = issues
    scan["knowledge"] = knowledge.scan_summary(scan, known)
    store.write_latest(scan)
    write_outputs(scan)
    changed = sum(1 for f in findings if before.get(f["key"]) != f["priority"])
    return {"findings": len(findings), "changed_priority": changed}


def cmd_knowledge_edit(args):
    """Change the knowledge bundle. For the dashboard Knowledge tab and operators; the agent has no access."""
    b = knowledge.ensure()
    if args.action == "seed":
        return _json(knowledge.seed(b))
    if args.action == "reindex":
        knowledge.reindex(b)
        return _json({"reindexed": str(b.root)})
    actor = knowledge.check_actor(args.by or "")
    if args.action == "save":
        if args.fields:
            fields = json.loads(knowledge.inbox_file(args.fields).read_text(encoding="utf-8"))
            meta, body = knowledge.compose(args.kind or fields.pop("kind", ""), fields, actor)
        elif args.file:
            meta, body = okf.parse(knowledge.inbox_file(args.file).read_text(encoding="utf-8"))
        else:
            sys.exit("save needs --file (an OKF concept) or --fields (wizard fields as JSON)")
        result = knowledge.save(meta, body, actor, path=args.path, verify=args.verify, replace=args.replace, b=b)
    elif args.action == "verify":
        result = knowledge.verify(args.path, actor, b)
    elif args.action == "deprecate":
        result = knowledge.deprecate(args.path, actor, args.reason or "", b)
    elif args.action == "remove":
        result = knowledge.remove(args.path, actor, b)
    elif args.action == "import":
        if not args.file or not args.name:
            sys.exit("import needs --file (converted markdown) and --name (original file name)")
        text = knowledge.inbox_file(args.file).read_text(encoding="utf-8", errors="replace")
        result = knowledge.import_reference(text, args.name, actor, sha256=args.sha256 or "", converter=args.converter or "",
                                            title=args.title or "", b=b)
    else:
        sys.exit(f"unknown action {args.action}")
    if args.action != "import":
        try:
            result["rescored"] = rescore()
        except Exception as exc:  # the change is saved; the board catches up at the next scan
            result["rescored"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    _json(result)


def _improve_file(raw: str) -> Path:
    """Files the improvement commands may read: the improvement folder and approved/shipped skill folders."""
    path = Path(raw).expanduser()
    if path.is_symlink():
        sys.exit("refusing a symbolic link")
    resolved = path.resolve()
    roots = [Path(p) for p in os.environ.get("RGTRIAGE_IMPROVE_DIR", "").split(os.pathsep) if p]
    roots += [Path("/opt/data/rg-improve"), config.home() / "rg-improve"]
    if any(r.resolve() in resolved.parents or r.resolve() == resolved for r in roots if r.exists()):
        return resolved
    if "skills" in resolved.parts and "profiles" in resolved.parts:
        return resolved
    sys.exit(f"{raw} is not in the improvement folder or a profile's skills folder")


def _grade_run(run_dir: Path, cases: dict | None = None):
    from .improve import evals, grade
    cases = cases or evals.load_cases()
    meta = evals.ensure(cases["fixture"])
    by_id = {t["id"]: t for t in evals.tasks(meta, cases)}
    paths, refs = evals.known_paths(meta["home"]), evals.known_refs(meta["home"])
    grades = []
    for f in sorted((run_dir / "cases").glob("*.json")):
        item = json.loads(f.read_text(encoding="utf-8"))
        task = by_id.get(item.get("case"))
        if task:
            grades.append(grade.grade(task, item.get("answer", ""), item.get("trajectory"), paths, refs))
    return grades


def cmd_improve(args):
    """Offline improvement: evaluation, grading, the security gate, trace analysis and consolidation. Never calls a model."""
    from .improve import consolidate, evals, gate, hints, traces
    action = args.action
    if action == "suite":
        result = evals.suite()
        if args.json:
            return _json(result)
        _out(f"Deterministic desk checks: {result['passed']}/{result['total']} passed (fixture {result['fixture']})")
        for r in result["checks"]:
            _out(f"  {'ok  ' if r['ok'] else 'FAIL'} {r['id']}" + ("" if r["ok"] else f": {'; '.join(r['problems'])}"))
        return
    if action == "tasks":
        cases = evals.load_cases()
        meta = evals.ensure(cases["fixture"])
        return _json({"fixture": meta["name"], "tasks": [{k: t.get(k) for k in ("id", "split", "critical", "tags", "prompt", "skill")}
                                                       for t in evals.tasks(meta, cases)]})
    if action == "exec":
        meta = evals.ensure(evals.load_cases()["fixture"])
        rest = [a for a in args.rest if a != "--"]
        result = evals.exec_tool(meta, rest)
        if result["rc"]:
            sys.exit(result["stderr"][-1500:] or f"exit {result['rc']}")
        return _out(result["stdout"])
    if action == "grade-run":
        grades = _grade_run(_improve_file(args.run))
        return _json({"summary": gate.summarize(grades), "grades": grades})
    if action == "gate":
        baseline = _grade_run(_improve_file(args.baseline))
        candidate = _grade_run(_improve_file(args.candidate))
        text = _improve_file(args.skill_file).read_text(encoding="utf-8")
        base = _improve_file(args.base_skill_file).read_text(encoding="utf-8") if args.base_skill_file else ""
        suite = evals.suite()
        okf_errors = sum(i["level"] == "error" for i in knowledge.bundle().validate())
        return _json(gate.decide(baseline, candidate, text, base, suite=suite, okf_errors=okf_errors))
    if action == "lint":
        text = _improve_file(args.skill_file).read_text(encoding="utf-8")
        base = _improve_file(args.base_skill_file).read_text(encoding="utf-8") if args.base_skill_file else ""
        return _json(gate.lint(text, base))
    if action == "hint":
        f = _ref_or_exit(_latest_or_exit(), args.rest[0] if args.rest else "")
        practices = knowledge.practices_for(f.get("control_id") or "", knowledge.bundle().concepts())
        return _json(hints.guidance(f, practices))
    records = traces.load(args.days)
    if action == "traces":
        return _json(traces.summary(records))
    if action == "failures":
        return _json(traces.failures(records))
    if action == "lessons":
        return _json(traces.lessons(records))
    if action == "gaps":
        return _json(traces.gaps(records))
    if action == "cases-mined":
        return _json(traces.case_candidates(records))
    if action == "consolidate":
        skills_dir = _improve_file(args.skills_dir) if args.skills_dir else Path(__file__).resolve().parents[1] / "profiles/remedigenius/skills"
        items = (consolidate.skills_report(skills_dir) if skills_dir.is_dir() else []) + consolidate.knowledge_report()
        return _json(items)
    sys.exit(f"unknown improve action {action}")


def cmd_playbook(args):
    if not args.name:
        _out("\n".join(playbooks.names()))
    else:
        _out(playbooks.load(args.name))


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(prog="rgtriage", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a triage profile from the current AWS identity")
    p.add_argument("--profile"); p.add_argument("--region"); p.add_argument("--name"); p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)
    sub.add_parser("doctor", help="check access and enabled sources").set_defaults(func=cmd_doctor)
    p = sub.add_parser("scan", help="collect and prioritize findings")
    p.add_argument("--sources", help="comma list: " + ",".join(config.ALL_SOURCES))
    p.add_argument("--limit", type=int, default=5); p.add_argument("--json", action="store_true"); p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_scan)
    p = sub.add_parser("digest", help="print the latest attention board")
    p.add_argument("--limit", type=int, default=5); p.add_argument("--all", action="store_true", help="expand P3/P4")
    p.set_defaults(func=cmd_digest)
    p = sub.add_parser("list", help="list prioritized findings")
    p.add_argument("--priority"); p.add_argument("--source"); p.add_argument("--category"); p.add_argument("--account")
    p.add_argument("--issues", action="store_true", help="grouped issues instead of findings")
    p.add_argument("--all", action="store_true", help="include closed decisions"); p.add_argument("--limit", type=int, default=30)
    p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("show", help="show one finding"); p.add_argument("ref"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("fix", help="IaC location + remediation playbook for a finding")
    p.add_argument("ref"); p.add_argument("--iac", action="append", help="IaC repo path (repeatable)")
    p.add_argument("--excerpts", type=int, default=2); p.set_defaults(func=cmd_fix)
    p = sub.add_parser("decide", help="record an operator decision")
    p.add_argument("ref"); p.add_argument("status", choices=store.DECISION_STATUSES); p.add_argument("--reason", required=True)
    p.add_argument("--by", default="operator"); p.add_argument("--issue", action="store_true", help="apply to every finding in the issue")
    p.set_defaults(func=cmd_decide)
    p = sub.add_parser("report", help="write the HTML report"); p.add_argument("--open", action="store_true"); p.set_defaults(func=cmd_report)
    p = sub.add_parser("watch", help="scan; print only new urgent findings (empty output = nothing new)")
    p.add_argument("--min-priority", default="P2", choices=PRIORITY_ORDER); p.set_defaults(func=cmd_watch)
    p = sub.add_parser("aws", help="one guarded read-only AWS API call")
    p.add_argument("service"); p.add_argument("operation"); p.add_argument("--params"); p.add_argument("--account")
    p.add_argument("--region"); p.add_argument("--max-chars", type=int, default=12000); p.set_defaults(func=cmd_aws)
    p = sub.add_parser("validate", help="terraform init/validate/fmt a module copy with proposed files overlaid")
    p.add_argument("--module", required=True, help="Terraform module folder the change belongs to")
    p.add_argument("--file", action="append", required=True, help="proposed file, optionally =target-name (repeatable)")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("serve", help="desk API on a Unix socket for the containerized agent; checkpoints state")
    p.add_argument("--socket", required=True)
    p.add_argument("--durable", default="", help="s3://bucket/prefix or a folder for durable checkpoints")
    p.add_argument("--home", action="append", default=[], help="name=path to checkpoint (repeatable)")
    p.add_argument("--every", type=int, default=120, help="checkpoint interval in seconds")
    p.add_argument("--spot", action="store_true", help="watch for EC2 Spot interruption notices")
    p.add_argument("--scan-every-hours", type=float, default=0, help="run scheduled scans (0 = off)")
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("durable", help="checkpoint or restore state homes (s3://bucket/prefix or a folder)")
    p.add_argument("action", choices=["checkpoint", "restore"])
    p.add_argument("--url", required=True)
    p.add_argument("--home", action="append", required=True, help="name=path (repeatable)")
    p.add_argument("--owner", help="uid:gid to own restored files")
    p.add_argument("--force", action="store_true", help="checkpoint: start a new lineage even if it diverges")
    p.set_defaults(func=cmd_durable)
    p = sub.add_parser("onboarding", help="account coverage and the one-time setup for accounts not read yet")
    p.add_argument("--json", action="store_true"); p.set_defaults(func=cmd_onboarding)
    p = sub.add_parser("playbook", help="list or print remediation playbooks"); p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_playbook)
    p = sub.add_parser("knowledge", help="read the desk's knowledge (OKF bundle)")
    p.add_argument("view", nargs="?", default="overview", choices=KNOWLEDGE_VIEWS)
    p.add_argument("arg", nargs="*", help="query (search), concept path (show), finding ref (for), file (inspect)")
    p.add_argument("--type", help="list: only this concept type")
    p.add_argument("--limit", type=int, default=10); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_knowledge)
    p = sub.add_parser("knowledge-edit", help="change the knowledge bundle (dashboard and operators only)")
    p.add_argument("action", choices=["save", "verify", "deprecate", "remove", "import", "seed", "reindex"])
    p.add_argument("--by", help="reviewer, human:<name>")
    p.add_argument("--file", help="OKF concept (save) or converted markdown (import), inside the knowledge inbox")
    p.add_argument("--fields", help="wizard fields as JSON, inside the knowledge inbox"); p.add_argument("--kind")
    p.add_argument("--path", help="concept path in the bundle")
    p.add_argument("--verify", action="store_true", help="save: record the reviewer's confirmation")
    p.add_argument("--replace", action="store_true", help="save: overwrite an existing concept")
    p.add_argument("--reason"); p.add_argument("--name", help="import: original file name")
    p.add_argument("--sha256"); p.add_argument("--converter"); p.add_argument("--title")
    p.set_defaults(func=cmd_knowledge_edit)
    p = sub.add_parser("improve", help="offline improvement: evaluation, grading, gate, traces, consolidation (no model calls)")
    p.add_argument("action", choices=["suite", "tasks", "exec", "grade-run", "gate", "lint", "hint", "traces", "failures",
                                      "lessons", "gaps", "cases-mined", "consolidate"])
    p.add_argument("rest", nargs="*", help="exec: rgtriage arguments after --; hint: finding ref")
    p.add_argument("--run"); p.add_argument("--baseline"); p.add_argument("--candidate")
    p.add_argument("--skill-file"); p.add_argument("--base-skill-file"); p.add_argument("--skills-dir")
    p.add_argument("--days", type=int, default=30); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_improve)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    except okf.OKFError as exc:
        sys.exit(f"knowledge: {exc}")


if __name__ == "__main__":
    main()
