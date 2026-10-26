"""The desk's knowledge: one Open Knowledge Format (OKF) bundle per installation.

Two parts live in the same bundle:
- `remedigenius/` — shipped with RemediGenius Community Edition (source guides, where to look, playbooks).
  Code-owned: refreshed on every start, never edited in place.
- everything else — the organization's own knowledge (applications, accounts, teams, risk exceptions,
  goals, policies, runbooks, references), added through the dashboard Knowledge tab or `rgtriage knowledge-edit`.

Only organization concepts that a person has reviewed (OKF trust tier `human-reviewed`, status `stable`)
change prioritization; every effect is cited by concept path in the finding's reasons. Drafts from the agent
or from document import wait in the review queue until a person approves them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import __version__, config, okf, playbooks

SHIPPED = "remedigenius"
SEED_DIR = Path(__file__).parent / "knowledge_base"
ACTOR = re.compile(r"^human:[A-Za-z0-9._@+-]{1,64}$")
CRITICALITIES = tuple(config.CRITICALITY_POINTS)

# Organization concept kinds. `fields` drive the dashboard wizard; `effect` is what the kind changes.
KINDS = {
    "Application": {
        "folder": "applications",
        "effect": "Resources carrying the application's tags get its criticality; findings show its owner.",
        "fields": [
            {"name": "title", "label": "Application name", "required": True},
            {"name": "description", "label": "What it does, in one sentence", "required": True},
            {"name": "match_tags", "label": "Resource tags that identify it", "kind": "tags", "required": True,
             "help": "For example app=payments. Every listed tag must match."},
            {"name": "criticality", "label": "Business criticality", "kind": "criticality", "required": True},
            {"name": "data", "label": "Data it handles", "help": "For example card data, customer PII, none"},
            {"name": "owner", "label": "Owning team", "kind": "team"},
            {"name": "body", "label": "Notes for the desk", "kind": "text",
             "help": "Architecture, dependencies, what an outage or breach would mean."},
        ]},
    "Account": {
        "folder": "accounts",
        "effect": "Every finding in the AWS account gets this criticality (unless an application concept is more specific).",
        "fields": [
            {"name": "account_id", "label": "AWS account id (12 digits)", "required": True},
            {"name": "title", "label": "Account name", "required": True},
            {"name": "description", "label": "What runs there", "required": True},
            {"name": "environment", "label": "Environment", "kind": "choice",
             "choices": ["production", "staging", "development", "sandbox", "security", "shared-services"]},
            {"name": "criticality", "label": "Business criticality", "kind": "criticality", "required": True},
            {"name": "owner", "label": "Owning team", "kind": "team"},
            {"name": "body", "label": "Notes for the desk", "kind": "text"},
        ]},
    "Team": {
        "folder": "teams",
        "effect": "Named as owner on findings for its applications and accounts; tells the desk whom to involve.",
        "fields": [
            {"name": "title", "label": "Team name", "required": True},
            {"name": "description", "label": "What the team owns", "required": True},
            {"name": "contact", "label": "How to reach them", "help": "Channel, email list or on-call rotation"},
            {"name": "escalation", "label": "Escalation for P1 findings"},
            {"name": "body", "label": "Notes for the desk", "kind": "text"},
        ]},
    "Risk Exception": {
        "folder": "exceptions",
        "effect": "Matching findings are treated as accepted risk until the exception expires; then they come back.",
        "fields": [
            {"name": "title", "label": "Short name", "required": True},
            {"name": "description", "label": "Why the risk is accepted", "required": True},
            {"name": "control_id", "label": "Control id (for example S3.8)",
             "help": "Fill at least one of control id, finding type or resource."},
            {"name": "finding_type", "label": "Finding type (GuardDuty/Inspector type or title)"},
            {"name": "resource", "label": "Resource id or ARN (exact)"},
            {"name": "account_id", "label": "Only in this AWS account (optional)"},
            {"name": "expires", "label": "Expires on (YYYY-MM-DD)", "kind": "date", "required": True},
            {"name": "approved_by", "label": "Approved by", "required": True},
            {"name": "body", "label": "Compensating controls and conditions", "kind": "text"},
        ]},
    "Security Goal": {
        "folder": "goals",
        "effect": "Matching findings get extra priority points, cited with the goal.",
        "fields": [
            {"name": "title", "label": "Goal in plain words", "required": True},
            {"name": "description", "label": "Why it matters this quarter", "required": True},
            {"name": "resource_types", "label": "Resource types (comma list)",
             "help": "For example AwsS3Bucket, AwsRdsDbInstance, AwsIamRole"},
            {"name": "categories", "label": "Finding categories (comma list)",
             "help": "threat, vulnerability, exposure, posture, operational, health, data"},
            {"name": "signals", "label": "Signals (comma list)",
             "help": "public_exposure, identity_risk, root_usage, exploit_available, detection_gap"},
            {"name": "points", "label": "Extra points (1-15)", "kind": "number"},
            {"name": "body", "label": "Notes", "kind": "text"},
        ]},
    "Policy": {"folder": "policies", "effect": "Context for investigations and fix proposals (no score change).",
               "fields": [{"name": "title", "label": "Policy name", "required": True},
                          {"name": "description", "label": "One-sentence summary", "required": True},
                          {"name": "body", "label": "The rule, in your words", "kind": "text", "required": True}]},
    "Runbook": {"folder": "runbooks", "effect": "Steps the desk proposes for matching situations (no score change).",
                "fields": [{"name": "title", "label": "Runbook name", "required": True},
                           {"name": "description", "label": "When to use it", "required": True},
                           {"name": "body", "label": "Steps", "kind": "text", "required": True}]},
    "Architecture": {"folder": "architecture", "effect": "Context for investigations and blast-radius questions.",
                     "fields": [{"name": "title", "label": "Name", "required": True},
                                {"name": "description", "label": "One-sentence summary", "required": True},
                                {"name": "body", "label": "Description", "kind": "text", "required": True}]},
    "Repository": {"folder": "repositories", "effect": "Where the infrastructure code lives: fixes cite it and open PRs against it (no score change).",
                   "fields": [{"name": "title", "label": "Repository", "required": True},
                              {"name": "description", "label": "What it deploys", "required": True},
                              {"name": "owner", "label": "Owning team", "kind": "team"},
                              {"name": "body", "label": "Notes for the desk", "kind": "text"}]},
    "Note": {"folder": "notes", "effect": "Context only.",
             "fields": [{"name": "title", "label": "Title", "required": True},
                        {"name": "description", "label": "One-sentence summary", "required": True},
                        {"name": "body", "label": "Note", "kind": "text", "required": True}]},
    "Reference": {"folder": "references", "effect": "Source material (imported documents) that other concepts cite.",
                  "fields": []},
}
SCORING_KINDS = ("Application", "Account", "Risk Exception", "Security Goal")


def bundle_dir() -> Path:
    return Path(os.environ.get("RGTRIAGE_KNOWLEDGE") or config.home() / "knowledge")


def bundle() -> okf.Bundle:
    return okf.Bundle(bundle_dir())


def inbox_roots() -> list[Path]:
    """Folders the desk may read drafts and imports from (written by the agent or the dashboard, never the desk)."""
    raw = os.environ.get("RGTRIAGE_KNOWLEDGE_INBOX")
    if raw:
        return [Path(p) for p in raw.split(os.pathsep) if p]
    return [Path("/opt/data/proposals/knowledge"), Path("/opt/data/knowledge-inbox"),
            config.home() / "proposals" / "knowledge", config.home() / "knowledge-inbox"]


def review_root() -> Path:
    """Where agent and import drafts wait for review (the first existing proposals/knowledge folder)."""
    for root in inbox_roots():
        if root.name == "knowledge" and root.parent.name == "proposals" and root.parent.exists():
            return root
    return inbox_roots()[0]


def inbox_file(raw: str) -> Path:
    """Resolve a draft/import file and refuse anything outside the inbox folders (symlinks included)."""
    path = Path(raw).expanduser()
    if path.is_symlink():
        raise okf.OKFError("refusing a symbolic link")
    resolved = path.resolve()
    for root in inbox_roots():
        try:
            base = root.resolve()
        except OSError:
            continue
        if base in resolved.parents and resolved.is_file():
            return resolved
    raise okf.OKFError(f"{raw} is not a file in the knowledge inbox ({', '.join(str(r) for r in inbox_roots())})")


def check_actor(actor: str) -> str:
    if not ACTOR.match(actor or ""):
        raise okf.OKFError("reviewer must look like human:<name> (letters, digits, . _ @ + -)")
    return actor


def is_shipped(path: str) -> bool:
    return PurePosixPath(path).parts[:1] == (SHIPPED,)


# ------------------------------------------------------------------ what changes triage

def _list(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in value or [] if str(v).strip()]


def _ext(c: okf.Concept) -> dict:
    ext = c.meta.get("remedigenius")
    return ext if isinstance(ext, dict) else {}


def effective(b: okf.Bundle | None = None, now: datetime | None = None) -> dict:
    """Organization concepts that change prioritization, plus the ones that do not yet and why."""
    b = b or bundle()
    now = now or datetime.now(timezone.utc)
    out = {"applications": [], "accounts": {}, "exceptions": [], "goals": [], "teams": {}, "ignored": [], "expired": []}
    concepts = b.concepts()
    titles = {c.path: c.title for c in concepts}
    for c in concepts:
        if c.error or is_shipped(c.path):
            continue
        if c.type == "Team":
            out["teams"][c.path] = {"path": c.path, "title": c.title, **{k: _ext(c).get(k) for k in ("contact", "escalation")}}
        if c.type not in SCORING_KINDS:
            continue
        tier, state = okf.trust_tier(c.meta), okf.status(c.meta)
        if state != "stable" or tier != "human-reviewed":
            out["ignored"].append({"path": c.path, "reason": f"{state}, {tier}: approve it in the Knowledge tab to apply it"})
            continue
        ext = _ext(c)
        cite = {"path": c.path, "title": c.title, "stale": okf.is_stale(c.meta, now)}
        owner = okf.resolve_link(c.path, str(ext.get("owner") or "")) if ext.get("owner") else None
        if owner:
            cite["owner"] = {"path": owner, "title": titles.get(owner, PurePosixPath(owner).stem.replace("-", " ")),
                             "exists": owner in titles}
        if c.type == "Application":
            tags = ext.get("match_tags") if isinstance(ext.get("match_tags"), dict) else {}
            if not tags or ext.get("criticality") not in CRITICALITIES:
                out["ignored"].append({"path": c.path, "reason": "needs match_tags and a known criticality"})
                continue
            out["applications"].append({**cite, "tags": {str(k): str(v) for k, v in tags.items()},
                                        "criticality": ext["criticality"], "data": ext.get("data")})
        elif c.type == "Account":
            account_id = str(ext.get("account_id") or "")
            if not re.fullmatch(r"\d{12}", account_id) or ext.get("criticality") not in CRITICALITIES:
                out["ignored"].append({"path": c.path, "reason": "needs a 12-digit account_id and a known criticality"})
                continue
            out["accounts"][account_id] = {**cite, "criticality": ext["criticality"], "environment": ext.get("environment")}
        elif c.type == "Risk Exception":
            match = {k: str(ext[k]).strip() for k in ("control_id", "finding_type", "resource", "account_id") if ext.get(k)}
            expires = okf.instant(ext.get("expires"))
            if not ({"control_id", "finding_type", "resource"} & set(match)) or not expires:
                out["ignored"].append({"path": c.path, "reason": "needs a control id, finding type or resource, and an expiry date"})
                continue
            item = {**cite, "match": match, "expires": str(ext.get("expires")), "approved_by": ext.get("approved_by"),
                    "description": str(c.meta.get("description") or "")}
            (out["expired"] if now >= expires else out["exceptions"]).append(item)
        elif c.type == "Security Goal":
            boost = {"resource_types": _list(ext.get("resource_types")), "categories": _list(ext.get("categories")),
                     "signals": _list(ext.get("signals"))}
            if not any(boost.values()):
                out["ignored"].append({"path": c.path, "reason": "needs resource types, categories or signals"})
                continue
            try:
                points = max(1, min(15, int(ext.get("points") or 5)))
            except (TypeError, ValueError):
                points = 5
            out["goals"].append({**cite, "text": c.title, "boost": {**boost, "points": points}})
    return out


def exception_for(finding: dict, exceptions: list[dict]) -> dict | None:
    resource = finding.get("resource") or {}
    for e in exceptions:
        m = e["match"]
        if m.get("account_id") and m["account_id"] != finding.get("account"):
            continue
        if m.get("control_id") and m["control_id"] != (finding.get("control_id") or ""):
            continue
        if m.get("finding_type") and m["finding_type"] not in (finding.get("type") or "") and m["finding_type"] != finding.get("title"):
            continue
        if m.get("resource") and m["resource"] not in (resource.get("id"), resource.get("name")):
            continue
        return e
    return None


# ------------------------------------------------------------------ shipped knowledge

def _shipped_files() -> dict[str, str]:
    """Bundle path -> text for everything RemediGenius-CE ships (guides, source guides, playbooks)."""
    files = {}
    if SEED_DIR.is_dir():
        for path in sorted(SEED_DIR.rglob("*.md")):
            files[f"{SHIPPED}/{path.relative_to(SEED_DIR).as_posix()}"] = path.read_text(encoding="utf-8")
    for name in playbooks.names():
        files[f"{SHIPPED}/playbooks/{name}.md"] = (playbooks.DIR / f"{name}.md").read_text(encoding="utf-8")
    return files


def seed(b: okf.Bundle | None = None) -> dict:
    """Write or refresh the shipped concepts; leave the organization's concepts alone."""
    b = b or bundle()
    b.root.mkdir(parents=True, exist_ok=True)
    wanted = _shipped_files()
    changed = []
    for rel, text in wanted.items():
        okf.parse(text)  # a broken shipped file must fail loudly, not land in the bundle
        path = b.root / rel
        if not path.exists() or path.read_text(encoding="utf-8") != text.replace("\r\n", "\n"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
            changed.append(rel)
    shipped_root = b.root / SHIPPED
    for path in sorted(shipped_root.rglob("*.md")) if shipped_root.exists() else []:
        rel = path.relative_to(b.root).as_posix()
        if path.name not in okf.RESERVED and rel not in wanted:
            path.unlink()
            changed.append(rel)
    if changed or not (b.root / "log.md").exists():
        b.log("Update", f"Shipped knowledge refreshed for RemediGenius-CE {__version__} ({len(changed)} files)")
    reindex(b)
    return {"bundle": str(b.root), "shipped": len(wanted), "changed": len(changed)}


def reindex(b: okf.Bundle | None = None) -> None:
    b = b or bundle()
    b.build_indexes(title="RemediGenius-CE knowledge")


def ensure() -> okf.Bundle:
    b = bundle()
    if not (b.root / SHIPPED).is_dir():
        seed(b)
    return b


# ------------------------------------------------------------------ the generated wiki view (Hermes WebUI)

WIKI_ENV = "RGTRIAGE_WIKI_DIR"
WIKI_SCHEMA = ("Generated view of the RemediGenius-CE knowledge bundle. Do not edit; edit in the dashboard "
               "Knowledge tab.")
LOG_ACTION = re.compile(r"^\*\*([^*]{1,40})\*\*:\s*(.*)$")


def wiki_dir() -> Path | None:
    """Where the desk writes the read-only wiki view; unset means no export."""
    raw = os.environ.get(WIKI_ENV)
    return Path(raw) if raw else None


def _wiki_page(c: okf.Concept) -> tuple[str, str]:
    """(wiki folder, file name): organization concepts as entities/<folder>-<slug>.md, shipped and sources by slug."""
    slug = okf.slug(PurePosixPath(c.path).stem)
    if is_shipped(c.path):
        return "concepts", f"{slug}.md"
    parts = PurePosixPath(c.path).parts
    if parts[0] == "references":
        return "raw", f"{slug}.md"
    return "entities", f"{okf.slug(parts[0])}-{slug}.md"


def _wiki_write(root: Path, rel: str, text: str) -> None:
    """Write one generated file strictly inside the staging folder (never through a symbolic link)."""
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or pure.suffix != ".md":
        raise okf.OKFError(f"refusing to write {rel!r} in the wiki view")
    path = root / pure
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise okf.OKFError(f"refusing to follow a symbolic link at {rel!r}")
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o644)


