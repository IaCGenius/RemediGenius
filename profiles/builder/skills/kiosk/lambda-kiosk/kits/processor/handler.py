"""{{name}} (kit processor): validate the unit, process records, write one output, return a short summary.

Contract: handle(unit, ctx) -> {"status": SUCCEEDED | PARTIAL | FAILED, "summary": {...small...}, "reason": "..."}.
Big data goes to ctx.write_json(name, obj) (outputs/<agent>/<function>/<run_id>/<unit_index>/<name>), never in the summary.
Stop early when ctx.should_stop() is true and return PARTIAL with what is done.
"""


def handle(unit, ctx):
    records = (unit or {}).get("records")
    if not isinstance(records, list):
        return {"status": "FAILED", "reason": "unit.records must be a list", "summary": {}}
    done, bad = [], 0
    for r in records:
        if ctx.should_stop():
            ctx.write_json("result.json", {"processed": done, "complete": False})
            return {"status": "PARTIAL", "reason": "deadline", "summary": {"processed": len(done), "invalid": bad}}
        if not isinstance(r, dict) or not isinstance(r.get("value"), (int, float)):
            bad += 1
            continue
        done.append({"id": r.get("id"), "value": r["value"], "double": r["value"] * 2})
    total = sum(x["value"] for x in done)
    ctx.write_json("result.json", {"processed": done, "complete": True, "total": total})
    status = "SUCCEEDED" if bad == 0 else "PARTIAL"
    return {"status": status, "summary": {"processed": len(done), "invalid": bad, "total": total}}
