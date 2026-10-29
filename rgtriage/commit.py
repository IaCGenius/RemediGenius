"""The commit loop: from the SQLite outbox to idempotent Iceberg batches (roadmap CE-13).

One writer (the desk) drains the outbox in bounded batches. Observations, coverage and scan facts commit once per
completed run; a human decision commits before it is acknowledged; a GitHub intent commits before GitHub is called.
Raw objects are confirmed in object storage before their facts are trusted.

A batch ID and content hash are written into each Iceberg snapshot summary. If the process dies after the catalog
commit but before the local acknowledgement, the next run finds the batch in table history and does not append it
again. Readers deduplicate by event ID, so at-least-once delivery cannot inflate counts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import cache as cache_module
from . import contracts, ocsf, rawstore
from .iceberg_store import IcebergUnavailable

KIND_TABLES = {
    "coverage": "coverage", "scan_run": "scan_runs", "signal": "signals", "decision": "decisions",
    "fix_event": "fix_events", "verification_attempt": "verification_attempts",
    "github_intent": "github_ops", "github_result": "github_ops",
}


@dataclass
class CommitResult:
    status: str
    batch_id: str = ""
    events: int = 0
    tables: dict = field(default_factory=dict)
    snapshot_id: int | None = None
    error: str = ""
    raw_problems: list = field(default_factory=list)

    @property
    def durable(self) -> bool:
        return self.status == "committed"

    def as_dict(self) -> dict:
        return {"status": self.status, "batch_id": self.batch_id, "events": self.events,
                "tables": self.tables, "snapshot_id": self.snapshot_id, "error": self.error,
                "raw_problems": self.raw_problems, "durable": self.durable}


def _at(value, fallback: str) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    try:
        return contracts.parse_time(str(value)) if value else contracts.parse_time(fallback)
    except contracts.ContractError:
        return contracts.parse_time(fallback)


def _json(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else contracts.canonical_json(value)


class Committer:
    def __init__(self, cache: cache_module.Cache, raw: rawstore.RawStore, storage,
                 *, max_batch: int = 500):
        self.cache = cache
        self.raw = raw
        self.storage = storage
        self.max_batch = max_batch
        self._ready = False

    def ensure_ready(self) -> None:
        if not self._ready:
            self.storage.ensure_tables()
            self._ready = True

    # ---------------------------------------------------------------- row mapping
    def _base(self, event: contracts.Event, sequence: int) -> dict:
        return {"event_id": event.event_id, "installation_id": event.installation_id, "epoch": event.epoch,
                "sequence": sequence, "observed_at": contracts.parse_time(event.observed_at),
                "ingested_at": contracts.parse_time(event.ingested_at)}

    def row_for(self, staged: cache_module.StagedEvent, sequence: int) -> tuple[str, dict]:
        event, payload = staged.event, staged.payload
        raw_ref = event.raw_ref
        raw_sha = raw_ref.sha256 if raw_ref else ""
        if event.kind == "observation":
            source = str(payload.get("source") or event.scope.source)
            if source in ocsf.SIGNAL_SOURCES:
                row = ocsf.signal_row(payload, event, raw_ref)
                row["sequence"] = sequence
                return "signals", row
            row = ocsf.finding_row(
                payload, event, raw_ref, priority=payload.get("priority"),
                reasons=payload.get("reasons"), issue_key=payload.get("issue_key") or "",
                coverage_status=payload.get("coverage_status") or "", truncated=bool(payload.get("truncated")))
            row["sequence"] = sequence
            return "findings", row
        if event.kind == "signal":
            row = ocsf.signal_row(payload, event, raw_ref)
            row["sequence"] = sequence
            return "signals", row
        table = KIND_TABLES[event.kind]
        row = self._base(event, sequence)
        if table == "coverage":
            row.update({"run_id": payload.get("run_id", ""), "account_id": payload.get("account_id") or event.scope.account,
                        "region": payload.get("region") or event.scope.region,
                        "source": payload.get("source") or event.scope.source, "status": payload.get("status", ""),
                        "count": payload.get("count"), "total": payload.get("total"),
                        "truncated": payload.get("truncated"), "completeness": payload.get("completeness"),
                        "note": payload.get("note"), "raw_sha256": raw_sha})
        elif table == "scan_runs":
            row.update({"run_id": payload.get("run_id", ""), "started_at": _at(payload.get("started_at"), event.observed_at),
                        "completed_at": _at(payload.get("completed_at"), event.observed_at),
                        "status": payload.get("status", ""), "accounts": payload.get("accounts") or [],
                        "regions": payload.get("regions") or [], "sources": payload.get("sources") or [],
                        "findings_count": payload.get("findings_count"), "issues_count": payload.get("issues_count"),
                        "truncated": payload.get("truncated"), "note": payload.get("note"),
                        "raw_sha256": raw_sha, "payload_hash": event.payload_hash})
        elif table == "decisions":
            row.update({"finding_key": payload.get("finding_key", ""), "status": payload.get("status", ""),
                        "reason": payload.get("reason", ""), "by": payload.get("by", "operator"),
                        "decided_at": _at(payload.get("decided_at"), event.observed_at),
                        "fix": _json(payload.get("fix")), "raw_sha256": raw_sha})
        elif table == "fix_events":
            row.update({"finding_key": payload.get("finding_key", ""), "state": payload.get("state", ""),
                        "previous_state": payload.get("previous_state"), "source": payload.get("source"),
                        "changed_at": _at(payload.get("changed_at"), event.observed_at),
                        "evidence": _json(payload.get("evidence")), "owner": payload.get("owner"),
                        "raw_sha256": raw_sha})
        elif table == "verification_attempts":
            row.update({"finding_key": payload.get("finding_key", ""),
                        "attempt_at": _at(payload.get("attempt_at"), event.observed_at),
                        "outcome": payload.get("outcome", ""), "passed": payload.get("passed"),
                        "observed": _json(payload.get("observed")), "error": payload.get("error"),
                        "target": payload.get("target") or {}, "rule_version": payload.get("rule_version"),
                        "raw_sha256": raw_sha})
        elif table == "github_ops":
            row.update({"operation_id": payload.get("operation_id") or event.event_id,
                        "phase": payload.get("phase") or ("intent" if event.kind == "github_intent" else "result"),
                        "finding_key": payload.get("finding_key"), "repo": payload.get("repo"),
                        "base_branch": payload.get("base_branch"), "branch": payload.get("branch"),
                        "proposal_digest": payload.get("proposal_digest"), "pr_number": payload.get("pr_number"),
                        "state": payload.get("state"), "at": _at(payload.get("at"), event.observed_at),
                        "error": payload.get("error"), "raw_sha256": raw_sha})
        return table, row

    # ---------------------------------------------------------------- commit
    def commit_pending(self, *, kinds: tuple[str, ...] | None = None, ack: bool = True,
                       max_batch: int | None = None) -> CommitResult:
        try:
            self.ensure_ready()
        except Exception as exc:
            return CommitResult("not-durable", error=f"storage is not ready: {type(exc).__name__}: {exc}"[:300])
        staged = self.cache.pending_batch(max_batch or self.max_batch, kinds)
        if not staged:
            return CommitResult("empty")
        try:
            plan = contracts.plan_batch([item.event for item in staged])
        except contracts.ConflictError as exc:
            return CommitResult("quarantined", error=str(exc))

        refs = [item.event.raw_ref for item in staged if item.event.raw_ref is not None]
        try:
            problems = self.raw.verify_many(refs) if refs else []
        except rawstore.BackendUnavailable as exc:
            return CommitResult("blocked", events=len(staged), error=f"raw store unreachable: {exc}"[:300])
        if problems:
            return CommitResult("blocked-raw", batch_id=plan.batch_id, events=len(staged), raw_problems=problems,
                                error="raw evidence is not confirmed in object storage")

        sequence = self.cache.next_sequence()
        rows: dict[str, list[dict]] = {}
        for item in staged:
            table, row = self.row_for(item, sequence)
            rows.setdefault(table, []).append(row)
        tables = sorted(rows)
        try:
            already = {table: self.storage.batch_in_history(table, plan.batch_id) for table in tables}
        except Exception as exc:
            return CommitResult("not-durable", batch_id=plan.batch_id, events=len(staged),
                                error=f"cannot read table history: {type(exc).__name__}: {exc}"[:300])
        self.cache.start_batch(plan, max(item.rowid for item in staged))
        appended: dict = {}
        try:
            appended = self.storage.append_many(
                {table: rows[table] for table in tables if not already[table]},
                batch_id=plan.batch_id, content_hash=plan.content_hash)
        except Exception as exc:
            self.cache.fail_batch(plan.batch_id, f"{type(exc).__name__}: {exc}"[:500], uncertain=True)
            return CommitResult("not-durable", batch_id=plan.batch_id, events=len(staged), tables=appended,
                                error=f"Iceberg commit failed: {type(exc).__name__}: {exc}"[:300])
        snapshot_ids = {table: self.storage.snapshot_for_batch(table, plan.batch_id) for table in tables}
        if any(value is None for value in snapshot_ids.values()):
            self.cache.fail_batch(plan.batch_id, "batch is missing from table history after append", uncertain=True)
            return CommitResult("not-durable", batch_id=plan.batch_id, events=len(staged), tables=appended,
                                error="batch is missing from table history after append")
        snapshot_id = next(value for value in snapshot_ids.values() if value is not None)
        if not ack:
            return CommitResult("committed-not-acked", batch_id=plan.batch_id, events=len(staged), tables=appended,
                                snapshot_id=snapshot_id)
        try:
            self.cache.complete_batch(plan.batch_id, snapshot_id, sequence)
        except Exception as exc:
            return CommitResult("committed-not-acked", batch_id=plan.batch_id, events=len(staged), tables=appended,
                                snapshot_id=snapshot_id,
                                error=f"catalog committed but local acknowledgement failed: {type(exc).__name__}: {exc}"[:300])
        return CommitResult("committed", batch_id=plan.batch_id, events=len(staged), tables=appended,
                            snapshot_id=snapshot_id)

    # ---------------------------------------------------------------- human and operation events
    def commit_decision(self, event: contracts.Event, payload: dict) -> CommitResult:
        if event.kind != "decision":
            raise ValueError("commit_decision needs a decision event")
        self.cache.stage_event(event, payload)
        result = self.commit_pending(kinds=("decision",), max_batch=1)
        if result.status == "empty" and self.cache.event_state(event.event_id) == "committed":
            return CommitResult("committed", events=1)
        return result

    def begin_github(self, event: contracts.Event, payload: dict) -> CommitResult:
        """Commit the intent. The caller must not call GitHub unless this result is durable."""
        if event.kind != "github_intent":
            raise ValueError("begin_github needs a github_intent event")
        self.cache.stage_event(event, payload)
        result = self.commit_pending(kinds=("github_intent",), max_batch=1)
        if result.status == "empty" and self.cache.event_state(event.event_id) == "committed":
            return CommitResult("committed", events=1)
        return result

    def finish_github(self, event: contracts.Event, payload: dict) -> CommitResult:
        if event.kind != "github_result":
            raise ValueError("finish_github needs a github_result event")
        self.cache.stage_event(event, payload)
        result = self.commit_pending(kinds=("github_result",), max_batch=1)
        if result.status == "empty" and self.cache.event_state(event.event_id) == "committed":
            return CommitResult("committed", events=1)
        return result

    def retry_pending(self) -> CommitResult:
        return self.commit_pending()