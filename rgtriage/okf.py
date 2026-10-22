"""Open Knowledge Format (OKF) v0.2 bundles: read, write, index, log, validate, search, graph.

A bundle is a folder of markdown concepts with YAML frontmatter (`type` is the only required key),
reserved `index.md` / `log.md` files, and plain markdown links between concepts. Spec:
https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md

Parsing is defensive because concepts come from people, documents and agents: size limits, safe YAML only
(no anchors, aliases or tags), unique keys, and timestamps kept as the text that was written.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

import yaml

OKF_VERSION = "0.2"
RESERVED = {"index.md", "log.md"}
STATUSES = ("draft", "stable", "deprecated")
MAX_CONCEPT_BYTES = 400_000
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


class OKFError(ValueError):
    pass


# ------------------------------------------------------------------ parse / dump

class _Loader(yaml.SafeLoader):
    """Safe loader that rejects duplicate keys and keeps timestamps as the original text."""


def _mapping(loader, node):
    out = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise OKFError("frontmatter keys must be strings")
        if key in out:
            raise OKFError(f"duplicate frontmatter key {key!r}")
        out[key] = loader.construct_object(value_node, deep=True)
    return out


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)
_Loader.add_constructor("tag:yaml.org,2002:timestamp", lambda loader, node: loader.construct_scalar(node))


def split(text: str) -> tuple[str | None, str]:
    """(frontmatter text or None, body)."""
    text = text.replace("\r\n", "\n").lstrip("﻿")
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 3)
    while end != -1 and text[end + 4:end + 5] not in ("", "\n"):
        end = text.find("\n---", end + 4)
    if end == -1:
        raise OKFError("frontmatter starts with --- but has no closing --- line")
    return text[4:end + 1], text[end + 5:].lstrip("\n")


def load_yaml(raw: str) -> dict:
    try:
        tokens = list(yaml.scan(raw))
    except yaml.YAMLError as exc:
        raise OKFError(f"frontmatter is not valid YAML: {exc}".splitlines()[0]) from None
    if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)) for t in tokens):
        raise OKFError("YAML anchors, aliases and tags are not accepted in frontmatter")
    try:
        meta = yaml.load(raw, Loader=_Loader)  # noqa: S506 - _Loader is a SafeLoader subclass
    except (yaml.YAMLError, RecursionError) as exc:
        raise OKFError(f"frontmatter is not valid YAML: {exc}".splitlines()[0]) from None
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise OKFError("frontmatter must be a mapping")
    return meta


def parse(text: str, require_type: bool = True) -> tuple[dict, str]:
    """Parse a concept document into (frontmatter, body)."""
    if len(text.encode("utf-8")) > MAX_CONCEPT_BYTES:
        raise OKFError(f"concept is larger than {MAX_CONCEPT_BYTES // 1000} KB")
    raw, body = split(text)
    if raw is None:
        raise OKFError("no YAML frontmatter (a concept starts with a --- line)")
    meta = load_yaml(raw)
    if require_type and (not isinstance(meta.get("type"), str) or not meta["type"].strip()):
        raise OKFError("frontmatter needs a non-empty `type`")
    return meta, body


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def dump(meta: dict, body: str) -> str:
    front = yaml.dump(meta, Dumper=_Dumper, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    return f"---\n{front}---\n\n{body.strip()}\n"


# ------------------------------------------------------------------ trust and lifecycle

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def instant(value) -> datetime | None:
    """ISO 8601 date or datetime -> aware datetime (dates are midnight UTC); None when absent or invalid."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def verifications(meta: dict) -> list[dict]:
    """`verified` as a list (a bare mapping is a one-element list, spec §5.2)."""
    value = meta.get("verified")
    if isinstance(value, dict):
        value = [value]
    return [v for v in value or [] if isinstance(v, dict) and isinstance(v.get("by"), str)]


def trust_tier(meta: dict) -> str:
    actors = [v["by"] for v in verifications(meta)]
    if not actors:
        return "unverified"
    return "human-reviewed" if any(a.startswith("human:") for a in actors) else "machine-confirmed"


