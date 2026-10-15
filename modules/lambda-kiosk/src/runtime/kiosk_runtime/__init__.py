"""kiosk_runtime: the contract every kiosk function runs inside.

A function is `handle(unit, ctx) -> {"status": ..., "summary": {...}}`.
- `unit`: one JSON work order.
- `ctx`: deadline, output writer, logging with redaction, AWS clients with retries.

The same code runs in Lambda (`entry.main`), in a container task, in the gate's sandbox and in
`kiosk test` on the agent's side. `rules` holds the static checks shared by the gate and `kiosk test`.
"""

STATUSES = ("SUCCEEDED", "PARTIAL", "FAILED")
__version__ = "0.1.0"
