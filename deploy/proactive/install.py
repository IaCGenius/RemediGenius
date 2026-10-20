"""Run inside the Hermes container with HERMES_HOME set to the ce-desk profile.

Installs native cron jobs once. Existing named jobs are preserved, including pauses.
--bootstrap queues one initial run. No credentials or provider settings are changed.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, "/opt/hermes")
from cron.jobs import create_job, list_jobs, update_job

parser = argparse.ArgumentParser()
parser.add_argument("--bootstrap", action="store_true")
args = parser.parse_args()
home = Path(os.environ["HERMES_HOME"])
if home.name != "ce-desk":
    raise SystemExit("Select HERMES_HOME for ce-desk before installing jobs")
scripts = home / "scripts"
scripts.mkdir(parents=True, exist_ok=True)
shutil.copy2(Path(__file__).with_name("heartbeat.py"), scripts / "rgce-heartbeat.py")
existing = {job.get("name"): job for job in list_jobs(include_disabled=True)}
definitions = [
    ("RemediGenius heartbeat", "*/15 * * * *", None),
    ("RemediGenius hourly", "7 * * * *", "hourly"),
    ("RemediGenius monthly", "13 3 1 * *", "monthly"),
]
bootstrap_marker = home / "cron" / "rgce-bootstrap-registered.json"
if args.bootstrap and not bootstrap_marker.exists():
    definitions.append(("RemediGenius bootstrap", "1m", "bootstrap"))
for name, schedule, mode in definitions:
    if name in existing:
        if mode in ("hourly", "monthly") and not existing[name].get("context_from"):
            update_job(existing[name]["id"], {"context_from": [existing[name]["id"]]})
        if mode == "bootstrap":
            bootstrap_marker.write_text(json.dumps({"id": existing[name]["id"]}))
        print(json.dumps({"name": name, "result": "preserved", "id": existing[name]["id"]}))
        continue
    options = dict(name=name, schedule=schedule, deliver="local",
                   enabled_toolsets=["skills", "ce_runtime"])
    if mode is None:
        options.update(prompt=None, script=str(scripts / "rgce-heartbeat.py"), no_agent=True)
    else:
        options.update(
            prompt=f"Run ce-proactive-security mode {mode}. This is an unattended scheduled run. "
                   "Stay within the current account, us-east-1, and one bounded investigation. "
                   "Bootstrap uses max_reads=3; hourly uses max_reads=4. "
                   "Keep calling ce_assessment next until terminal; do not interleave independent tools. "
                   "Record questions for the operator; do not wait for clarification. "
                   "Use saved evidence and confirmed knowledge. Report a useful decision brief.",
            skills=["ce-proactive-security"])
        if mode == "bootstrap":
            options["repeat"] = 1
    job = create_job(**options)
    if mode in ("hourly", "monthly"):
        update_job(job["id"], {"context_from": [job["id"]]})
    if mode == "bootstrap":
        bootstrap_marker.write_text(json.dumps({"id": job["id"]}))
    print(json.dumps({"name": name, "result": "created", "id": job["id"]}))