def status(meta: dict) -> str:
    value = meta.get("status") or "stable"
    return value if value in STATUSES else "stable"


def is_stale(meta: dict, now: datetime | None = None) -> bool:
    when = instant(meta.get("stale_after"))
    return bool(when and (now or datetime.now(timezone.utc)) >= when)


# ------------------------------------------------------------------ bundle

@dataclass
class Concept:
    path: str                     # bundle-relative posix path, e.g. "applications/payments.md"
    meta: dict
    body: str
    error: str = ""
    links: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or PurePosixPath(self.path).stem.replace("-", " "))

    @property
    def type(self) -> str:
        return str(self.meta.get("type") or "")

    def summary(self, now: datetime | None = None) -> dict:
        return {"path": self.path, "type": self.type, "title": self.title,
                "description": str(self.meta.get("description") or ""), "tags": self.meta.get("tags") or [],
                "status": status(self.meta), "trust": trust_tier(self.meta), "stale": is_stale(self.meta, now),
                "stale_after": self.meta.get("stale_after"), "generated": self.meta.get("generated"),
                "verified": verifications(self.meta), "error": self.error}


def resolve_link(source_path: str, target: str) -> str | None:
    """Bundle-relative path a markdown link points to, or None for external links and anchors."""
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return None
    if target.startswith("/"):
        path = PurePosixPath(target.lstrip("/"))
    else:
        path = PurePosixPath(source_path).parent / target
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    resolved = "/".join(parts)
    if target.endswith("/"):
        resolved += "/"
    return resolved or None


def links_in(source_path: str, body: str) -> list[str]:
    out = []
    for _, target in LINK.findall(body):
        resolved = resolve_link(source_path, target)
        if resolved and (resolved.endswith(".md") or resolved.endswith("/")) and resolved not in out:
            out.append(resolved)
    return out


def _skip(rel: PurePosixPath) -> bool:
    return any(part.startswith((".", "_")) for part in rel.parts)


