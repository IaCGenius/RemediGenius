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
"""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import datetime, timezone

from botocore.exceptions import BotoCoreError, ClientError

from . import __version__, accounts, aws, collect, config, digest, iac, playbooks, prioritize, store

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
    findings, _ = prioritize.prioritize(findings, profile, store.load_decisions())
    scan = {
        "version": __version__, "scanned_at": collect.now_iso(),
        "profile": {"name": profile["name"], "accounts": [{"name": a["name"], "account_id": a.get("account_id"),
                    "criticality": a["criticality"]} for a in profile["accounts"]], "goals": [g.get("text") for g in profile["goals"]]},
        "findings": findings, "coverage": coverage, "onboarding": onboarding,
    }
    store.save_onboarding(onboarding, profile)
    store.mark_changes(scan)
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
    if f.get("decision"):
        _out(f"Decision: {json.dumps(f['decision'])}")
    if f["remediation"].get("text") or f["remediation"].get("url"):
        _out(f"\nAWS remediation: {f['remediation'].get('text', '')} {f['remediation'].get('url', '')}")
    _out(f"Console: {f.get('console_url')}")
    _out(f"Playbooks: {', '.join(playbooks.select(f))}  (`rgtriage fix {f['key']}`)")


def cmd_fix(args):
    scan = _latest_or_exit()
    f = _ref_or_exit(scan, args.ref)
    paths = args.iac or config.load().get("iac_paths", [])
    _out(f"# Fix context for {f['key']}: {f['title']}")
    _out(f"{f['priority']} · {f['product']} {f['severity']} · control/type {f.get('control_id') or f.get('type')} · "
         f"resource {f['resource'].get('type')} `{f['resource'].get('id')}` · account {f['account']} / {f['region']}")
    if f["remediation"].get("url"):
        _out(f"AWS remediation doc: {f['remediation']['url']}")
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


def cmd_aws(args):
    profile = config.load()
    known = profile["accounts"] + store.discovered_accounts(profile)
    account = next((a for a in known if args.account in (None, a["name"], a.get("account_id"))), None)
    if not account:
        sys.exit(f"Unknown account {args.account}")
    region = args.region or account["regions"][0]
    op = args.operation.replace("-", "_")
    if not aws.is_read_operation(aws.snake_to_pascal(op)):
        sys.exit(f"Refused: {op} is not a read-only operation (allowed prefixes: describe/get/list/batch_get/lookup/search).")
    params = json.loads(args.params) if args.params else {}
    try:
        client = aws.client(aws.session_for(account, region), args.service, region)
        result = getattr(client, op)(**params)
    except AttributeError:
        sys.exit(f"{args.service} has no operation {op}")
    except (ClientError, BotoCoreError, aws.WriteBlocked) as exc:
        sys.exit(f"AWS error: {exc}")
    result.pop("ResponseMetadata", None)
    text = json.dumps(result, indent=1, default=str)
    if len(text) > args.max_chars:
        text = text[:args.max_chars] + f"\n... truncated ({len(text)} chars; narrow the query or raise --max-chars)"
    _out(text)


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

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except FileNotFoundError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
