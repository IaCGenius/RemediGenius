"""Render the triage queue for people: a short markdown attention board and an HTML report."""
from __future__ import annotations

import html
import re
import json
from collections import Counter

from .accounts import summary_lines
from .knowledge import board_lines
from .prioritize import is_open

PRIORITY_HEADINGS = {"P1": "P1 — act now", "P2": "P2 — fix this week", "P3": "P3 — backlog", "P4": "P4 — monitor"}


def _when(value: str) -> str:
    return str(value or "")[:16].replace("T", " ")


def _reason(text: str) -> str:
    return re.sub(r" \([+-]\d+\)$", "", text)


def _resources(issue: dict) -> str:
    names = issue["resources"][:3]
    more = issue["resource_count"] - len(names)
    text = ", ".join(f"`{n}`" for n in names) or "account-wide"
    return text + (f" +{more} more" if more > 0 else "")


def summary_line(scan: dict) -> str:
    open_issues = [i for i in scan["issues"] if is_open(i)]
    counts = Counter(i["priority"] for i in open_issues)
    return (f"{counts.get('P1', 0)} P1 · {counts.get('P2', 0)} P2 · {counts.get('P3', 0)} P3 · {counts.get('P4', 0)} P4 "
            f"open issues from {len(scan['findings'])} findings")


def coverage_gaps(scan: dict) -> list[str]:
    grouped: dict[tuple, list] = {}
    for c in scan["coverage"]:
        if c["status"] != "ok":
            grouped.setdefault((c["source"], c["status"], c["account"]), []).append(c)
    gaps = []
    for (source, status, account), items in grouped.items():
        label = {"not_enabled": "not enabled", "denied": "access denied", "error": "read error",
                 "not_available": "API not available"}.get(status, status)
        regions = ", ".join(sorted(c["region"] for c in items))
        notes = {c.get("note", "")[:120] for c in items if c.get("note")}
        note = f" — {notes.pop()}" if len(notes) == 1 else ""
        gaps.append(f"{source} {label} in {account}: {regions}{note}")
    return gaps


def markdown(scan: dict, limit: int = 5, include_low: bool = False) -> str:
    profile = scan.get("profile", {})
    accounts = sorted({c["account"] for c in scan["coverage"]})
    regions = sorted({c["region"] for c in scan["coverage"] if c["region"] not in ("-",)})
    ch = scan.get("changes", {})
    lines = [
        f"# Security attention board — {profile.get('name', 'AWS')}",
        f"Scanned {_when(scan['scanned_at'])} UTC · accounts: {', '.join(accounts)} · regions: {', '.join(regions)}",
        f"**{summary_line(scan)}**",
    ]
    if ch.get("previous_scan"):
        gone = ch.get("no_longer_active_count", len(ch.get("no_longer_active", [])))
        lines.append(f"Since previous scan ({_when(ch['previous_scan'])}): {ch.get('new', 0)} new findings "
                     f"({ch.get('new_urgent', 0)} P1/P2), {gone} no longer active.")
    for b in ch.get("new_sources") or []:
        lines.append(f"Newly readable: {b['source']} in {b['account']}/{b['region']} — {b['total']:,} existing findings "
                     "taken as the baseline (not counted as new).")
    open_issues = [i for i in scan["issues"] if is_open(i)]
    for priority in ("P1", "P2", "P3", "P4"):
        items = [i for i in open_issues if i["priority"] == priority]
        if not items:
            continue
        if priority in ("P3", "P4") and not include_low:
            top = "; ".join(i["title"][:90] for i in items[:3])
            lines.append(f"\n## {PRIORITY_HEADINGS[priority]} ({len(items)} issues)\n{top}{' …' if len(items) > 3 else ''}")
            continue
        lines.append(f"\n## {PRIORITY_HEADINGS[priority]} ({len(items)} issues)")
        for n, issue in enumerate(items[:limit], 1):
            new = " 🆕" if issue.get("new") else ""
            status = f" · status: {issue['decision']['status']}" if issue.get("decision") else ""
            owner = f" · owner {issue['owner']['title']}" if issue.get("owner") else ""
            ident = issue["control_id"] or issue["type"] or ""
            lines.append(
                f"{n}. **{issue['title'][:110]}**{new} — {issue['product']} {issue['severity']}"
                f"{' · ' + ident if ident else ''} · {issue['finding_count']} finding(s) on {_resources(issue)}"
                f" · account {', '.join(issue['accounts'])}{owner}{status}\n"
                f"   Why {priority}: {'; '.join(_reason(r) for r in issue['reasons'][1:5]) or issue['reasons'][0]}\n"
                f"   Ref: `{issue['top_key']}`")
        if len(items) > limit:
            lines.append(f"   …and {len(items) - limit} more {priority} issues (`rgtriage list --priority {priority}`)")
    closed = len(scan["issues"]) - len(open_issues)
    if closed:
        lines.append(f"\n{closed} issues hidden by operator decisions (accepted risk / suppressed / resolved).")
    gaps = coverage_gaps(scan)
    lines.append("\n## Coverage")
    ok = [c for c in scan["coverage"] if c["status"] == "ok"]
    lines.append(f"Read OK: {', '.join(sorted({c['source'] for c in ok})) or 'nothing'}.")
    lines.extend(summary_lines(scan.get("onboarding") or {}))
    lines.extend(volume_lines(scan))
    if gaps:
        lines.append("Gaps (absence of findings here is NOT a clean bill of health):")
        lines.extend(f"- {g}" for g in gaps[:12])
    knowledge = board_lines(scan)
    if knowledge:
        lines.append("\n## Knowledge")
        lines.extend(knowledge)
    return "\n".join(lines)


