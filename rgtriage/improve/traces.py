"""Read and learn from execution traces written by the rg-triage Hermes plugin.

One JSON line per agent turn (skills loaded, tool calls, finding refs, citations, tokens, redacted text) plus
feedback lines (/rate, or a correction detected in the next user message). Everything here is deterministic:
failures, knowledge gaps, lessons (a reusable lesson for a skill vs. an organization fact for the OKF review queue)
and candidate evaluation cases. Organization facts only ever become drafts that a person reviews.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config, okf
from .redact import redact

ORG_FACT = re.compile(r"\b(owns?|owned by|belongs? to|our team|team|on-?call|contact|production|prod\b|sandbox|staging|"
                      r"critical|approved|exception|policy|is used (?:only )?by|used for|handles|stores|pci|customer data)\b", re.I)
NO_MATCH = "No concept matches"


def traces_dir() -> Path:
    if os.environ.get("RGTRIAGE_TRACES_DIR"):
        return Path(os.environ["RGTRIAGE_TRACES_DIR"])
    for candidate in (Path("/opt/data/rg-traces"), config.home() / "rg-traces"):
        if candidate.is_dir():
            return candidate
    return config.home() / "rg-traces"


def load(days: int = 30, root: Path | None = None) -> list[dict]:
    root = root or traces_dir()
    if not root.is_dir():
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    records = []
    for path in sorted(root.glob("*.jsonl")):
        if path.stem < since:
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def turns(records: list[dict]) -> list[dict]:
    """Turn records with their feedback attached."""
    by_id = {}
    ordered = []
    for r in records:
        if r.get("type") == "turn":
            r = dict(r, feedback=[])
            by_id[(r.get("session_id"), str(r.get("turn_id")))] = r
            ordered.append(r)
    for r in records:
        if r.get("type") == "feedback":
            turn = by_id.get((r.get("session_id"), str(r.get("turn_id"))))
            if turn is None:  # feedback on "the last turn" of the session
                same = [t for t in ordered if t.get("session_id") == r.get("session_id") and t.get("at", "") <= r.get("at", "~")]
                turn = same[-1] if same else None
            if turn is not None:
                turn["feedback"].append({"rating": r.get("rating"), "comment": redact(r.get("comment"), 600)})
    return ordered


def _tool_key(tool: dict) -> str:
    return f"{tool.get('name')} {json.dumps(tool.get('args') or {}, sort_keys=True)[:200]}"


def failure_reasons(turn: dict) -> list[str]:
    reasons = []
    for fb in turn.get("feedback", []):
        if fb["rating"] == "down":
            reasons.append("rated down" + (f": {fb['comment']}" if fb.get("comment") else ""))
        elif fb["rating"] == "correction":
            reasons.append(f"user corrected: {fb.get('comment')}")
    tools = turn.get("tools") or []
    for t in tools:
        if t.get("status") not in (None, "ok", "success") or t.get("error"):
            reasons.append(f"tool error in {t.get('name')}: {(t.get('error') or '')[:160]}")
    for key, n in Counter(_tool_key(t) for t in tools).items():
        if n >= 3:
            reasons.append(f"repeated the same call {n} times: {key[:160]}")
    for t in tools:
        if (t.get("args") or {}).get("view") == "search" and NO_MATCH in (t.get("result") or ""):
            reasons.append(f"knowledge search found nothing: {(t.get('args') or {}).get('query')}")
    return reasons


def summary(records: list[dict]) -> dict:
    ts = turns(records)
    feedback = Counter(fb["rating"] for t in ts for fb in t["feedback"])
    skills = Counter(s for t in ts for s in t.get("skills") or [])
    actions = Counter((t2.get("args") or {}).get("action") or t2.get("name") for t in ts for t2 in t.get("tools") or [])
    return {"turns": len(ts), "sessions": len({t.get("session_id") for t in ts}),
            "tokens": {"input": sum((t.get("tokens") or {}).get("input", 0) or 0 for t in ts),
                       "output": sum((t.get("tokens") or {}).get("output", 0) or 0 for t in ts)},
            "feedback": dict(feedback), "skills": dict(skills.most_common(10)), "tools": dict(actions.most_common(12)),
            "failed_turns": sum(1 for t in ts if failure_reasons(t)), "dir": str(traces_dir())}


def failures(records: list[dict], limit: int = 50) -> list[dict]:
    out = []
    for t in turns(records):
        reasons = failure_reasons(t)
        if reasons:
            out.append({"id": t.get("id"), "at": t.get("at"), "reasons": reasons, "user": redact(t.get("user"), 400),
                        "answer": redact(t.get("answer"), 600), "skills": t.get("skills") or [],
                        "tools": [(x.get("args") or {}).get("action") or x.get("name") for x in t.get("tools") or []]})
    return out[-limit:]


def target_skill(turn: dict) -> str:
    skills = [s for s in turn.get("skills") or [] if s.startswith("rg-")]
    if skills:
        return skills[-1]
    actions = {(t.get("args") or {}).get("action") for t in turn.get("tools") or []}
    if "fix" in actions or "validate" in actions:
        return "rg-iac-fix"
    if "aws" in actions:
        return "rg-investigate"
    if "knowledge" in actions:
        return "rg-knowledge"
    if "onboarding" in actions or "doctor" in actions:
        return "rg-onboard"
    return "rg-triage"


def _draft(title: str, statement: str, evidence: str) -> str:
    meta = {"type": "Note", "title": title[:100], "description": statement[:200], "status": "draft",
            "sources": [{"id": "trace", "resource": f"trace:{evidence}", "title": "conversation with the security desk"}],
            "generated": {"by": "remedigenius-desk/lessons", "at": okf.now_iso()}}
    return okf.dump(meta, f"What the user told the desk:\n\n> {statement}\n\nTurn this into an Application, Account, Team, "
                          "Policy or Risk Exception concept if it changes priorities, then approve it.")


def lessons(records: list[dict]) -> list[dict]:
    """Corrections and repeated failures become lessons: reusable ones for a skill, organization facts for review."""
    out = []
    for t in turns(records):
        reasons = failure_reasons(t)
        if not reasons:
            continue
        corrections = [fb["comment"] for fb in t["feedback"] if fb.get("comment")]
        skill = target_skill(t)
        for comment in corrections:
            if ORG_FACT.search(comment):
                title = " ".join(re.findall(r"[\w'-]+", comment)[:8]) or "Organization fact"
                out.append({"kind": "org_fact", "skill": skill, "text": comment, "evidence": [t.get("id")],
                            "draft": _draft(title, comment, t.get("id") or "")})
            else:
                out.append({"kind": "general", "skill": skill, "evidence": [t.get("id")],
                            "text": f"After the user asked \"{redact(t.get('user'), 160)}\", they corrected the answer: "
                                    f"\"{comment}\". Change the {skill} guidance so this does not happen again."})
        for reason in reasons:
            if reason.startswith(("repeated the same call", "tool error")):
                out.append({"kind": "general", "skill": skill, "evidence": [t.get("id")],
                            "text": f"{reason}. The {skill} guidance should tell the agent how to get this evidence in one call "
                                    "or when to stop and say what it could not see."})
    merged: dict[tuple, dict] = {}
    for item in out:  # the same lesson from several turns is one lesson with more evidence
        key = (item["kind"], item["skill"], item["text"][:120])
        if key in merged:
            merged[key]["evidence"] += item["evidence"]
        else:
            merged[key] = item
    return list(merged.values())


def gaps(records: list[dict]) -> list[dict]:
    """Knowledge the agent looked for and did not find, as specific questions with evidence."""
    searches, questions, unowned = defaultdict(list), defaultdict(list), defaultdict(set)
    for t in turns(records):
        for tool in t.get("tools") or []:
            args = tool.get("args") or {}
            result = tool.get("result") or ""
            if args.get("view") == "search" and NO_MATCH in result:
                searches[str(args.get("query") or "").strip().lower()].append(t.get("id"))
            if tool.get("name") == "clarify" and args.get("question"):
                questions[redact(args["question"], 300)].append(t.get("id"))
            if args.get("action") in ("show", "fix") and args.get("ref") and "Owner:" not in result and "rgtriage show" not in result:
                unowned[args["ref"]].add(t.get("session_id"))
    items = []
    for query, ids in searches.items():
        if query:
            items.append({"kind": "missing knowledge", "question": f"The desk searched its knowledge for \"{query}\" and found "
                          "nothing. What should it know about this?", "evidence": ids, "count": len(ids)})
    for question, ids in questions.items():
        items.append({"kind": "asked the user", "question": question, "evidence": ids, "count": len(ids)})
    for ref, sessions in unowned.items():
        if len(sessions) >= 2:
            items.append({"kind": "owner", "question": f"Finding {ref} was investigated in {len(sessions)} conversations without "
                          "a known owner. Who owns this resource, and how critical is it?", "evidence": sorted(s for s in sessions if s),
                          "count": len(sessions)})
    return sorted(items, key=lambda i: -i["count"])


def case_candidates(records: list[dict]) -> list[dict]:
    """Corrected turns are candidate evaluation tasks (a person writes the rubric before they count)."""
    out = []
    for t in turns(records):
        corrections = [fb["comment"] for fb in t["feedback"] if fb.get("comment")]
        if corrections and t.get("user"):
            expected = sorted(set(re.findall(r"\b[A-Z][\w-]{2,}(?:\s+[A-Z][\w-]{2,})*\b|\b[a-z0-9-]+\.[a-z0-9.-]+\b", corrections[0])))[:4]
            out.append({"id": f"from-{(t.get('id') or 'turn').replace(':', '-')}", "split": "train", "prompt": redact(t["user"], 500),
                        "must_include": [{"pattern": re.escape(e), "why": "from the user's correction"} for e in expected],
                        "notes": f"User correction: {corrections[0]}", "evidence": [t.get("id")], "reviewed": False})
    return out
