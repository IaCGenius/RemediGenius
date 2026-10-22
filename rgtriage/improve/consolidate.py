"""Find overlapping skill text, duplicate or contradictory knowledge, stale concepts and oversized skills.

Every result is a proposal: a unified diff for a skill (which then goes through the security gate like any
candidate) or a merged OKF draft for the review queue that cites the originals. Nothing is changed here.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from .. import knowledge, okf

STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are", "it", "this", "that", "be", "as",
        "by", "at", "from", "you", "your", "team", "use", "when", "if", "not", "no", "only", "then"}
MAX_SKILL_TOKENS = 1800


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_.-]+", text.lower()) if w not in STOP and len(w) > 1}


def _similar(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _bullets(text: str) -> list[str]:
    body = okf.split(text)[1] if text.startswith("---") else text
    return [line.strip() for line in body.splitlines() if line.strip().startswith(("-", "*", "1", "2", "3", "4", "5"))
            and len(_tokens(line)) >= 6]


def skills_report(skills_dir: Path, threshold: float = 0.7) -> list[dict]:
    skills = {p.parent.name: p.read_text(encoding="utf-8") for p in sorted(skills_dir.glob("*/SKILL.md"))}
    items = []
    for name, text in skills.items():
        est = len(text) // 4
        if est > MAX_SKILL_TOKENS:
            items.append({"kind": "skill too long", "skills": [name], "detail": f"about {est} tokens (aim for under {MAX_SKILL_TOKENS})"})
    names = sorted(skills)
    seen = set()
    for i, a in enumerate(names):
        for b in names[i:]:
            for la in _bullets(skills[a]):
                for lb in _bullets(skills[b]):
                    if (a == b and la == lb) or (a, la) == (b, lb):
                        continue
                    score = _similar(_tokens(la), _tokens(lb))
                    key = tuple(sorted([(a, la), (b, lb)]))
                    if score >= threshold and key not in seen:
                        seen.add(key)
                        # keep the instruction where it is longer-lived (the shorter skill), drop the other copy
                        drop_skill, drop_line = (b, lb) if len(skills[b]) >= len(skills[a]) else (a, la)
                        after = skills[drop_skill].replace(drop_line + "\n", "", 1)
                        diff = "".join(difflib.unified_diff(skills[drop_skill].splitlines(True), after.splitlines(True),
                                                            f"{drop_skill}/SKILL.md", f"{drop_skill}/SKILL.md (proposed)"))
                        items.append({"kind": "overlapping instructions", "skills": sorted({a, b}), "similarity": round(score, 2),
                                      "a": la[:240], "b": lb[:240], "proposal": {"skill": drop_skill, "diff": diff, "text": after}})
    return items


def _draft_merge(kind: str, concepts: list[okf.Concept]) -> str:
    first = concepts[0]
    meta = {"type": first.type, "title": first.title, "description": str(first.meta.get("description") or ""), "status": "draft",
            "sources": [{"id": f"c{n}", "resource": f"/{c.path}", "title": c.title} for n, c in enumerate(concepts, 1)],
            "generated": {"by": "remedigenius-desk/consolidate", "at": okf.now_iso()}}
    ext = {}
    for c in concepts:
        for k, v in (c.meta.get("remedigenius") or {}).items():
            ext.setdefault(k, v)
    if ext:
        meta["remedigenius"] = ext
    body = [f"Merged from {', '.join(c.path for c in concepts)} ({kind}). After approving this concept, deprecate the "
            "originals in the Knowledge tab; their history and links stay.", ""]
    for c in concepts:
        body += [f"## From {c.path}", "", c.body.strip(), ""]
    return okf.dump(meta, "\n".join(body))


def knowledge_report(b: okf.Bundle | None = None) -> list[dict]:
    b = b or knowledge.bundle()
    org = [c for c in b.concepts() if not c.error and not knowledge.is_shipped(c.path) and okf.status(c.meta) != "deprecated"]
    items = []
    by_type: dict[str, list] = {}
    for c in org:
        by_type.setdefault(c.type, []).append(c)
    for type_name, group in by_type.items():
        for i, a in enumerate(group):
            for c2 in group[i + 1:]:
                ta, tb = _tokens(a.title), _tokens(c2.title)
                ea, eb = a.meta.get("remedigenius") or {}, c2.meta.get("remedigenius") or {}
                same_contact = ea.get("contact") and ea.get("contact") == eb.get("contact")
                if _similar(ta, tb) >= 0.5 or same_contact:
                    items.append({"kind": "duplicate concepts", "paths": [a.path, c2.path],
                                  "detail": "same contact" if same_contact else "similar titles",
                                  "proposal": {"draft": _draft_merge("duplicates", [a, c2])}})
    apps = [c for c in by_type.get("Application", []) if isinstance((c.meta.get("remedigenius") or {}).get("match_tags"), dict)]
    for i, a in enumerate(apps):
        for c2 in apps[i + 1:]:
            ta, tb = a.meta["remedigenius"]["match_tags"], c2.meta["remedigenius"]["match_tags"]
            if ta == tb:
                ca, cb = a.meta["remedigenius"].get("criticality"), c2.meta["remedigenius"].get("criticality")
                items.append({"kind": "contradiction" if ca != cb else "duplicate concepts", "paths": [a.path, c2.path],
                              "detail": f"both match tags {ta}" + (f" but say {ca} vs {cb}" if ca != cb else ""),
                              "proposal": {"draft": _draft_merge("same tags", [a, c2])}})
    accounts: dict[str, list] = {}
    for c in by_type.get("Account", []):
        aid = str((c.meta.get("remedigenius") or {}).get("account_id") or "")
        if aid:
            accounts.setdefault(aid, []).append(c)
    for aid, group in accounts.items():
        crits = {(c.meta.get("remedigenius") or {}).get("criticality") for c in group}
        if len(group) > 1:
            items.append({"kind": "contradiction" if len(crits) > 1 else "duplicate concepts", "paths": [c.path for c in group],
                          "detail": f"account {aid} described {len(group)} times" + (f" with {sorted(map(str, crits))}" if len(crits) > 1 else ""),
                          "proposal": {"draft": _draft_merge("same account", group)}})
    for c in org:
        if okf.is_stale(c.meta):
            items.append({"kind": "stale", "paths": [c.path], "detail": f"stale since {c.meta.get('stale_after')}: re-review or deprecate"})
    deprecated = {c.path for c in b.concepts() if okf.status(c.meta) == "deprecated"}
    for c in org:
        for target in c.links:
            if target in deprecated:
                items.append({"kind": "links to deprecated", "paths": [c.path, target], "detail": "update the link"})
    return items
