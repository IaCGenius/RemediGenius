"""Desk results view on synthetic results (fake account 111122223333, no real data).

  python tests/test_results.py       # exits non-zero on any failure
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "profiles/desk/skills/remedigenius/results/scripts/results.py"


def finding(rule, sev):
    return {"rule_id": rule, "row_id": f"{rule}:global:x", "resource_id": "arn:aws:iam::111122223333:role/x",
            "scope": "global", "severity": sev, "evidence": {}, "fix_id": "FIX-IAMLP-01"}


def run(root, *args):
    env = {**os.environ, "RG_RESULTS_DIR": root}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


def main():
    fails = 0
    with tempfile.TemporaryDirectory() as root:
        def check(name, cond):
            nonlocal fails
            print(("ok   " if cond else "FAIL ") + name)
            fails += not cond

        check("empty root says NOT_RUN", "NOT_RUN" in run(root, "overview").stdout)
        base = {"mission": "B6", "status": {"status": "OK", "reason": ""},
                "scope": {"account": "111122223333", "regions": ["us-east-1"]}}
        for date, rows in (("2026-01-01", [finding("IAMLP-001", "critical")]),
                           ("2026-01-02", [finding("IAMLP-002", "high")]),
                           ("2026-01-02-direct", [finding("IAMLP-003", "low")])):
            Path(root, "t", date).mkdir(parents=True)
            Path(root, "t", date, "iam.json").write_text(json.dumps({**base, "findings": rows, "annotations": []}))
        out = run(root, "overview").stdout
        check("overview counts tenants", "Tenants assessed: 1" in out)
        check("overview uses latest dated run, ignores non-date folder", "runs: 2, latest 2026-01-02" in out)
        check("show filters by severity", "IAMLP-002" not in run(root, "show", "--tenant", "t", "--severity", "critical").stdout)
        d = run(root, "diff", "--tenant", "t").stdout
        check("diff finds new", "NEW: 1" in d and "IAMLP-002" in d)
        check("diff does not claim missing rows resolved", "NOT_OBSERVED: 1" in d and "RESOLVED: 1" not in d and "IAMLP-001" in d)
        check("unknown tenant exits 2", run(root, "show", "--tenant", "zz").returncode == 2)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
