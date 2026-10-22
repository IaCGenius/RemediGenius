"""Offline evaluation: a fixture organization, deterministic desk checks, and read-only tool replay for agent tasks.

The fixture is built by the real pipeline (prioritize, knowledge, board), so a check that fails here fails for users.
Agent tasks are replayed by the Hermes-side runner; their tool calls come back through `exec`, which runs the normal
rgtriage commands against the fixture home with recorded AWS responses and no credentials.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .. import config, knowledge, okf, prioritize, store
from . import hints

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"
REF = re.compile(r"\{ref:([a-z0-9-]+)\}")
EXEC_ALLOWED = {"digest", "list", "show", "fix", "knowledge", "playbook", "aws", "report"}
EXEC_REFUSED = {
    "scan": "Scanning is not available in this evaluation: the fixture is a fixed snapshot. Use digest, list or show.",
    "watch": "Not available in this evaluation.",
    "decide": "Decisions are recorded only after the user approves them in Hermes; nothing was recorded in this evaluation.",
    "validate": "terraform validate is not run in this evaluation; say that the proposal should be validated.",
    "onboarding": "Account onboarding is not part of this evaluation fixture.",
    "doctor": "Not available in this evaluation.",
}


def improve_roots() -> list[Path]:
    roots = [Path(p) for p in os.environ.get("RGTRIAGE_IMPROVE_DIR", "").split(os.pathsep) if p]
    return roots + [Path("/opt/data/rg-improve"), config.home() / "rg-improve"]


def load_cases(path: Path | None = None) -> dict:
    """The shipped cases plus tasks a person reviewed from real conversations (rg-improve/cases/*.yaml, reviewed: true)."""
    cases = yaml.safe_load((path or EVALS / "cases.yaml").read_text(encoding="utf-8"))
    if path is None:
        seen = {t["id"] for t in cases.get("tasks", [])}
        for root in improve_roots():
            for f in sorted((root / "cases").glob("*.yaml")) if (root / "cases").is_dir() else []:
                try:
                    extra = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError:
                    continue
                if isinstance(extra, dict) and extra.get("reviewed") is True and extra.get("id") not in seen and extra.get("prompt"):
                    extra.setdefault("split", "train")
                    cases["tasks"].append(extra)
                    seen.add(extra["id"])
    return cases


def fixture_hash(name: str) -> str:
    h = hashlib.sha256()
    for base in (EVALS / name, ROOT / "knowledge_base", ROOT / "playbooks"):
        for p in sorted(base.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(ROOT).as_posix().encode())
                h.update(p.read_bytes())
    for module in ("prioritize.py", "knowledge.py", "digest.py", "okf.py"):
        h.update((ROOT / module).read_bytes())
    return h.hexdigest()[:16]


@contextlib.contextmanager
def _home(path: Path):
    saved = {k: os.environ.get(k) for k in ("RGTRIAGE_HOME", "RGTRIAGE_KNOWLEDGE", "RGTRIAGE_CONFIG")}
    os.environ["RGTRIAGE_HOME"] = str(path)
    os.environ.pop("RGTRIAGE_KNOWLEDGE", None)
    os.environ.pop("RGTRIAGE_CONFIG", None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def build(name: str, dest: Path) -> dict:
    """Build a fixture home with the real pipeline: knowledge, priorities, issues, board."""
    from .. import cli, collect  # cli imports this package lazily; avoid a cycle at import time

    src = EVALS / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    spec = yaml.safe_load((src / "fixture.yaml").read_text(encoding="utf-8"))
    profile = json.loads(json.dumps(spec["profile"]).replace("{home}", dest.as_posix()))
    (dest / "triage.yaml").write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
    for folder in ("iac", "aws"):
        if (src / folder).is_dir():
            shutil.copytree(src / folder, dest / folder)
    aliases = {}
    with _home(dest):
        knowledge.seed()
        b = knowledge.bundle()
        for concept_file in sorted((src / "knowledge").rglob("*.md")):
            target = b.root / concept_file.relative_to(src / "knowledge")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(concept_file.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        knowledge.reindex(b)
        findings = []
        for raw in json.loads((src / "findings.json").read_text(encoding="utf-8")):
            raw = dict(raw)
            alias = raw.pop("alias")
            f = collect.base_finding(raw.pop("source"), raw.pop("native_id"), **raw)
            aliases[alias] = f["key"]
            findings.append(f)
        known = knowledge.effective()
        findings, _ = prioritize.prioritize(findings, config.load(), {}, known)
        scan = {"version": "eval", "scanned_at": "2026-10-21T10:00:00Z",
                "profile": {"name": profile["name"], "accounts": [{"name": a["name"], "account_id": a["account_id"],
                            "criticality": a["criticality"]} for a in profile["accounts"]], "goals": []},
                "findings": findings, "coverage": spec["coverage"],
                "onboarding": {"mode": "standalone", "admin": {}, "full_read": [], "findings_only": [], "not_covered": [], "notes": []}}
        store.mark_changes(scan)
        scan["issues"] = prioritize.build_issues(findings)
        store.cap_findings(scan, 1000)
        store.save_scan(scan)
        scan["knowledge"] = knowledge.scan_summary(scan, known)
        store.write_latest(scan)
        cli.write_outputs(scan)
    meta = {"name": name, "hash": fixture_hash(name), "home": str(dest), "aliases": aliases}
    (dest / "eval-fixture.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def ensure(name: str) -> dict:
    """The fixture home for `name`, rebuilt when the fixture or the scoring code changed."""
    dest = config.home() / "improve" / "fixtures" / name
    marker = dest / "eval-fixture.json"
    if marker.exists():
        meta = json.loads(marker.read_text(encoding="utf-8"))
        if meta.get("hash") == fixture_hash(name):
            return meta
    return build(name, dest)


def substitute(value, aliases: dict):
    if isinstance(value, str):
        return REF.sub(lambda m: aliases.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [substitute(v, aliases) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, aliases) for k, v in value.items()}
    return value


def tasks(meta: dict, cases: dict | None = None) -> list[dict]:
    cases = cases or load_cases()
    return [substitute(t, meta["aliases"]) for t in cases.get("tasks", [])]


def known_paths(home: str) -> set[str]:
    b = okf.Bundle(Path(home) / "knowledge")
    return {c.path for c in b.concepts()}


def known_refs(home: str) -> set[str]:
    scan = json.loads((Path(home) / "latest.json").read_text(encoding="utf-8"))
    refs = {f["key"] for f in scan["findings"]} | {i["top_key"] for i in scan.get("issues", [])}
    return refs


def exec_tool(meta: dict, args: list[str], timeout: int = 120) -> dict:
    """Run one read-only rgtriage command against the fixture home with recorded AWS responses."""
    if not args:
        return {"rc": 2, "stdout": "", "stderr": "no command"}
    if args[0] in EXEC_REFUSED:
        return {"rc": 0, "stdout": EXEC_REFUSED[args[0]], "stderr": ""}
    if args[0] not in EXEC_ALLOWED:
        return {"rc": 2, "stdout": "", "stderr": f"{args[0]} is not available in this evaluation"}
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    env.update(RGTRIAGE_HOME=meta["home"], RGTRIAGE_EVAL_AWS=str(Path(meta["home"]) / "aws"), AWS_EC2_METADATA_DISABLED="true",
               AWS_CONFIG_FILE=os.devnull, AWS_SHARED_CREDENTIALS_FILE=os.devnull, PYTHONIOENCODING="utf-8",
               PYTHONPATH=str(ROOT.parent) + os.pathsep + env.get("PYTHONPATH", ""))
    env.pop("RGTRIAGE_KNOWLEDGE", None)
    env.pop("RGTRIAGE_CONFIG", None)
    try:
        proc = subprocess.run([sys.executable, "-m", "rgtriage", *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"rc": 124, "stdout": "", "stderr": "timed out"}
    return {"rc": proc.returncode, "stdout": proc.stdout[-30000:], "stderr": proc.stderr[-3000:]}


def suite(name: str | None = None) -> dict:
    """Deterministic checks of the desk on the fixture: priorities, citations, exceptions, coverage honesty, hints."""
    cases = load_cases()
    meta = ensure(name or cases["fixture"])
    home = Path(meta["home"])
    scan = json.loads((home / "latest.json").read_text(encoding="utf-8"))
    by_key = {f["key"]: f for f in scan["findings"]}
    board = (home / "digest.md").read_text(encoding="utf-8")
    with _home(home):
        concepts = knowledge.bundle().concepts()
        gaps_text = "\n".join(knowledge.gaps(scan))
    results = []
    for check in cases.get("checks", []):
        f = by_key.get(meta["aliases"].get(check.get("alias", ""), ""), {})
        problems = []
        if check.get("alias") and not f:
            problems.append(f"no finding with alias {check['alias']}")
        if "priority" in check and f.get("priority") not in check["priority"]:
            problems.append(f"priority {f.get('priority')} (score {f.get('score')}), expected {'/'.join(check['priority'])}")
        if "reason" in check and not any(check["reason"] in r for r in f.get("reasons", [])):
            problems.append(f"no reason contains {check['reason']!r}")
        if "owner" in check and (f.get("owner") or {}).get("title") != check["owner"]:
            problems.append(f"owner {(f.get('owner') or {}).get('title')!r}, expected {check['owner']!r}")
        if "decision" in check and (f.get("decision") or {}).get("status") != check["decision"]:
            problems.append(f"decision {(f.get('decision') or {}).get('status')!r}, expected {check['decision']!r}")
        if "ranks_above" in check:
            other = by_key.get(meta["aliases"].get(check["ranks_above"], ""), {})
            if f.get("score", 0) <= other.get("score", 0):
                problems.append(f"score {f.get('score')} not above {check['ranks_above']} ({other.get('score')})")
        if "board" in check and check["board"] not in board:
            problems.append(f"board lacks {check['board']!r}")
        if "board_not" in check and check["board_not"].lower() in board.lower():
            problems.append(f"board says {check['board_not']!r}")
        if {"skill", "practice", "fix_skill", "evidence"} & set(check):
            g = hints.guidance(f, knowledge.practices_for(f.get("control_id") or "", concepts))
            for key in ("skill", "fix_skill", "evidence"):
                if key in check and g.get(key) != check[key]:
                    problems.append(f"guidance {key} {g.get(key)}, expected {check[key]}")
            if "practice" in check and check["practice"] not in g["practices"]:
                problems.append(f"guidance practices {g['practices']}, expected {check['practice']}")
        if "fix" in check:
            out = exec_tool(meta, ["fix", f.get("key", "")])
            if check["fix"] not in out["stdout"]:
                problems.append(f"fix output lacks {check['fix']!r}")
        if "gap" in check and check["gap"] not in gaps_text:
            problems.append(f"knowledge gaps lack {check['gap']!r}")
        results.append({"id": check["id"], "ok": not problems, "problems": problems, "why": check.get("why", "")})
    return {"fixture": meta["name"], "passed": sum(r["ok"] for r in results), "total": len(results), "checks": results}