def _wiki_index(pages: list[dict]) -> str:
    lines = ["---", f'okf_version: "{okf.OKF_VERSION}"', "---", "", "# RemediGenius-CE knowledge", "",
             WIKI_SCHEMA, ""]
    by_type: dict[str, list[dict]] = {}
    for page in pages:
        by_type.setdefault(str(page["type"] or "Unreadable"), []).append(page)
    for type_name in sorted(by_type):
        lines += [f"## {type_name}", ""]
        for page in sorted(by_type[type_name], key=lambda p: p["title"].lower()):
            lines.append(f"* [{okf._md_text(page['title'])}]({page['page']}) - {page['path']}, "
                         f"{page['trust']}, {page['status']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _wiki_log(entries: list[dict]) -> str:
    """The knowledge change log, newest first, with the headings the WebUI reads the last writer from."""
    lines = ["# Knowledge log", ""]
    for entry in entries:
        text = str(entry.get("text") or "").strip()
        match = LOG_ACTION.match(text)
        action, rest = (match.group(1).strip(), match.group(2)) if match else ("Update", text)
        links = okf.LINK.findall(rest)
        heading = f"## [{entry.get('date') or ''}] {action}" + (f" | {links[0][1]}" if links else "")
        lines += [heading, "", f"* {text}", ""]
    return "\n".join(lines).rstrip() + "\n"


def export_wiki(dest: Path, b: okf.Bundle | None = None) -> dict:
    """Write the read-only wiki view the Hermes WebUI shows (Insights -> LLM Wiki) from the bundle.

    Generated one-way: build in a temporary folder inside `dest`, then replace every entry, so pages of removed
    concepts disappear. Nothing outside `dest` is written and no symbolic link is followed.
    """
    b = b or bundle()
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if dest.is_dir() and not dest.is_symlink():
        dest.chmod(0o755)
    staging = Path(tempfile.mkdtemp(dir=dest, prefix=".build-"))
    os.chmod(staging, 0o755)
    pages, counts, taken, entries = [], {"entities": 0, "concepts": 0, "raw": 0}, set(), []
    try:
        for c in b.concepts():
            if c.error:
                continue
            folder, name = _wiki_page(c)
            page, n = f"{folder}/{name}", 2
            while page in taken:  # same stem in two folders: keep both pages
                page, n = f"{folder}/{name[:-3]}-{n}.md", n + 1
            taken.add(page)
            note = f"> Generated from {c.path} ({okf.trust_tier(c.meta)}). Edit in the dashboard Knowledge tab."
            # The WebUI reads the last writer from `updated_by`: who last verified the concept, else who generated it.
            checks = okf.verifications(c.meta)
            writer = checks[-1]["by"] if checks else str((c.meta.get("generated") or {}).get("by") or "unknown")
            _wiki_write(staging, page, okf.dump({**c.meta, "updated_by": writer}, f"{note}\n\n{c.body}"))
            counts[folder] += 1
            pages.append({"page": page, "path": c.path, "type": c.type, "title": c.title,
                          "trust": okf.trust_tier(c.meta), "status": okf.status(c.meta)})
        entries = b.log_entries(limit=200)
        _wiki_write(staging, "index.md", _wiki_index(pages))
        _wiki_write(staging, "SCHEMA.md", f"# Wiki schema\n\n{WIKI_SCHEMA}\n")
        _wiki_write(staging, "log.md", _wiki_log(entries))
        for path in staging.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        for old in dest.iterdir():  # removed concepts go away with their folder; a link is unlinked, never followed
            if old == staging:
                continue
            if old.is_dir() and not old.is_symlink():
                shutil.rmtree(old)
            else:
                old.unlink()
        for child in staging.iterdir():
            os.replace(child, dest / child.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"dest": str(dest), **counts, "pages": len(pages), "log": len(entries)}


# ------------------------------------------------------------------ writes (dashboard / operator only)

def target_path(meta: dict) -> str:
    kind = KINDS.get(str(meta.get("type")), {})
    folder = kind.get("folder") or okf.slug(str(meta.get("type") or "notes"))
    return f"{folder}/{okf.slug(str(meta.get('title') or 'concept'))}.md"


def _guard_org_path(rel: str) -> str:
    rel = rel.strip().lstrip("/")
    if is_shipped(rel):
        raise okf.OKFError(f"{SHIPPED}/ holds the shipped knowledge and is refreshed on every start; save your own concept elsewhere")
    return rel


def save(meta: dict, body: str, actor: str, path: str | None = None, verify: bool = False, replace: bool = False,
         b: okf.Bundle | None = None) -> dict:
    b = b or bundle()
    check_actor(actor)
    meta = dict(meta)
    if not isinstance(meta.get("type"), str) or not meta["type"].strip():
        raise okf.OKFError("frontmatter needs a non-empty `type`")
    rel = _guard_org_path(path or target_path(meta))
    exists = b.path_of(rel).exists()
    if exists and not replace:
        raise okf.OKFError(f"{rel} already exists; choose another title or replace it")
    meta.setdefault("generated", {"by": actor, "at": okf.now_iso()})
    if verify:
        meta["verified"] = okf.verifications(meta) + [{"by": actor, "at": okf.now_iso()}]
        if okf.status(meta) == "draft":
            meta["status"] = "stable"
    rel = b.write(rel, meta, body)
    b.log("Update" if exists else "Creation", f"[{okf._md_text(str(meta.get('title') or rel))}](/{rel}) "
          f"({meta['type']}) by {actor}{', reviewed' if verify else ''}")
    reindex(b)
    return {"path": rel, "trust": okf.trust_tier(meta), "status": okf.status(meta), "replaced": exists}


def verify(rel: str, actor: str, b: okf.Bundle | None = None) -> dict:
    b = b or bundle()
    check_actor(actor)
    rel = _guard_org_path(rel)
    c = b.read(rel)
    if c.error:
        raise okf.OKFError(f"{rel}: {c.error}")
    c.meta["verified"] = okf.verifications(c.meta) + [{"by": actor, "at": okf.now_iso()}]
    if okf.status(c.meta) == "draft":
        c.meta["status"] = "stable"
    b.write(rel, c.meta, c.body)
    b.log("Review", f"[{okf._md_text(c.title)}](/{rel}) confirmed by {actor}")
    reindex(b)
    return {"path": rel, "trust": okf.trust_tier(c.meta), "status": okf.status(c.meta)}


def deprecate(rel: str, actor: str, reason: str, b: okf.Bundle | None = None) -> dict:
    b = b or bundle()
    check_actor(actor)
    rel = _guard_org_path(rel)
    c = b.read(rel)
    if c.error:
        raise okf.OKFError(f"{rel}: {c.error}")
    c.meta["status"] = "deprecated"
    if reason:
        c.meta.setdefault("remedigenius", {})
        if isinstance(c.meta["remedigenius"], dict):
            c.meta["remedigenius"]["deprecated_reason"] = reason[:300]
    b.write(rel, c.meta, c.body)
    b.log("Deprecation", f"[{okf._md_text(c.title)}](/{rel}) by {actor}" + (f": {reason[:200]}" if reason else ""))
    reindex(b)
    return {"path": rel, "status": "deprecated"}


def remove(rel: str, actor: str, b: okf.Bundle | None = None) -> dict:
    """Move a concept to the knowledge trash folder (recoverable), never delete it."""
    b = b or bundle()
    check_actor(actor)
    rel = _guard_org_path(rel)
    path = b.path_of(rel)
    if not path.exists():
        raise okf.OKFError(f"no concept at {rel}")
    trash = config.home() / "knowledge-trash"
    trash.mkdir(parents=True, exist_ok=True)
    target = trash / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{rel.replace('/', '__')}"
    shutil.move(str(path), target)
    b.log("Removal", f"{rel} by {actor} (kept in {target.name})")
    reindex(b)
    return {"path": rel, "trash": str(target)}


def compose(kind: str, fields: dict, actor: str) -> tuple[dict, str]:
    """Concept from the dashboard wizard fields; values are checked per kind."""
    spec = KINDS.get(kind)
    if not spec or not spec["fields"]:
        raise okf.OKFError(f"unknown concept kind {kind!r}")
    fields = {k: (v.strip() if isinstance(v, str) else v) for k, v in (fields or {}).items()}
    for f in spec["fields"]:
        if f.get("required") and not fields.get(f["name"]):
            raise okf.OKFError(f"{f['label']} is required")
    meta = {"type": kind, "title": str(fields["title"])[:120], "description": str(fields["description"])[:300]}
    tags = _list(fields.get("tags"))
    if tags:
        meta["tags"] = tags
    ext: dict = {}
    if fields.get("criticality"):
        if fields["criticality"] not in CRITICALITIES:
            raise okf.OKFError(f"criticality must be one of {', '.join(CRITICALITIES)}")
        ext["criticality"] = fields["criticality"]
    if kind == "Application":
        pairs = fields.get("match_tags")
        if isinstance(pairs, str):
            pairs = dict(p.split("=", 1) for p in _list(pairs) if "=" in p)
        if not isinstance(pairs, dict) or not pairs:
            raise okf.OKFError("give at least one tag as key=value")
        ext["match_tags"] = {str(k).strip(): str(v).strip() for k, v in pairs.items()}
        if fields.get("data"):
            ext["data"] = str(fields["data"])[:200]
    if kind == "Account":
        if not re.fullmatch(r"\d{12}", str(fields.get("account_id") or "")):
            raise okf.OKFError("AWS account id must be 12 digits")
        ext["account_id"] = str(fields["account_id"])
        if fields.get("environment"):
            ext["environment"] = str(fields["environment"])
    if kind == "Team":
        for k in ("contact", "escalation"):
            if fields.get(k):
                ext[k] = str(fields[k])[:300]
    if kind == "Risk Exception":
        for k in ("control_id", "finding_type", "resource", "account_id", "approved_by"):
            if fields.get(k):
                ext[k] = str(fields[k])[:500]
        if not {"control_id", "finding_type", "resource"} & set(ext):
            raise okf.OKFError("give a control id, a finding type or a resource")
        if ext.get("account_id") and not re.fullmatch(r"\d{12}", ext["account_id"]):
            raise okf.OKFError("AWS account id must be 12 digits")
        expires = okf.instant(fields.get("expires"))
        if not expires or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fields["expires"])):
            raise okf.OKFError("expiry must be a date like 2027-01-31")
        if expires <= datetime.now(timezone.utc):
            raise okf.OKFError("expiry must be in the future")
        ext["expires"] = str(fields["expires"])
        meta["stale_after"] = f"{fields['expires']}T00:00:00Z"
    if kind == "Security Goal":
        for k in ("resource_types", "categories", "signals"):
            if fields.get(k):
                ext[k] = _list(fields[k])
        if not any(ext.get(k) for k in ("resource_types", "categories", "signals")):
            raise okf.OKFError("give resource types, categories or signals")
        if fields.get("points") not in (None, ""):
            try:
                ext["points"] = max(1, min(15, int(fields["points"])))
            except (TypeError, ValueError):
                raise okf.OKFError("points must be a number from 1 to 15") from None
    if fields.get("owner"):
        owner = str(fields["owner"]).strip()
        ext["owner"] = owner if owner.startswith("/") else f"/teams/{okf.slug(owner)}.md"
    if ext:
        meta["remedigenius"] = ext
    meta["generated"] = {"by": actor, "at": okf.now_iso()}
    body = str(fields.get("body") or "").strip()
    if ext.get("owner"):
        body = (body + "\n\n" if body else "") + f"Owned by [{PurePosixPath(ext['owner']).stem.replace('-', ' ')}]({ext['owner']})."
    return meta, body or str(meta["description"])


