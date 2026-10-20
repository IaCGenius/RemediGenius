"""Native Hermes no-agent heartbeat. Reads the saved baseline; no AWS API/model."""
import json
import os
from pathlib import Path
import datetime

root = Path(os.environ.get("HERMES_HOME", "/opt/data/profiles/ce-desk"))
status = Path("/opt/data/work/ACCOUNT-STATUS.md")
if (root / "secagent" / "STOP").exists():
    print("STOPPED: pause RemediGenius agent jobs on the Cron page.")
elif not status.exists():
    print("BASELINE_UNAVAILABLE: inspect the collector service; no scan was attempted.")
else:
    fields = dict(line.split(": ", 1) for line in status.read_text().splitlines()
                  if line.startswith(("Observed: ", "Next expected refresh: ", "Run status: ")))
    due = datetime.datetime.fromisoformat(fields["Next expected refresh"])
    stale = datetime.datetime.now(datetime.timezone.utc) > due
    print(json.dumps({"status": "BASELINE_STALE" if stale else "BASELINE_PRESENT",
                      "collection_status": fields["Run status"], "observed_at": fields["Observed"],
                      "next_expected_refresh": fields["Next expected refresh"], "path": str(status),
                      "note": "Presence is not a coverage or security verdict."}))
