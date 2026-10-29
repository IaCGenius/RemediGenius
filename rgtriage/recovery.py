"""Rebuild on new compute and reconcile in-flight operations (roadmap CE-11).

A replacement Spot instance starts with an empty disk. It reads the installation ID and namespace from configuration,
verifies that the catalog belongs to that installation, rebuilds the cache from the current-state tables, starts a new
recovery epoch and re-runs unfinished scans. A missing catalog, wrong installation or schema mismatch is an explicit
recovery state, never a healthy-looking empty installation.

GitHub intents without a result are reconciled read-only against the original operation, branch and proposal identity.
A merged pull request is recorded as merged; recovery never creates an automatic numbered follow-up.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import cache as cache_module
from . import contracts
from .iceberg_store import IcebergUnavailable


@dataclass
class RecoveryReport:
    state: str
    reason: str = ""
    installation_id: str = ""
    namespace: str = ""
    epoch: str = ""
    watermark: contracts.Watermark | None = None
    rebuilt: dict = field(default_factory=dict)
    outbox_events: int = 0
    undurable_decisions: int = 0
    unresolved_operations: int = 0
    needs_scan: bool = False
    actions: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"state": self.state, "reason": self.reason, "installation_id": self.installation_id,
                "namespace": self.namespace, "epoch": self.epoch,
                "watermark": self.watermark.as_dict() if self.watermark else None,
                "rebuilt": self.rebuilt, "outbox_events": self.outbox_events,
                "undurable_decisions": self.undurable_decisions,
                "unresolved_operations": self.unresolved_operations, "needs_scan": self.needs_scan,
                "actions": self.actions}

    def health(self, *, raw_backlog: dict | None = None, checkpoint_age_seconds: float | None = None,
               last_maintenance: str = "") -> dict:
        backlog = raw_backlog or {}
        mark = self.watermark
        return {"installation_id": self.installation_id, "namespace": self.namespace, "epoch": self.epoch,
                "state": self.state, "commit_watermark": mark.as_dict() if mark else None,
                "commit_age_seconds": mark.lag_seconds() if mark else None,
                "outbox_events": self.outbox_events, "undurable_decisions": self.undurable_decisions,
                "raw_backlog": backlog.get("objects", 0), "last_maintenance": last_maintenance,
                "checkpoint_age_seconds": checkpoint_age_seconds,
                "unresolved_operations": self.unresolved_operations, "reason": self.reason}


def _mark_from_rows(rows: list[dict]) -> contracts.Watermark | None:
    for row in rows:
        value = row.get("watermark")
        if not value:
            continue
        data = dict(value)
        committed = data.get("committed_at")
        if isinstance(committed, datetime):
            data["committed_at"] = contracts.format_time(committed)
        try:
            return contracts.Watermark.from_dict(data)
        except (contracts.ContractError, KeyError, TypeError):
            continue
    return None


class Recovery:
    def __init__(self, cache: cache_module.Cache, storage, current_state, committer=None, raw=None):
        self.cache = cache
        self.storage = storage
        self.current_state = current_state
        self.committer = committer
        self.raw = raw

    def recover(self, *, empty_disk: bool = False, installation_id: str | None = None,
                namespace: str | None = None) -> RecoveryReport:
        configured = installation_id or os.environ.get("RGTRIAGE_INSTALLATION_ID") or ""
        namespace = namespace or self.cache.namespace()
        if empty_disk:
            if not configured:
                return RecoveryReport("blocked", "installation id is not configured; refusing to adopt an unknown catalog",
                                      installation_id="", namespace=namespace)
            try:
                self.cache.set_identity(configured, namespace, force=True)
            except cache_module.CacheError as exc:
                return RecoveryReport("blocked", str(exc), installation_id=configured, namespace=namespace)
        installation = self.cache.installation_id() or configured
        if not installation:
            return RecoveryReport("blocked", "installation id is unknown", namespace=namespace)

        try:
            self.storage.ensure_tables()
        except Exception as exc:  # catalog, credentials, schema or network
            return RecoveryReport("blocked", f"storage is not ready: {type(exc).__name__}: {exc}"[:300],
                                  installation_id=installation, namespace=namespace)
        try:
            findings = self.storage.scan_rows("current_findings")
            fixes = self.storage.scan_rows("current_fixes")
            decisions = self.storage.scan_rows("current_decisions")
            operations = self.storage.scan_rows("current_operations")
            events = self.storage.scan_rows("findings", limit=100)
        except Exception as exc:
            return RecoveryReport("blocked", f"cannot read committed facts: {type(exc).__name__}: {exc}"[:300],
                                  installation_id=installation, namespace=namespace)

        owners = set()
        for row in (*findings, *fixes, *decisions, *operations):
            value = row.get("watermark") or {}
            if value.get("installation_id"):
                owners.add(str(value["installation_id"]))
        for row in events:
            if row.get("installation_id"):
                owners.add(str(row["installation_id"]))
        if owners and installation not in owners:
            return RecoveryReport("blocked", f"the catalog belongs to installation {', '.join(sorted(owners))}",
                                  installation_id=installation, namespace=namespace)
        if any(owner != installation for owner in owners):
            return RecoveryReport("blocked", "the catalog mixes more than one installation", installation_id=installation,
                                  namespace=namespace)

        storage_mark = _mark_from_rows(findings) or _mark_from_rows(fixes) or _mark_from_rows(decisions)
        cache_mark = self.cache.watermark()
        rebuilt = {}
        actions = []
        if empty_disk or cache_mark is None or (storage_mark and cache_mark.sequence < storage_mark.sequence):
            rebuilt = self.current_state.rebuild_cache(storage_mark)
            if storage_mark:
                self.cache.adopt_watermark(storage_mark)
            actions.append("cache rebuilt from current-state tables")
        if empty_disk:
            actions.append(f"recovery epoch {self.cache.epoch()} started")
            actions.append("unfinished scans will be collected again")
        if not findings and not events:
            return RecoveryReport("recovering", "no committed facts yet; the first scan will populate the store",
                                  installation_id=installation, namespace=namespace, epoch=self.cache.epoch() or "",
                                  watermark=self.cache.watermark(), rebuilt=rebuilt, needs_scan=True, actions=actions)

        outbox = self.cache.pending_count()
        if self.committer is not None and outbox:
            result = self.committer.commit_pending()
            actions.append(f"outbox drain: {result.status}")
            outbox = self.cache.pending_count()

        unresolved = len(operations)
        state = "recovering" if empty_disk or rebuilt else "healthy"
        reason = "rebuilt from durable storage" if rebuilt else ""
        if outbox:
            state, reason = "degraded", f"{outbox} event(s) are not yet durable"
        elif unresolved:
            state, reason = ("degraded" if state == "healthy" else state), f"{unresolved} GitHub operation(s) need reconciliation"
        return RecoveryReport(state, reason, installation_id=installation, namespace=namespace,
                              epoch=self.cache.epoch() or "", watermark=self.cache.watermark(), rebuilt=rebuilt,
                              outbox_events=outbox, undurable_decisions=self.cache.undurable_decisions(),
                              unresolved_operations=unresolved, needs_scan=empty_disk, actions=actions)

    def reconcile_operations(self, reconcile) -> dict:
        """Read-only reconciliation. The callback returns {found, state, number, url, error}; no new operation is started."""
        if self.committer is None:
            raise RuntimeError("recovery needs a committer to record reconciled results")
        resolved, unresolved = [], []
        for operation in self.storage.scan_rows("current_operations"):
            try:
                result = reconcile(operation) or {}
            except Exception as exc:
                unresolved.append({"operation_id": operation.get("operation_id"),
                                   "reason": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            if not result.get("found"):
                unresolved.append({"operation_id": operation.get("operation_id"),
                                   "reason": result.get("reason") or "no matching pull request"})
                continue
            payload = {"operation_id": operation.get("operation_id"), "phase": "result",
                       "finding_key": operation.get("finding_key"), "repo": operation.get("repo"),
                       "base_branch": operation.get("base_branch"), "branch": operation.get("branch"),
                       "proposal_digest": operation.get("proposal_digest"),
                       "pr_number": result.get("number"), "state": result.get("state") or "found",
                       "at": contracts.format_time(contracts.utc_now()), "error": result.get("error") or ""}
            event = contracts.Event(
                event_id=contracts.operation_event_id(), kind="github_result",
                installation_id=self.cache.installation_id(), epoch=self.cache.epoch(), sequence=0,
                scope=contracts.Scope(account="", region="", source="desk"),
                observed_at=payload["at"], ingested_at=payload["at"],
                payload_hash=contracts.payload_hash(payload))
            committed = self.committer.finish_github(event, payload)
            if committed.durable:
                resolved.append({"operation_id": operation.get("operation_id"), "state": payload["state"],
                                 "pr_number": payload["pr_number"]})
            else:
                unresolved.append({"operation_id": operation.get("operation_id"),
                                   "reason": committed.error or committed.status})
        mark = self.cache.watermark()
        if mark:
            self.current_state.refresh_operations(mark)
        return {"resolved": resolved, "unresolved": unresolved}