def volume_lines(scan: dict) -> list[str]:
    """Totals for high-volume sources, what was read in detail, and the fixes that clear the most."""
    lines = []
    for c in scan["coverage"]:
        if c["status"] != "ok" or not (c.get("truncated") or c.get("total", 0) > 500):
            continue
        counts = c.get("counts") or {}
        sev = " · ".join(f"{counts[k]:,} {k.lower()}" for k in ("CRITICAL", "HIGH", "MEDIUM") if counts.get(k))
        if c["source"] == "inspector":
            lines.append(f"- inspector {c['account']}/{c['region']}: {c.get('total', 0):,} open findings ({sev}); "
                         f"{c.get('detailed', 0):,} critical/high/exploitable read in detail, the rest summarized by AMI, "
                         "ECR repository and Lambda function.")
            pkgs = ", ".join(f"{p['package']} ({p['all']:,})" for p in (c.get("top_packages") or [])[:5] if p.get("package"))
            if pkgs:
                lines.append(f"  Packages behind the most findings: {pkgs}")
        elif c["source"] == "securityhub":
            capped = ", ".join(s.lower() for s in c.get("truncated_severities") or [])
            lines.append(f"- securityhub {c['account']}/{c['region']}: read {c.get('count', 0):,} findings"
                         + (f"; {capped} capped at the configured detail limit — counts there are 'at least'" if capped else ""))
        else:
            lines.append(f"- {c['source']} {c['account']}/{c['region']}: {c.get('total', c.get('count', 0)):,} findings"
                         + (" (capped)" if c.get("truncated") else ""))
    if scan.get("stored_overflow"):
        lines.append(f"- {scan['stored_overflow']:,} lower-ranked findings were read but not stored (max_stored_findings).")
    return (["Volume:"] + lines) if lines else []


HTML_ROW_LIMIT = 5000