def import_reference(markdown: str, original_name: str, actor: str, sha256: str = "", converter: str = "",
                     title: str = "", b: okf.Bundle | None = None) -> dict:
    """Converted document text becomes a Reference concept (source material, not reviewed knowledge)."""
    b = b or bundle()
    check_actor(actor)
    if sha256:
        for c in b.concepts():
            if c.type == "Reference" and _ext(c).get("original_sha256") == sha256:
                return {"path": c.path, "characters": len(c.body), "truncated": bool(_ext(c).get("truncated")), "existing": True}
    name = PurePosixPath(original_name.replace("\\", "/")).name[:180] or "document"
    limit = okf.MAX_CONCEPT_BYTES - 20_000
    text = markdown.strip()
    truncated = len(text.encode("utf-8")) > limit
    if truncated:
        text = text.encode("utf-8")[:limit].decode("utf-8", "ignore") + "\n\n[truncated: the document is longer than this reference keeps]"
    title = (title or PurePosixPath(name).stem.replace("_", " ").replace("-", " ")).strip()[:120]
    meta = {"type": "Reference", "title": title, "description": f"Imported from {name}",
            "sources": [{"id": "original", "resource": f"file:{name}", "title": name}],
            "generated": {"by": converter or "rgtriage/import", "at": okf.now_iso()},
            "remedigenius": {"original_name": name, **({"original_sha256": sha256} if sha256 else {}),
                             "imported_by": actor, "truncated": truncated}}
    rel = f"references/{okf.slug(title)}.md"
    n = 2
    while b.path_of(rel).exists():
        rel = f"references/{okf.slug(title)}-{n}.md"
        n += 1
    b.write(rel, meta, text or "(no text could be extracted)")
    b.log("Creation", f"Reference [{okf._md_text(title)}](/{rel}) imported from {name} by {actor}")
    reindex(b)
    return {"path": rel, "characters": len(text), "truncated": truncated}


