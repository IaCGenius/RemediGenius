"""Read-only view over the analyst's SkillResult files, for the desk agent.

  python3 results.py overview
  python3 results.py show --tenant T [--date YYYY-MM-DD] [--severity critical,high]
  python3 results.py diff --tenant T
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.environ.get("RG_RESULTS_DIR", "/opt/data/results")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEVERITIES = ("critical", "high", "medium", "low", "info")


def tenants():
    if not os.path.isdir(ROOT):
        return []
    return sorted(d for d in os.listdir(ROOT) if os.path.isdir(os.path.join(ROOT, d)))


def runs(tenant):
    path = os.path.join(ROOT, tenant)
    return sorted(d for d in os.listdir(path) if DATE.match(d) and os.path.isdir(os.path.join(path, d)))


def load(tenant, date):
    out = {}
    folder = os.path.join(ROOT, tenant, date)
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                out[name[:-5]] = json.load(fh)
        except (OSError, ValueError) as exc:
            out[name[:-5]] = {"status": {"status": "ERROR", "reason": f"unreadable: {exc}"}, "findings": []}
    return out


def sev_line(findings):
    c = Counter(f.get("severity") for f in findings)
    return ", ".join(f"{c[s]} {s}" for s in SEVERITIES if c[s]) or "none"


def overview(_):
    ts = tenants()
    if not ts:
        print("No results yet (NOT_RUN): nothing under", ROOT)
        return
    print(f"Tenants assessed: {len(ts)}")
    for t in ts:
        rs = runs(t)
        if not rs:
            print(f"\n{t}: NOT_RUN (no dated run)")
            continue
        res = load(t, rs[-1])
        scope = next((r["scope"] for r in res.values() if r.get("scope")), {})
        allf = [f for r in res.values() for f in r.get("findings", [])]
        print(f"\n{t}  (account {scope.get('account', '?')}, regions {','.join(scope.get('regions', [])) or '?'})")
        print(f"  runs: {len(rs)}, latest {rs[-1]}")
        print(f"  findings: {len(allf)} ({sev_line(allf)})")
        for name, r in res.items():
            st = r.get("status", {})
            fs = r.get("findings", [])
            reason = f" - {st['reason']}" if st.get("reason") else ""
            print(f"  - {name} [{r.get('mission', '?')}]: {st.get('status', '?')}{reason}; "
                  f"{len(fs)} findings ({sev_line(fs)}), {len(r.get('annotations', []))} explained")


def show(a):
    rs = runs(a.tenant)
    date = a.date or (rs[-1] if rs else None)
    if not date:
        print(f"{a.tenant}: NOT_RUN")
        return
    want = set(a.severity.split(",")) if a.severity else set(SEVERITIES)
    print(f"{a.tenant} run {date}")
    for name, r in load(a.tenant, date).items():
        notes = {x["row_id"]: x for x in r.get("annotations", [])}
        for f in r.get("findings", []):
            if f.get("severity") not in want:
                continue
            print(f"\n[{f['severity'].upper()}] {f['rule_id']} {f['resource_id']} ({f['scope']}) - {name}")
            n = notes.get(f["row_id"])
            if n:
                print(f"  why: {n['explanation']}\n  impact: {n['impact']}\n  next: {n['next_step']}")
            else:
                print("  (no explanation yet)")


def diff(a):
    rs = runs(a.tenant)
    if len(rs) < 2:
        print(f"{a.tenant}: only {len(rs)} run(s); nothing to compare yet")
        return

    def rows(date):
        return {f["row_id"]: f for r in load(a.tenant, date).values() for f in r.get("findings", [])}

    old, new = rows(rs[-2]), rows(rs[-1])
    print(f"{a.tenant}: {rs[-2]} -> {rs[-1]}")
    print("Missing rows are NOT_OBSERVED, not proven resolved; this legacy format has no coverage receipt.")
    for label, keys, src in (("NEW", new.keys() - old.keys(), new), ("NOT_OBSERVED", old.keys() - new.keys(), old)):
        print(f"\n{label}: {len(keys)}")
        for k in sorted(keys, key=lambda k: SEVERITIES.index(src[k]["severity"])):
            print(f"  [{src[k]['severity']}] {src[k]['rule_id']} {src[k]['resource_id']}")
    print(f"\nunchanged: {len(new.keys() & old.keys())}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("overview").set_defaults(fn=overview)
    s = sub.add_parser("show")
    s.add_argument("--tenant", required=True)
    s.add_argument("--date")
    s.add_argument("--severity")
    s.set_defaults(fn=show)
    d = sub.add_parser("diff")
    d.add_argument("--tenant", required=True)
    d.set_defaults(fn=diff)
    a = p.parse_args()
    if getattr(a, "tenant", None) and a.tenant not in tenants():
        print(f"unknown tenant {a.tenant}; known: {', '.join(tenants()) or 'none'}")
        sys.exit(2)
    a.fn(a)


if __name__ == "__main__":
    main()
