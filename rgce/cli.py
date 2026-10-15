import argparse
import json
import sys
from pathlib import Path
from . import core, runtime
from .store import Store


def collected_payload(args):
    if args.command == 'collect-source':
        from .onboarding import collect
        spec = {k: getattr(args, k) for k in ('source', 'role_arn', 'region', 'location', 'hours', 'max_calls')}
        return collect(spec, consent=args.consent, check=args.check, profile=args.profile, external_id=args.external_id)
    from .adapters import collect_aws
    return collect_aws(args.adapter, args.role_arn, args.external_id, args.regions, args.max_calls, args.profile, args.group_ids)


def main():
    parser = argparse.ArgumentParser(description="RemediGenius CE: collect, understand, propose, reassess")
    parser.add_argument("--home", help="Local evidence directory (default RGCE_HOME or ~/.rgce)")
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser('migrate-s3', help='Explicitly copy local records and originals to a dedicated S3 prefix; retain source')
    migrate.add_argument('--bucket', required=True)
    migrate.add_argument('--prefix', required=True)
    migrate.add_argument('--consent', action='store_true')
    serve = sub.add_parser("serve", help="Start the local console; does not load demo automatically")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--container-bind", action="store_true", help="Bind inside a container; publish its port on host loopback only")
    sub.add_parser("demo", help="Load synthetic evidence; no AWS or model calls")
    imp = sub.add_parser("import", help="Import an evidence envelope (10MB maximum)")
    imp.add_argument("file")
    ai = sub.add_parser("import-ai", help="Save external model output as a separately labeled, unreviewed annotation")
    ai.add_argument("file")
    repo = sub.add_parser("repo", help="Read committed Terraform files; no execution or network")
    repo.add_argument("path")
    docs = sub.add_parser("documents", help="Copy a file or a flat folder into the unreviewed knowledge library")
    docs.add_argument("path")
    docs.add_argument("--topic", default="other")
    docs.add_argument("--scope", default="organization")
    docs.add_argument("--owner", default="")
    collect = sub.add_parser("collect-aws", help="Assume the scoped community role and read AWS")
    collect.add_argument("adapter", choices=["sg", "securityhub-asff"])
    collect.add_argument("--role-arn", required=True)
    collect.add_argument("--external-id")
    collect.add_argument("--regions", nargs="+", required=True)
    collect.add_argument("--max-calls", type=int, default=50)
    collect.add_argument("--profile")
    collect.add_argument("--group-ids", nargs="+", help="Optional exact SG IDs; limits collection to selected resources")
    collect.add_argument('--output', help='Write an importable JSON file instead of opening a workspace; refuses overwrite')
    for name in ("plan-source", "collect-source"):
        source = sub.add_parser(name, help="Review or explicitly run a bounded existing-source read")
        source.add_argument("source", choices=["cloudtrail-events", "cloudwatch-logs", "s3-object"])
        source.add_argument("--role-arn", required=True)
        source.add_argument("--region", required=True)
        source.add_argument("--location", default="")
        source.add_argument("--hours", type=int, default=1)
        source.add_argument("--max-calls", type=int, default=5)
        source.add_argument("--profile")
        source.add_argument("--external-id")
        source.add_argument("--consent", action="store_true")
        source.add_argument("--check", action="store_true")
        if name == 'collect-source':
            source.add_argument('--output', help='Write an importable JSON file instead of opening a workspace; refuses overwrite')
    ls = sub.add_parser("list", help="List local record IDs without source contents")
    ls.add_argument("--kind", choices=["assessment", "evidence"], default="assessment")
    rec = sub.add_parser("record", help="Read one verified local record as JSON")
    rec.add_argument("id")
    exp = sub.add_parser("export-workspace", help="Export selected evidence/assessments for humans and skills; no MCP needed")
    exp.add_argument("ids", nargs="+")
    verify = sub.add_parser("verify-workspace", help="Check a generated folder against its file manifest")
    verify.add_argument("path")
    for command in ("investigate", "proposal"):
        read = sub.add_parser(command, help="Read a finding with resolved knowledge")
        read.add_argument("assessment_id")
        read.add_argument("row_id")
    compare = sub.add_parser("reassess", help="Compare two pinned assessments")
    compare.add_argument("before")
    compare.add_argument("after")
    sub.add_parser("connect", help="Print MCP connection configuration; does not modify Hermes")
    sub.add_parser("mcp", help="Run the read-only stdio MCP server")
    args = parser.parse_args()
    try:
        if args.command in ('collect-source', 'collect-aws') and args.output:
            path = Path(args.output)
            if path.exists() or not path.parent.is_dir():
                raise ValueError('Choose a new output filename in an existing directory')
            payload = collected_payload(args)
            encoded = json.dumps(payload, ensure_ascii=False, indent=2)
            if len(encoded.encode('utf-8')) > 10_000_000:
                raise ValueError('Export exceeds the 10MB import limit; narrow the selected resources or read budget')
            # Explicit selected-data export; never inherit the console's storage
            # credentials or open another S3 writer just to collect on a workstation.
            with path.open('x', encoding='utf-8') as output:
                output.write(encoded)
            print(json.dumps({'status':'exported', 'file':str(path.resolve()),
                'coverage':payload.get('coverage','unknown'), 'errors':payload.get('errors',[]),
                'notice':'Review this file, then use Import evidence in your console. Imported coverage is unverified; no model call.'}, indent=2))
            return
        store = Store(args.home)
        if args.command == 'migrate-s3':
            if not args.consent:
                raise ValueError('Review destination and stop other writers, then supply --consent')
            from .object_storage import ObjectStorage, migrate_local
            print(json.dumps(migrate_local(store, ObjectStorage(args.bucket, args.prefix)), indent=2))
            return
        if args.command == "serve":
            import uvicorn
            from .app import create_app
            uvicorn.run(create_app(store.home), host="0.0.0.0" if args.container_bind else "127.0.0.1", port=args.port)
            return
        if args.command == "mcp":
            from .mcp_server import create_server
            create_server(store).run(transport="stdio")
            return
        if args.command in ("list", "record", "export-workspace", "verify-workspace", "investigate", "proposal", "reassess"):
            from .workspace import export_workspace, verify_workspace
            if args.command == "list":
                result = [{"id": r["id"], "kind": r["kind"], "adapter": r["body"]["adapter"], "observed_at": r["body"]["observed_at"]} for r in store.list(args.kind)]
            elif args.command == "record": result = store.get(args.id)
            elif args.command == "export-workspace": result = export_workspace(store, args.ids)
            elif args.command == "verify-workspace": result = verify_workspace(args.path)
            elif args.command == "reassess": result = core.compare(store, args.before, args.after)
            else:
                fn = core.investigation if args.command == "investigate" else core.proposal
                result = fn(store, args.assessment_id, args.row_id)
            print(json.dumps(result, indent=2))
            return
        if args.command == "demo":
            result = core.demo(store)
        elif args.command == "connect":
            result = runtime.connection(store.home)
        elif args.command in ("import", "import-ai"):
            path = Path(args.file)
            if path.stat().st_size > 10_000_000:
                raise ValueError("10MB import limit")
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if args.command == "import-ai":
                required = {"assessment_id", "row_id", "text", "model", "citations"}
                if set(payload) != required:
                    raise ValueError("AI import requires exactly: " + ", ".join(sorted(required)))
                result = core.annotate(store, **payload)
            else:
                e = core.ingest(store, payload)
                result = core.assess(store, e["id"]) if e["body"]["adapter"] not in core.CONTEXT_ADAPTERS else e
        elif args.command in ("plan-source", "collect-source"):
            from .onboarding import workspace_plan
            spec = {k: getattr(args, k) for k in ("source", "role_arn", "region", "location", "hours", "max_calls")}
            if args.command == "plan-source":
                print(json.dumps(workspace_plan(spec, store.home, 's3' if store.objects else 'local'), indent=2))
                return
            payload = collected_payload(args)
            result = core.ingest(store, payload, authority="collector")
            result["notice"] = "Saved source evidence. Coverage: " + payload["coverage"] + "; errors: " + json.dumps(payload["errors"]) + ". Review Evidence library or retrieve with your MCP agent."
        elif args.command == "documents":
            from .documents import intake, TYPES
            path = Path(args.path)
            paths = sorted(path.iterdir()) if path.is_dir() else [path]
            paths = [p for p in paths if p.is_file() and not p.is_symlink() and p.suffix.lower() in TYPES]
            if not paths or len(paths) > 50:
                raise ValueError("Select a supported file or a flat folder with 1..50 supported files; subfolders are not traversed")
            records = []
            for p in paths:
                if p.stat().st_size > 5_000_000:
                    raise ValueError(f"{p.name} exceeds 5MB; earlier files, if any, remain imported")
                records.append(intake(store, p.name, p.read_bytes(), args.topic, args.scope, args.owner, "file_or_folder"))
            result = {"notice": f"Imported {len(records)} unreviewed document sources. Originals left in place."}
        elif args.command == "repo":
            from .adapters import repository_snapshot
            result = core.ingest(store, repository_snapshot(args.path))
        else:
            payload = collected_payload(args)
            e = core.ingest(store, payload, authority="collector")
            result = core.assess(store, e["id"])
        # Source facts are not printed by default; inspect explicitly in the console.
        if args.command == "connect":
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"status": "saved", "record_id": result.get("id"),
                "assessment_ids": [result[k]["id"] for k in ("before", "after") if k in result],
                "home": str(store.home), "notice": result.get("notice")}, indent=2))
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
