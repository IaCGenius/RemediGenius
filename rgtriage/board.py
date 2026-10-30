"""One board, two renderings: a 46-column card for chat and a self-contained page for a meeting.

Both come from the same `snapshot`, which is built from the stored scan only — no AWS calls, no second query engine.
The page is deliberately static: it stamps the snapshot and generation time and never pretends to be live. The chat
card is tied to the scan's age, so a six-hour-old board says it is six hours old instead of calling itself current.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone

from .digest import coverage_gaps
from .prioritize import is_open

STALE_HOURS = 6.0
BAR_CELLS = 12
WIDTH = 46
RULE = "─" * WIDTH
PRIORITIES = ("P1", "P2", "P3", "P4")
FIX_LABELS = {"decided": "decided", "pr": "in PR", "deployed": "deployed",
              "verified": "verified", "reopened": "reopened", "stalled": "stalled"}


def _at(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def age_text(seconds: float | None) -> str:
    if seconds is None:
        return "unknown age"
    minutes = int(seconds // 60)
    if minutes < 5:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h ago" if rest < 5 else f"{hours}h {rest}m ago"


def _coverage_cell(statuses: list[str]) -> str:
    if statuses and all(s == "ok" for s in statuses):
        return "ok"
    return "partial" if "ok" in statuses else "off"


def snapshot(scan: dict, *, now: datetime | None = None, stale_hours: float = STALE_HOURS) -> dict:
    """The one object both renderers consume. Every value is copied or counted, nothing is estimated."""
    when = _at(scan.get("scanned_at"))
    now = now or datetime.now(timezone.utc)
    seconds = round((now - when).total_seconds(), 3) if when else None
    issues = [i for i in scan.get("issues") or [] if is_open(i)]
    counts = Counter(i["priority"] for i in issues)
    changes = scan.get("changes") or {}
    coverage = [c for c in scan.get("coverage") or [] if c.get("region") != "-"]

    sources = sorted({c["source"] for c in coverage})
    accounts = sorted({c["account"] for c in coverage})
    cells = {}
    for c in coverage:
        cells.setdefault((c["account"], c["source"]), []).append(c.get("status"))
    matrix = [{"account": a, "sources": {s: _coverage_cell(cells.get((a, s), [])) for s in sources}}
              for a in accounts]

    fixes = scan.get("fixes") or []
    fix_counts = Counter(f.get("state") for f in fixes)
    verified = [f for f in fixes if f.get("state") == "verified"]
    profile = scan.get("profile") or {}
    onboarding = scan.get("onboarding") or {}
    # A single-account profile still knows about accounts discovery found but cannot read; the board says so.
    known = max(int(onboarding.get("known_accounts") or 0), len(profile.get("accounts") or []), len(accounts) or 1)
    regions = {c["region"] for c in coverage}
    enabled = set()
    for footprint in (scan.get("footprint") or {}).values():
        enabled |= set(footprint.get("enabled_regions") or [])

    ranked = sorted(issues, key=lambda i: (PRIORITIES.index(i["priority"]), -float(i.get("score") or 0)))
    top = [{"priority": i["priority"], "title": i.get("title", ""), "product": i.get("product", ""),
            "severity": i.get("severity", ""), "resource": ", ".join((i.get("resources") or [])[:2]) or "account-wide",
            "accounts": ", ".join(i.get("accounts") or []), "ref": i.get("top_key", ""),
            "why": [_why(r) for r in (i.get("reasons") or [])[1:3]]} for i in ranked[:6]]

    snap = {
        "name": profile.get("name") or "AWS", "scanned_at": scan.get("scanned_at"),
        "age_seconds": seconds, "age": age_text(seconds),
        "state": "empty" if not when else ("live" if seconds is not None and seconds <= stale_hours * 3600 else "stale"),
        "stale_hours": stale_hours,
        "open": sum(counts.values()), "counts": {p: counts.get(p, 0) for p in PRIORITIES},
        "changes": {"new": changes.get("new", 0), "urgent": changes.get("new_urgent", 0),
                    "cleared": changes.get("no_longer_active_count", 0),
                    "previous_scan": changes.get("previous_scan")},
        "coverage": {"accounts": len(accounts), "accounts_known": known,
                     "regions": len(regions), "regions_enabled": len(enabled) or len(regions),
                     "sources": sources, "sources_ok": len({c["source"] for c in coverage if c.get("status") == "ok"}),
                     "matrix": matrix, "gaps": coverage_gaps(scan)[:6],
                     "not_covered": len(onboarding.get("not_covered") or []),
                     "findings_only": len(onboarding.get("findings_only") or [])},
        "fixes": {"counts": {s: fix_counts.get(s, 0) for s in FIX_LABELS},
                  "verified": [{"title": f.get("title", ""), "resource": f.get("resource", ""),
                                "changed_at": f.get("changed_at")} for f in verified[:4]]},
        "top": top,
        "scope": ("The desk ranks what your AWS security services report, in the accounts, regions and sources above, "
                  "and checks live configuration when you ask. It has no detectors of its own: a quiet board means "
                  "nothing was reported there, not that nothing is wrong."),
    }
    digest = hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
    snap["snapshot"] = digest[:6]
    return snap


def _bar(count: int, largest: int) -> str:
    if not count:
        return ""
    return "█" * max(1, round(count / max(largest, 1) * BAR_CELLS))


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _why(reason: str) -> str:
    """Drop the score arithmetic; a reader wants the fact, not the points."""
    return re.sub(r" \(\+\d+\)$", "", str(reason))


def _short_gap(gap: str) -> str:
    """One readable line for the card: drop the note after an em dash and shorten the status words."""
    text = str(gap).split(" — ")[0]
    for long, short in (("API not available", "unavailable"), ("not enabled", "off"), ("access denied", "denied"),
                        ("read error", "error")):
        text = text.replace(long, short)
    return text


def card(snap: dict, width: int = WIDTH) -> str:
    """The chat card. Exact by construction; the prompt in SOUL.md produces the same shape."""
    rule = "─" * width
    counts, largest = snap["counts"], max(snap["counts"].values() or [1])
    state = {"live": "● LIVE", "stale": "○ STALE", "empty": "◌ DAY ONE"}[snap["state"]]
    lines = [f"{state}  REMEDIGENIUS · {_clip(snap['name'], width - 18)}",
             f"as of {str(snap['scanned_at'] or '')[11:16]} UTC · {snap['age']}", rule,
             f"OPEN   {' · '.join(f'{counts[p]} {p}' for p in PRIORITIES)}"]
    lines += [f"{p} {counts[p]:>3}  {_bar(counts[p], largest)}".rstrip() for p in PRIORITIES]
    if snap["state"] == "stale":
        lines += [rule, "NOT CURRENT OPERATIONAL STATE.", f"Last scan is older than {snap['stale_hours']:g} hours."]
    if snap["changes"]["previous_scan"]:
        change = snap["changes"]
        lines += [rule, (f"CHANGE +{change['new']} new · {change['urgent']} urgent · {change['cleared']} cleared"
                         if any(change[k] for k in ("new", "urgent", "cleared")) else
                         "CHANGE no change since the previous scan")]
    cov = snap["coverage"]
    lines += [rule, f"COVERAGE  {cov['accounts']}/{cov['accounts_known']} accounts · "
                    f"{cov['regions']}/{cov['regions_enabled']} regions",
              f"          {_clip(_short_gap(cov['gaps'][0]) if cov['gaps'] else 'all configured sources read', width - 10)}"]
    fix_parts = [f"{n} {FIX_LABELS[s]}" for s, n in snap["fixes"]["counts"].items() if n]
    if fix_parts:
        lines += [rule, f"FIXES     {_clip(' · '.join(fix_parts), width - 10)}"]
    if snap["top"]:
        head = snap["top"][0]
        lines += [rule, f"NEXT      {_clip(head['title'], width - 10)} ({head['priority']})",
                  f"          \"why {head['ref']}\" · \"fix {head['ref']}\""]
    return "\n".join(lines)


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def page(snap: dict, *, generated_at: datetime | None = None) -> str:
    """A single self-contained HTML page: no external assets, no scripts, prints on A4."""
    generated = (generated_at or datetime.now(timezone.utc)).strftime("%d %b %Y, %H:%M UTC")
    counts = snap["counts"]
    total = max(snap["open"], 1)
    cov = snap["coverage"]
    state_label = {"live": "live", "stale": "stale", "empty": "day one"}[snap["state"]]
    fixes = snap["fixes"]["counts"]
    verified_total = sum(fixes.values())
    tiles = [("P1 open", counts["P1"], "act now"), ("P2 open", counts["P2"], "this week"),
             ("fixes verified", fixes.get("verified", 0),
              f"of {verified_total} tracked" if verified_total else "none tracked yet"),
             ("accounts", (f"{cov['accounts']}/{cov['accounts_known']}" if cov["accounts_known"] != cov["accounts"]
                           else str(cov["accounts"])),
              "account inspected" if cov["accounts"] == 1 else "accounts inspected")]
    kpis = "".join(f'<div class="kpi"><div class="n">{_esc(value)}</div><div class="l">{_esc(label)} · {_esc(note)}</div></div>'
                   for label, value, note in tiles)
    sev = "".join(f'<i style="width:{counts[p] / total * 100:.1f}%;background:var(--{p.lower()})"></i>' for p in PRIORITIES)
    legend = "".join(f'<span><i class="dot" style="background:var(--{p.lower()})"></i><b>{counts[p]}</b> {p}</span>'
                     for p in PRIORITIES)
    change = snap["changes"]
    change_text = (f"+{change['new']} new ({change['urgent']} urgent) · {change['cleared']} cleared"
                   if any(change[k] for k in ("new", "urgent", "cleared")) else "no change since the previous scan") \
        if change["previous_scan"] else "first scan — no previous board to compare"
    decisions = "".join(
        f'<tr><td><span class="pill {item["priority"].lower()}">{item["priority"]}</span> <b>{_esc(item["title"])}</b>'
        f'<div class="why">{_esc("; ".join(item["why"]) or item["product"])}</div></td>'
        f'<td class="r"><span class="ref">{_esc(item["ref"])}</span><div class="why">{_esc(item["resource"])}</div></td></tr>'
        for item in snap["top"][:4]) or '<tr><td class="why">Nothing open.</td></tr>'
    head = "".join(f"<th>{_esc(s)}</th>" for s in cov["sources"])
    rows = "".join(
        f'<tr><td>{_esc(row["account"])}</td>' +
        "".join(f'<td><span class="dot {row["sources"][s]}" title="{row["sources"][s]}"></span></td>' for s in cov["sources"]) +
        "</tr>" for row in cov["matrix"])
    gaps = "".join(f"<li>{_esc(g)}</li>" for g in cov["gaps"]) or "<li>No gap recorded for the sources read.</li>"
    verified = "".join(f'<tr><td><b>{_esc(f["title"])}</b><div class="why">{_esc(f["resource"])}</div></td>'
                       f'<td class="r proof">verified</td></tr>' for f in snap["fixes"]["verified"]) or \
        '<tr><td class="why">No fix has been proven by read-back yet.</td></tr>'
    fix_summary = f"{fixes.get('verified', 0)} fix{'es' if fixes.get('verified', 0) != 1 else ''} verified"
    if fixes.get("deployed"):
        fix_summary += f", {fixes['deployed']} deployed awaiting AWS"
    return PAGE.replace("__NAME__", _esc(snap["name"])).replace("__STATE__", state_label) \
        .replace("__STATE_CLASS__", "stale" if snap["state"] == "stale" else "") \
        .replace("__SNAPSHOT__", _esc(snap["snapshot"])).replace("__WHEN__", _esc(str(snap["scanned_at"] or "")[:16].replace("T", " "))) \
        .replace("__AGE__", _esc(snap["age"])).replace("__GENERATED__", _esc(generated)) \
        .replace("__KPIS__", kpis).replace("__SEV__", sev).replace("__LEGEND__", legend) \
        .replace("__CHANGE__", _esc(change_text)).replace("__DECISIONS__", decisions) \
        .replace("__HEAD__", head).replace("__ROWS__", rows).replace("__GAPS__", gaps) \
        .replace("__VERIFIED__", verified).replace("__SCOPE__", _esc(snap["scope"])) \
        .replace("__FIX_SUMMARY__", _esc(fix_summary))


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="rgce-snapshot" content="__SNAPSHOT__"><title>RemediGenius board — __NAME__</title><style>
:root{--bg:#faf9f6;--panel:#fff;--ink:#17171a;--muted:#6b6b66;--line:#e4e2db;--chip:#f1efe9;
--mono:ui-monospace,SFMono-Regular,"Cascadia Mono","Segoe UI Mono",Menlo,Consolas,monospace;
--p1:#b42318;--p2:#c4320a;--p3:#a15c07;--p4:#5d6b82;--ok:#1f7a58;--warn:#b54708}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--panel:#1b1b19;--ink:#ecebe6;--muted:#a3a29c;--line:#2e2e2a;
--chip:#242420;--p1:#f97066;--p2:#fd853a;--p3:#fdb022;--p4:#98a2b3;--ok:#5bd6a4;--warn:#fdb022}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.board{max-width:1080px;margin:24px auto;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
header{padding:22px 24px 16px;border-bottom:1px solid var(--line)}.eyebrow{font:11px/1 var(--mono);letter-spacing:.1em;
text-transform:uppercase;color:var(--muted);margin-bottom:8px}h1{font-size:22px;margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px}.pill{display:inline-flex;align-items:center;font:12px/1 ui-monospace,monospace;
padding:5px 9px;border-radius:999px;border:1px solid var(--ok);color:var(--ok);margin-left:8px;vertical-align:2px}
.pill.stale{border-color:var(--warn);color:var(--warn)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));border-bottom:1px solid var(--line)}
.kpi{padding:18px 24px;border-right:1px solid var(--line)}.kpi:last-child{border-right:0}.kpi .n{font:600 30px/1.1 ui-monospace,monospace;letter-spacing:-.03em}
.kpi .n small{font-size:18px;color:var(--muted);font-weight:500}.kpi .l{font-size:12px;color:var(--muted);margin-top:6px}
.body{padding:20px 24px 24px;display:grid;gap:24px}h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin:0 0 12px;font-weight:650}
.sev{display:flex;height:14px;border-radius:7px;overflow:hidden;background:var(--chip);border:1px solid var(--line)}.sev i{display:block;height:100%}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:12.5px;color:var(--muted)}.legend b{font:600 12.5px ui-monospace,monospace;color:var(--ink)}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--muted)}.dot.ok{background:var(--ok)}.dot.partial{background:var(--warn)}.dot.off{background:var(--p1)}
table{width:100%;border-collapse:collapse;font-size:13.5px}th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
text-align:left;font-weight:600;padding:0 10px 8px 0;border-bottom:1px solid var(--line)}td{padding:9px 10px 9px 0;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}.r{text-align:right}.ref{font:12px ui-monospace,monospace;color:var(--muted)}.why{color:var(--muted);font-size:12.5px;margin-top:2px}
.pill.p1{color:var(--p1);border-color:var(--p1)}.pill.p2{color:var(--p2);border-color:var(--p2)}.pill.p3{color:var(--p3);border-color:var(--p3)}.pill.p4{color:var(--p4);border-color:var(--p4)}
.cov td:not(:first-child),.cov th:not(:first-child){text-align:center;width:70px}.proof{color:var(--ok);font:12px ui-monospace,monospace}
.two{display:grid;grid-template-columns:1.1fr .9fr;gap:24px}@media(max-width:760px){.two{grid-template-columns:1fr}}
footer{padding:16px 24px 22px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}footer b{color:var(--ink)}
ul{margin:0;padding-left:18px}li{margin:3px 0}@media print{body{background:#fff}.board{border:0;margin:0}.sev,.dot{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body><main class="board">
<header><div class="eyebrow">Security attention board</div>
<h1>__NAME__ <span class="pill __STATE_CLASS__">__STATE__</span></h1>
<div class="sub">Snapshot __SNAPSHOT__ · scanned __WHEN__ UTC (__AGE__) · generated __GENERATED__</div></header>
<div class="kpis">__KPIS__</div><div class="body">
<section><h2>Open issues by priority</h2><div class="sev">__SEV__</div>
<div class="legend">__LEGEND__<span style="margin-left:auto">__CHANGE__</span></div></section>
<div class="two"><section><h2>Needs a decision</h2><table>__DECISIONS__</table></section>
<section><h2>Verified fixes</h2><table>__VERIFIED__</table></section></div>
<section><h2>Coverage — absence of findings is not a clean bill of health</h2>
<table class="cov"><thead><tr><th>Account</th>__HEAD__</tr></thead><tbody>__ROWS__</tbody></table>
<div class="legend"><span><i class="dot ok"></i>read</span><span><i class="dot partial"></i>partial or capped</span>
<span><i class="dot off"></i>not enabled / not covered</span></div><ul style="margin-top:10px">__GAPS__</ul></section>
</div><footer><b>Scope.</b> __SCOPE__<br><br><b>Static snapshot</b> __SNAPSHOT__, generated __GENERATED__.
Re-run <span class="ref">rgtriage board</span> for the current one. __FIX_SUMMARY__.</footer>
</main></body></html>"""