class Bundle:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # -- paths
    def path_of(self, rel: str) -> Path:
        """Absolute path for a bundle-relative concept path; refuses anything outside the bundle."""
        rel = rel.strip().lstrip("/").replace("\\", "/")
        pure = PurePosixPath(rel)
        if not rel or pure.is_absolute() or ".." in pure.parts or _skip(pure):
            raise OKFError(f"invalid concept path {rel!r}")
        if pure.suffix != ".md":
            raise OKFError("concept paths end in .md")
        path = (self.root / pure).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise OKFError(f"concept path {rel!r} is outside the bundle")
        return path

    def exists(self) -> bool:
        return self.root.is_dir()

    # -- read
    def concept_files(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        out = []
        for path in sorted(self.root.rglob("*.md")):
            rel = PurePosixPath(path.relative_to(self.root).as_posix())
            if _skip(rel) or path.name in RESERVED or path.is_symlink():
                continue
            out.append(path)
        return out

    def read(self, rel: str) -> Concept:
        path = self.path_of(rel)
        if path.name in RESERVED:
            raise OKFError(f"{path.name} is a reserved file, not a concept")
        rel = path.relative_to(self.root.resolve()).as_posix()
        try:
            meta, body = parse(path.read_text(encoding="utf-8"))
            return Concept(rel, meta, body, links=links_in(rel, body))
        except FileNotFoundError:
            raise OKFError(f"no concept at {rel}") from None
        except (OKFError, UnicodeDecodeError) as exc:
            return Concept(rel, {}, "", error=str(exc))

    def concepts(self) -> list[Concept]:
        out = []
        for path in self.concept_files():
            rel = path.relative_to(self.root).as_posix()
            try:
                meta, body = parse(path.read_text(encoding="utf-8"))
                out.append(Concept(rel, meta, body, links=links_in(rel, body)))
            except (OKFError, UnicodeDecodeError, OSError) as exc:
                out.append(Concept(rel, {}, "", error=str(exc)))
        return out

    # -- write
    def write(self, rel: str, meta: dict, body: str) -> str:
        if not isinstance(meta.get("type"), str) or not meta["type"].strip():
            raise OKFError("frontmatter needs a non-empty `type`")
        path = self.path_of(rel)
        if path.name in RESERVED:
            raise OKFError(f"{path.name} is reserved for the bundle")
        text = dump(meta, body)
        parse(text)  # never write something this module cannot read back
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        return path.relative_to(self.root.resolve()).as_posix()

    def log(self, kind: str, text: str, day: str | None = None) -> None:
        """Prepend an entry to the root log.md under today's date (newest first, spec §9)."""
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.root / "log.md"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if not lines or not lines[0].startswith("# "):
            lines = ["# Directory Update Log", ""] + lines
        entry = f"* **{kind}**: {text}"
        heading = f"## {day}"
        if heading in lines:
            index = lines.index(heading) + 1
            lines.insert(index, entry)
        else:
            first = next((n for n, line in enumerate(lines) if line.startswith("## ")), len(lines))
            lines[first:first] = [heading, entry, ""]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")

    def log_entries(self, limit: int = 50) -> list[dict]:
        path = self.root / "log.md"
        if not path.exists():
            return []
        out, day = [], ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                day = line[3:].strip()
            elif line.startswith("* ") and day:
                out.append({"date": day, "text": line[2:].strip()})
                if len(out) >= limit:
                    break
        return out

    def build_indexes(self, concepts: list[Concept] | None = None, title: str = "") -> list[str]:
        """Write index.md in every folder (spec §8): concepts grouped by type, then sub-folders."""
        concepts = concepts if concepts is not None else self.concepts()
        folders: dict[str, list[Concept]] = {}
        for c in concepts:
            folders.setdefault(PurePosixPath(c.path).parent.as_posix(), []).append(c)
        all_folders = set(folders) | {"."}
        for folder in list(all_folders):
            parts = PurePosixPath(folder).parts
            for n in range(len(parts)):
                all_folders.add("/".join(parts[:n]) or ".")
        written = []
        for folder in sorted(all_folders):
            children = sorted(f.rsplit("/", 1)[-1] for f in all_folders
                              if f != "." and (f.rsplit("/", 1)[0] if "/" in f else ".") == folder)
            lines = []
            if folder == ".":
                lines += ["---", f'okf_version: "{OKF_VERSION}"', "---", ""]
                if title:
                    lines += [f"# {title}", ""]
            by_type: dict[str, list[Concept]] = {}
            for c in folders.get(folder, []):
                by_type.setdefault(c.type or "Unreadable", []).append(c)
            for type_name in sorted(by_type):
                lines += [f"# {type_name}", ""]
                for c in sorted(by_type[type_name], key=lambda c: c.title.lower()):
                    description = str(c.meta.get("description") or c.error or "").replace("\n", " ").strip()
                    lines.append(f"* [{_md_text(c.title)}]({PurePosixPath(c.path).name})" + (f" - {description}" if description else ""))
                lines.append("")
            if children:
                lines += ["# Folders", ""]
                for child in children:
                    sub = child if folder == "." else f"{folder}/{child}"
                    count = sum(len(v) for k, v in folders.items() if k == sub or k.startswith(sub + "/"))
                    lines.append(f"* [{child}]({child}/) - {count} concept{'s' if count != 1 else ''}")
                lines.append("")
            path = self.root / ("index.md" if folder == "." else f"{folder}/index.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            text = "\n".join(lines).rstrip() + "\n"
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8", newline="\n")
                written.append(path.relative_to(self.root).as_posix())
        for stale in self.root.rglob("index.md"):
            folder = stale.parent.relative_to(self.root).as_posix()
            if folder not in all_folders and not _skip(PurePosixPath(folder)):
                stale.unlink()  # generated file for a folder that no longer holds concepts
        return written

    # -- checks and views
    def validate(self, concepts: list[Concept] | None = None, now: datetime | None = None) -> list[dict]:
        """Conformance errors (spec §11) and curation warnings. Never rejects the bundle as a whole."""
        concepts = concepts if concepts is not None else self.concepts()
        known = {c.path for c in concepts}
        folders = {PurePosixPath(p).parent.as_posix() + "/" for p in known}
        issues = []
        for c in concepts:
            if c.error:
                issues.append({"level": "error", "path": c.path, "message": c.error})
                continue
            if not c.meta.get("title"):
                issues.append({"level": "warning", "path": c.path, "message": "no title"})
            if not c.meta.get("description"):
                issues.append({"level": "warning", "path": c.path, "message": "no description (used by index and search)"})
            if c.meta.get("status") not in (None, *STATUSES):
                issues.append({"level": "warning", "path": c.path, "message": f"unknown status {c.meta['status']!r}"})
            if is_stale(c.meta, now):
                issues.append({"level": "warning", "path": c.path, "message": f"stale since {c.meta.get('stale_after')}"})
            for target in c.links:
                if target not in known and target not in folders:
                    issues.append({"level": "warning", "path": c.path, "message": f"link to missing concept /{target}"})
            generated = c.meta.get("generated")
            if generated is not None and not (isinstance(generated, dict) and isinstance(generated.get("by"), str)):
                issues.append({"level": "warning", "path": c.path, "message": "`generated` needs `by`"})
        return issues

    def graph(self, concepts: list[Concept] | None = None, now: datetime | None = None) -> dict:
        concepts = concepts if concepts is not None else self.concepts()
        known = {c.path for c in concepts}
        nodes = [{"id": c.path, "title": c.title, "type": c.type, "trust": trust_tier(c.meta), "status": status(c.meta),
                  "stale": is_stale(c.meta, now), "error": bool(c.error)} for c in concepts]
        edges = []
        for c in concepts:
            for target in c.links:
                if target in known and target != c.path:
                    edges.append({"source": c.path, "target": target})
        return {"nodes": nodes, "edges": edges}

    def backlinks(self, rel: str, concepts: list[Concept] | None = None) -> list[str]:
        concepts = concepts if concepts is not None else self.concepts()
        return sorted(c.path for c in concepts if rel in c.links and c.path != rel)


def search(concepts: list[Concept], query: str, limit: int = 10) -> list[dict]:
    """Lexical search: title and tags weigh most, then description, then body."""
    words = [w for w in re.findall(r"[\w.:-]+", query.lower()) if len(w) > 1]
    if not words:
        return []
    results = []
    for c in concepts:
        if c.error:
            continue
        title = c.title.lower()
        tags = " ".join(str(t) for t in c.meta.get("tags") or []).lower()
        description = str(c.meta.get("description") or "").lower()
        extras = " ".join(str(v) for k, v in c.meta.items() if k not in ("title", "description", "tags", "sources")).lower()
        body = c.body.lower()
        score = 0
        for w in words:
            score += 8 * (w in title) + 5 * (w in tags) + 4 * (w in description) + 3 * (w in extras) + min(body.count(w), 5)
        if all(w in f"{title} {tags} {description} {extras} {body}" for w in words):
            score += 5
        if score:
            snippet = _snippet(c.body, words)
            results.append({**c.summary(), "score": score, "snippet": snippet})
    results.sort(key=lambda r: (-r["score"], r["path"]))
    return results[:limit]


def _snippet(body: str, words: list[str], width: int = 220) -> str:
    text = re.sub(r"\s+", " ", body)
    low = text.lower()
    hits = [low.find(w) for w in words if low.find(w) >= 0]
    start = max(0, min(hits) - 60) if hits else 0
    return ("…" if start else "") + text[start:start + width].strip() + ("…" if start + width < len(text) else "")


def _md_text(text: str) -> str:
    return text.replace("[", "(").replace("]", ")")


def slug(text: str, limit: int = 60) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return value[:limit].strip("-") or "concept"