def html_report(scan: dict) -> str:
    rows = []
    for f in scan["findings"][:HTML_ROW_LIMIT]:
        rows.append({
            "key": f["key"], "priority": f["priority"], "score": f["score"], "severity": f["severity"],
            "source": f["product"], "category": f["category"], "title": f["title"], "control": f.get("control_id") or f.get("type", ""),
            "resource": f["resource"].get("name") or f["resource"].get("id"), "rtype": f["resource"].get("type"),
            "account": f["account"], "region": f["region"], "last_seen": _when(f.get("last_seen")),
            "why": f["reasons"], "url": f.get("console_url", ""), "new": f.get("new", False),
            "decision": (f.get("decision") or {}).get("status", ""), "open": is_open(f),
        })
    data = json.dumps(rows, default=str).replace("</", "<\\/")
    gaps = "".join(f"<li>{html.escape(g)}</li>" for g in coverage_gaps(scan)) or "<li>None recorded</li>"
    title = html.escape(f"Security attention board — {scan.get('profile', {}).get('name', 'AWS')}")
    return TEMPLATE.replace("__TITLE__", title).replace("__SUMMARY__", html.escape(summary_line(scan))) \
        .replace("__SCANNED__", html.escape(_when(scan["scanned_at"]))).replace("__GAPS__", gaps).replace("__DATA__", data)


TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e3e2dd;--p1:#b42318;--p2:#c4320a;--p3:#a15c07;--p4:#5d6b82}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--muted:#a3a29c;--card:#1d1d1b;--line:#33332f;--p1:#f97066;--p2:#fd853a;--p3:#fdb022;--p4:#98a2b3}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:16px}
h1{font-size:20px;margin:8px 0}.muted{color:var(--muted)}.bar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
select,input{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line)}th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600}.pill{font-weight:700}.P1{color:var(--p1)}.P2{color:var(--p2)}.P3{color:var(--p3)}.P4{color:var(--p4)}
details summary{cursor:pointer}code{font-size:12px}.wrap{overflow-x:auto}a{color:inherit}</style></head><body><main>
<h1>__TITLE__</h1><div class="muted">Scanned __SCANNED__ UTC · __SUMMARY__</div>
<details><summary>Coverage gaps</summary><ul>__GAPS__</ul></details>
<div class="bar"><select id="p"><option value="">All priorities</option><option>P1</option><option>P2</option><option>P3</option><option>P4</option></select>
<select id="s"><option value="">All sources</option></select><label><input type="checkbox" id="o" checked> open only</label>
<input id="q" placeholder="Search title, resource, control"></div>
<div class="wrap"><table><thead><tr><th>Priority</th><th>Finding</th><th>Resource</th><th>Source</th><th>Account / region</th><th>Last seen</th></tr></thead><tbody id="t"></tbody></table></div>
</main><script>
const rows=__DATA__;const $=id=>document.getElementById(id);
[...new Set(rows.map(r=>r.source))].sort().forEach(s=>{const o=document.createElement('option');o.textContent=s;$('s').appendChild(o)});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function draw(){const p=$('p').value,s=$('s').value,q=$('q').value.toLowerCase(),o=$('o').checked;
$('t').innerHTML=rows.filter(r=>(!p||r.priority==p)&&(!s||r.source==s)&&(!o||r.open)&&(!q||(r.title+r.resource+r.control).toLowerCase().includes(q)))
.map(r=>`<tr><td class="pill ${r.priority}">${r.priority}<div class="muted">${r.score}</div></td><td>${r.new?'🆕 ':''}${r.url?`<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`:esc(r.title)}
<div class="muted">${esc(r.control)} · ${esc(r.severity)} · ${esc(r.category)}${r.decision?' · '+esc(r.decision):''}</div><details><summary class="muted">why</summary>${r.why.map(esc).join('<br>')}<br><code>${r.key}</code></details></td>
<td>${esc(r.resource)}<div class="muted">${esc(r.rtype)}</div></td><td>${esc(r.source)}</td><td>${esc(r.account)}<div class="muted">${esc(r.region)}</div></td><td>${esc(r.last_seen)}</td></tr>`).join('')}
['p','s','q','o'].forEach(id=>$(id).addEventListener('input',draw));draw();</script></body></html>"""
