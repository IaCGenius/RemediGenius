"""{{name}}: the smallest working kiosk function (kit hello)."""


def handle(unit, ctx):
    who = str((unit or {}).get("who", "world"))[:64]
    ctx.log("greeting", who=who)
    return {"status": "SUCCEEDED", "summary": {"greeting": f"hello {who}"}}
