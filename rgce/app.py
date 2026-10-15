import secrets
import io
import json
import re
import zipfile
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from . import core, runtime, documents, knowledge
from .store import Store


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindingRequest(Strict):
    assessment_id: str
    row_id: str


class CompareRequest(Strict):
    before: str
    after: str


class DraftRequest(Strict):
    assessment_id: str
    text: str = Field(min_length=1, max_length=10000)
    author: str = Field(min_length=1, max_length=120)
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class ApprovalRequest(Strict):
    draft_id: str
    expected_hash: str
    reviewer: str = Field(min_length=1, max_length=120)


class ConceptRequest(Strict):
    concept_id: str
    document: str = Field(min_length=1, max_length=100000)
    author: str
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    base_version: str | None = None


class SourceReplacement(Strict):
    old_id: str
    new_id: str
    reviewer: str


class Withdrawal(Strict):
    version_id: str
    reviewer: str
    reason: str


class ResourceContext(Strict):
    assessment_id: str
    resource: str
    values: dict[str, str]
    reviewer: str


class SourcePlan(Strict):
    source: str
    role_arn: str
    region: str
    location: str = ''
    hours: int = Field(default=1, ge=1, le=24)
    max_calls: int = Field(default=5, ge=1, le=20)


class WorkspaceExport(Strict):
    record_ids: list[str] = Field(min_length=1, max_length=50)


class HermesPrepare(WorkspaceExport):
    question: str = Field(min_length=1, max_length=4000)
    followup_job: str | None = None


class HermesStart(Strict):
    preparation_id: str
    consent: bool = False


class SimpleGuidance(Strict):
    statement: str = Field(min_length=1, max_length=80000)
    title: str = ''
    scope: dict[str, str] | None = None
    baseline_id: str | None = None
    source_ids: list[str] | None = None
    revision_id: str | None = None
    review_date: str | None = None
    author: str = 'Local operator'
    ai_assisted: bool = False