# ------------------------------------------------------------------ reads (agent and dashboard)

def review_queue() -> list[dict]:
    """Drafts waiting for a person: agent proposals and document-import drafts (OKF files in proposals/knowledge)."""
    root = review_root()
    out = []
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.md")):
        if path.is_symlink() or any(p.startswith(".") for p in path.relative_to(root).parts):
            continue
        item = {"file": str(path), "name": path.relative_to(root).as_posix(),
                "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            meta, body = okf.parse(path.read_text(encoding="utf-8"))
            target = target_path(meta)
            item.update({"type": meta["type"], "title": str(meta.get("title") or path.stem),
                         "description": str(meta.get("description") or ""), "generated": meta.get("generated"),
                         "target": target, "target_exists": bundle().path_of(target).exists() if not is_shipped(target) else True,
                         "affects_triage": meta["type"] in SCORING_KINDS})
        except (okf.OKFError, UnicodeDecodeError, OSError) as exc:
            item["error"] = str(exc)
        out.append(item)
    return out


def inspect_file(raw: str) -> dict:
    path = inbox_file(raw)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        meta, body = okf.parse(text)
    except okf.OKFError as exc:
        return {"file": str(path), "error": str(exc), "raw": text}
    target = target_path(meta)
    return {"file": str(path), "meta": meta, "body": body, "raw": text, "target": target,
            "target_exists": not is_shipped(target) and bundle().path_of(target).exists(), "trust": okf.trust_tier(meta),
            "affects_triage": meta["type"] in SCORING_KINDS, "effect": KINDS.get(meta["type"], {}).get("effect", "Context only.")}


def summary(b: okf.Bundle | None = None, concepts: list[okf.Concept] | None = None) -> dict:
    b = b or bundle()
    concepts = concepts if concepts is not None else b.concepts()
    org = [c for c in concepts if not is_shipped(c.path)]
    by_type: dict[str, int] = {}
    for c in org:
        by_type[c.type or "unreadable"] = by_type.get(c.type or "unreadable", 0) + 1
    return {"bundle": str(b.root), "concepts": len(concepts), "shipped": len(concepts) - len(org), "organization": len(org),
            "human_reviewed": sum(1 for c in org if okf.trust_tier(c.meta) == "human-reviewed"),
            "drafts": sum(1 for c in org if okf.status(c.meta) == "draft"),
            "stale": sorted(c.path for c in org if okf.is_stale(c.meta)),
            "errors": sorted(c.path for c in concepts if c.error), "by_type": dict(sorted(by_type.items())),
            "review_queue": len(review_queue())}


def practices_for(control_id: str, concepts: list[okf.Concept]) -> list[okf.Concept]:
    """Shipped Security Practice concepts whose `remedigenius.controls` list the Security Hub control id."""
    if not control_id:
        return []
    return [c for c in concepts if is_shipped(c.path) and c.type == "Security Practice"
            and control_id in [str(x) for x in _ext(c).get("controls") or []]]


def for_finding(finding: dict, b: okf.Bundle | None = None) -> list[dict]:
    """Concepts relevant to one finding: what was applied, the shipped guides, and matching organization concepts."""
    b = b or bundle()
    concepts = {c.path: c for c in b.concepts() if not c.error}
    out, seen = [], set()

    def add(path: str, why: str):
        c = concepts.get(path)
        if c and path not in seen:
            seen.add(path)
            out.append({**c.summary(), "why": why})

    for path in finding.get("knowledge") or []:
        add(path, "applied to this finding's priority")
    guidance_paths = set()
    for practice in practices_for(finding.get("control_id") or "", list(concepts.values())):
        add(practice.path, f"the security practice control {finding.get('control_id')} belongs to")
        guidance_paths.add(practice.path)
    guidance_paths |= {f"{SHIPPED}/playbooks/{name}.md" for name in playbooks.select(finding)}
    # The OKF graph: an organization concept that links to this finding's practice or playbook applies to it.
    for c in concepts.values():
        if not is_shipped(c.path) and guidance_paths & set(c.links):
            add(c.path, "linked to this finding's practice or playbook")
    for name in playbooks.select(finding):
        add(f"{SHIPPED}/playbooks/{name}.md", "remediation playbook for this control or finding type")
    add(f"{SHIPPED}/sources/{finding.get('source')}.md", f"how to read {finding.get('product') or finding.get('source')} findings")
    add(f"{SHIPPED}/guides/where-to-look.md", "where to find the evidence")
    # Specific identifiers only (control id, application, resource name or id): generic words would match everything.
    org = [c for c in concepts.values() if not is_shipped(c.path)]
    resource = finding.get("resource") or {}
    for term, why in ((finding.get("control_id"), "mentions control"), (finding.get("application"), "about application"),
                      (resource.get("name"), "mentions resource"), (resource.get("id"), "mentions resource")):
        if term and len(str(term)) > 2:
            for hit in okf.search(org, str(term), limit=5):
                add(hit["path"], f"{why} {term}")
    return out


def gaps(scan: dict | None, b: okf.Bundle | None = None) -> list[str]:
    """What the desk does not know yet that would change priorities, most useful first."""
    b = b or bundle()
    eff = effective(b)
    out = []
    if scan:
        open_urgent = [f for f in scan.get("findings", []) if f.get("priority") in ("P1", "P2")
                       and (f.get("decision") or {}).get("status") not in ("accepted_risk", "suppressed", "resolved", "false_positive")]
        unowned = [f for f in open_urgent if not f.get("application") and f["account"] not in eff["accounts"]]
        if unowned:
            sample = sorted({f["resource"].get("name") or f["resource"].get("id") for f in unowned})[:5]
            out.append(f"{len(unowned)} open P1/P2 findings sit on resources the desk cannot map to an application or a "
                       f"described account (for example {', '.join(sample)}). An Application concept (with the resource tags) "
                       "or an Account concept sets their real criticality and owner.")
        known = {a.get("account_id") for a in (scan.get("profile") or {}).get("accounts", [])}
        known |= set((scan.get("onboarding") or {}).get("full_read") or [])
        missing = sorted(a for a in known if a and a not in eff["accounts"])
        if missing:
            out.append(f"{len(missing)} AWS account(s) have no Account concept ({', '.join(missing[:6])}): say what runs there "
                       "and how critical it is.")
    if not eff["teams"]:
        out.append("No Team concepts: the desk cannot say whom to involve for a finding.")
    if eff["expired"]:
        out.append(f"{len(eff['expired'])} risk exception(s) expired; their findings are back in the queue: "
                   + ", ".join(e["path"] for e in eff["expired"][:5]))
    if eff["ignored"]:
        out.append(f"{len(eff['ignored'])} concept(s) would change priorities but are not applied yet: "
                   + "; ".join(f"{i['path']} ({i['reason']})" for i in eff["ignored"][:5]))
    queue = review_queue()
    if queue:
        out.append(f"{len(queue)} draft(s) wait in the review queue (Knowledge tab → Review).")
    return out


def board_lines(scan: dict) -> list[str]:
    k = scan.get("knowledge") or {}
    if not k:
        return []
    line = (f"Knowledge: {k.get('organization', 0)} organization concepts ({k.get('human_reviewed', 0)} reviewed) · "
            f"business context applied to {k.get('used_in', 0)} of {k.get('findings', 0) or '?'} findings")
    if k.get("review_queue"):
        line += f" · {k['review_queue']} draft(s) to review"
    if k.get("stale"):
        line += f" · {len(k['stale'])} stale"
    lines = [line]
    basics = k.get("basics") or {}
    if basics and sum(basics.values()) < len(basics):
        missing = ", ".join(name.replace("_", " ") for name, done in basics.items() if not done)
        lines.append(f"Business context: {sum(basics.values())} of {len(basics)} basics set (missing: {missing}). "
                     "Ranking uses generic defaults until then; say \"set up business context\" to do it in about ten minutes.")
    if k.get("gaps"):
        lines.append(f"Knowledge gap: {k['gaps'][0]}")
    return lines


def scan_summary(scan: dict, eff: dict, b: okf.Bundle | None = None) -> dict:
    data = summary(b)
    data["used_in"] = sum(1 for f in scan.get("findings", []) if f.get("knowledge"))
    data["findings"] = len(scan.get("findings", []))
    types = data.get("by_type") or {}
    data["basics"] = {"account_criticality": bool(eff["accounts"]), "critical_applications": bool(eff["applications"]),
                      "owners": bool(types.get("Team")), "IaC_location": bool(config.load().get("iac_paths")),
                      "a_policy": bool(types.get("Policy"))}
    data["gaps"] = gaps(scan, b)[:3]
    data["applied"] = {"applications": len(eff["applications"]), "accounts": len(eff["accounts"]),
                       "exceptions": len(eff["exceptions"]), "goals": len(eff["goals"])}
    return data


def dumps(data) -> str:
    return json.dumps(data, indent=1, default=str)
