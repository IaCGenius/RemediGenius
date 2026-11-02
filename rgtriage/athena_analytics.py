"""Bounded security-history reports through the upstream Athena MCP worker."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone

REPORTS = ("trend", "coverage", "verification", "scan_coverage")


def query(report, days, installation, snapshots, account=None, region=None):
    if report not in REPORTS or type(days) is not int or not 1 <= days <= 90:
        raise ValueError("Choose a supported analytics report and 1–90 days")
    if not re.fullmatch(r"[a-zA-Z0-9-]{1,80}", installation):
        raise ValueError("Invalid installation identity")
    if account and not re.fullmatch(r"\d{12}", account):
        raise ValueError("Analytics account must be a 12-digit account ID")
    if region and not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", region):
        raise ValueError("Invalid analytics region")

    def table(name):
        snapshot = snapshots[name]
        if snapshot is None:
            return name
        if not isinstance(snapshot, int) or snapshot < 0:
            raise ValueError("Invalid Iceberg snapshot")
        return f"{name} FOR VERSION AS OF {snapshot}"

    def where(clock="observed_at", scoped=True):
        terms = [f"installation_id = '{installation}'", f"{clock} >= current_timestamp - INTERVAL '{days}' DAY"]
        if scoped and account:
            terms.append(f"account_id = '{account}'")
        if scoped and region:
            terms.append(f"region = '{region}'")
        return " AND ".join(terms)

    if report == "trend":
        return (f"SELECT event_day, count(DISTINCT event_id) AS observations, "
                f"count(DISTINCT ce.finding_key) AS distinct_findings FROM {table('findings')} "
                f"WHERE {where('ingested_at')} GROUP BY event_day ORDER BY event_day DESC LIMIT 90")
    if report == "coverage":
        return (f"SELECT source, status, count(*) AS collection_checks, count_if(truncated) AS truncated_checks "
                f"FROM (SELECT DISTINCT event_id, source, status, truncated FROM {table('coverage')} "
                f"WHERE {where()}) GROUP BY source,status ORDER BY source,status LIMIT 100")
    if report == "verification":
        scope = where('ingested_at', scoped=False)
        if account:
            scope += f" AND target.account_id = '{account}'"
        if region:
            scope += f" AND target.region = '{region}'"
        return (f"SELECT outcome, count(DISTINCT event_id) AS attempts FROM {table('verification_attempts')} "
                f"WHERE {scope} GROUP BY outcome ORDER BY outcome LIMIT 100")
    if account or region:
        raise ValueError("scan_coverage reports installation-wide scan counts; use coverage for account/region scope")
    return (f"WITH c AS (SELECT run_id, count(*) AS source_checks, "
            f"count_if(status <> 'ok' OR truncated) AS gaps FROM "
            f"(SELECT DISTINCT event_id, run_id, status, truncated FROM {table('coverage')} WHERE {where()}) GROUP BY run_id), "
            f"s AS (SELECT run_id, max(completed_at) AS completed_at, max(findings_count) AS findings_count "
            f"FROM {table('scan_runs')} WHERE {where('ingested_at',scoped=False)} AND status = 'complete' GROUP BY run_id) "
            f"SELECT s.completed_at, s.findings_count, c.source_checks, c.gaps FROM s LEFT JOIN c ON s.run_id=c.run_id "
            f"ORDER BY s.completed_at DESC LIMIT 50")


def run(profile, service, report, days=30, account=None, region=None):
    settings = profile.get("athena_analytics") or {}
    if not settings.get("enabled"):
        raise ValueError("Athena analytics is not enabled. Existing desk history remains available; no analytics query ran")
    required = ("role_arn", "workgroup", "database", "python")
    if any(not settings.get(k) for k in required):
        raise ValueError("Athena analytics setup is incomplete; operator must configure role, workgroup, database and runtime")
    tables = {"trend": ["findings"], "coverage": ["coverage"], "verification": ["verification_attempts"],
              "scan_coverage": ["coverage", "scan_runs"]}.get(report)
    if tables is None:
        raise ValueError("Unknown analytics report")
    snapshots = {name: service.storage.last_snapshot_id(name) for name in tables}
    sql = query(report, days, service.installation_id, snapshots, account, region)
    request = {k: settings[k] for k in required if k != "python"}
    request.update(sql=sql, region=settings.get("region", "us-east-1"))
    # Separate vendor SDK environment. No model-supplied executable, SQL, or credentials.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "PYTHONPATH", "HOME", "SYSTEMROOT", "TEMP", "TMP"}}
    proc = subprocess.run([settings["python"], str(Path(__file__).with_name("athena_worker.py"))],
                          input=json.dumps(request), capture_output=True, text=True, timeout=100, env=env)
    if proc.returncode:
        raise ValueError("Athena analytics failed; no report accepted. Check scoped access, worker runtime and workgroup")
    try:
        result = json.loads(proc.stdout)
    except ValueError as exc:
        raise ValueError("Invalid analytics worker response; no evidence accepted") from exc
    if not isinstance(result, dict) or result.get("status") != "SUCCEEDED":
        raise ValueError("Athena query did not succeed; no report accepted")
    columns, rows = result.get("columns"), result.get("rows")
    if (not isinstance(columns, list) or not columns or not all(isinstance(c, str) for c in columns)
            or not isinstance(rows, list) or len(rows) > 100
            or any(not isinstance(row, list) or len(row) != len(columns) for row in rows)
            or not result.get("query_id") or type(result.get("truncated")) is not bool):
        raise ValueError("Malformed analytics evidence; no report accepted")
    result.update(report=report, days=days, account=account or "installation-wide", region=region or "all stored regions",
                  source="AWS Data Processing MCP / Athena", snapshots=snapshots,
                  observed_at=datetime.now(timezone.utc).isoformat(), durability=service._durability(),
                  interpretation="Coverage counts collection checks, not days. Earliest returned row is not proof of installation date. Missing dates mean no returned records, not a proven reason. Daily distinct counts do not establish identical membership across days.",
                  semantics="Pinned table snapshots; descriptive aggregates, not a cross-table committed-batch proof",
                  row_limit=50 if report == "scan_coverage" else 90 if report == "trend" else 100,
                  limits="Bounded report, not all raw history. Observation counts are not distinct issues. Missing rows are not proof of resolution; check coverage. Empty verification means no recorded attempts.")
    return result