def create_app(home=None):
    store = Store(home)
    from .hermes_jobs import HermesJobs
    hermes = HermesJobs(store)
    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        async def reconcile():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(hermes.runs)
                except (OSError, ValueError):
                    pass  # Keep failed durable writes fail-closed; surface via run endpoint.
                try:
                    await asyncio.wait_for(stop.wait(), 2)
                except asyncio.TimeoutError:
                    pass
        task = asyncio.create_task(reconcile())
        yield
        stop.set()
        await task
    app = FastAPI(title="RemediGenius Community", version="0.1.0rc10", docs_url=None, redoc_url=None, lifespan=lifespan)
    token = secrets.token_urlsafe(32)
    static = Path(__file__).with_name("static")

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "Loopback host required"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != f"http://{request.headers.get('host')}":
            return JSONResponse({"detail": "Cross-origin access denied"}, status_code=403)
        if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
            return JSONResponse({"detail": "Same-origin access only"}, status_code=403)
        if request.method not in ("GET", "HEAD") and not secrets.compare_digest(request.headers.get("x-rgce-token", ""), token):
            return JSONResponse({"detail": "Local session token required"}, status_code=403)
        if request.method not in ("GET", "HEAD"):
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 10_000_000:
                    return JSONResponse({"detail": "10MB request limit"}, status_code=413)
            request._body = bytes(data)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def value_error(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/api/session")
    def session():
        return {"token": token, "version": "0.1.0rc10"}

    @app.get('/api/hermes')
    def hermes_status():
        return {'runtime': hermes.status(), 'runs': hermes.runs()}

    @app.post('/api/hermes/prepare')
    def hermes_prepare(request: HermesPrepare):
        record = hermes.prepare(request.record_ids, request.question, request.followup_job)
        # File contents remain reviewable in the durable record, not duplicated here.
        return {'id': record['id'], **{k: v for k, v in record['body'].items() if k != 'files'},
                'file_count': len(record['body']['files'])}

    @app.post('/api/hermes/start')
    def hermes_start(request: HermesStart):
        return hermes.start(request.preparation_id, request.consent)

    @app.get('/api/hermes/runs/{job}')
    def hermes_run(job: str):
        return hermes.get(job)

    @app.post('/api/hermes/runs/{job}/cancel')
    def hermes_cancel(job: str):
        return hermes.cancel(job)

    @app.post("/api/onboarding/plan")
    def source_plan(request: SourcePlan):
        from .onboarding import workspace_plan
        return workspace_plan(request.model_dump(), store.home, 's3' if store.objects else 'local')

    @app.post("/api/workspace/export")
    def workspace_export(request: WorkspaceExport):
        from .workspace import export_workspace
        result = export_workspace(store, request.record_ids)
        result['download_url'] = '/api/workspace/download/' + Path(result['folder']).name
        return result

    @app.get('/api/workspace/download/{export_id}')
    def workspace_download(export_id: str):
        from .workspace import verify_workspace
        if not re.fullmatch(r'[a-f0-9]{32}', export_id):
            raise ValueError('Invalid export identifier')
        base = store.home / 'exports'
        folder = base / export_id
        if base.is_symlink() or folder.is_symlink() or not folder.is_dir():
            raise ValueError('Export not found')
        verify_workspace(folder)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        names = list(manifest['files']) + ['manifest.json']
        if len(names) > 2001 or sum((folder / n).stat().st_size for n in names) > 33_000_000:
            raise ValueError('Export exceeds download limit')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                # Hash verification above confines each member to this export.
                archive.write(folder / name, name)
        return Response(output.getvalue(), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="remedigenius-investigation.zip"'})

    @app.get("/api/state")
    def state():
        return {"storage": {"mode": "s3" if store.objects else "local", "notice": "Records saved to your S3 workspace; this machine holds a rebuildable cache. One active writer only." if store.objects else "Saved in this workspace's local data directory or Docker volume. Keep a backup before retiring storage."},
                "capabilities": core.capabilities(store), "assessments": store.list("assessment"),
                "evidence": [{"id": e["id"], "body": {k: v for k, v in e["body"].items() if k != "facts"}} for e in store.list("evidence")],
                "knowledge": store.list("knowledge_approval"), "drafts": store.list("knowledge_draft"),
                "annotations": store.list("ai_annotation"), "runtime": runtime.connection(store.home)}

    @app.get("/api/records/{record_id}")
    def record(record_id: str):
        return store.get(record_id)

    @app.post("/api/demo")
    def demo():
        return core.demo(store)

    @app.post("/api/import")
    def ingest(payload: dict):
        record = core.ingest(store, payload)
        return {"evidence": record, "assessment": core.assess(store, record["id"]) if payload["adapter"] not in core.CONTEXT_ADAPTERS else None}

    @app.post("/api/investigate")
    def investigate(a: FindingRequest):
        return core.investigation(store, a.assessment_id, a.row_id)

    @app.post("/api/proposal")
    def proposal(a: FindingRequest):
        result = core.proposal(store, a.assessment_id, a.row_id)
        receipt = store.put("knowledge_use", result["knowledge_context"])
        result["knowledge_receipt_id"] = receipt["id"]
        return result

    @app.post("/api/reassess")
    def reassess(a: CompareRequest):
        return core.compare(store, a.before, a.after)

    @app.post("/api/knowledge/draft")
    def draft(a: DraftRequest):
        return core.draft_knowledge(store, a.assessment_id, a.text, a.author, a.source_ids)

    @app.get("/api/documents")
    def list_documents(query: str = "", topic: str = "", scope: str = ""):
        return documents.search(store, query, topic, scope)

    @app.post("/api/documents")
    async def upload_document(request: Request, name: str, topic: str = "other", scope: str = "organization", owner: str = ""):
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(documents.intake, store, name, await request.body(), topic, scope, owner)

    @app.post("/api/knowledge/approve")
    def approve(a: ApprovalRequest):
        return core.approve_knowledge(store, a.draft_id, a.expected_hash, a.reviewer)

    @app.post("/api/guidance/draft")
    def simple_guidance(a: SimpleGuidance):
        return knowledge.simple_draft(store, **a.model_dump())

    @app.get("/api/guidance/ai-review")
    def ai_review(source_id: str | None = None, concept_id: str | None = None):
        return knowledge.review_brief(store, source_id, concept_id)

    @app.post("/api/guidance/review-files")
    def review_files():
        return knowledge.review_files(store)

    @app.get("/api/concepts")
    def concepts():
        return {"concepts": knowledge.catalog(store), "drafts": knowledge.records(store, "concept_draft"), "published_draft_ids": [r["body"]["draft_id"] for r in knowledge.records(store, "concept_publication")]}

    @app.get("/api/concepts/receipts")
    def knowledge_receipts():
        return {"receipts": knowledge.use_history(store), "limit": 100}

    @app.post("/api/concepts/draft")
    def concept_draft(a: ConceptRequest):
        return knowledge.draft(store, **a.model_dump())

    @app.post("/api/concepts/approve")
    def concept_approve(a: ApprovalRequest):
        return knowledge.publish(store, a.draft_id, a.expected_hash, a.reviewer)

    @app.post("/api/concepts/withdraw")
    def concept_withdraw(a: Withdrawal):
        return knowledge.withdraw(store, **a.model_dump())

    @app.post("/api/concepts/replace-source")
    def replace_source(a: SourceReplacement):
        return knowledge.replace_source(store, **a.model_dump())

    @app.post("/api/concepts/context")
    def resource_context(a: ResourceContext):
        return knowledge.mapping(store, **a.model_dump())

    @app.get("/api/concepts/export/{record_id}")
    def export_concept(record_id: str):
        return {"markdown": knowledge.export_okf(store, record_id)}

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
