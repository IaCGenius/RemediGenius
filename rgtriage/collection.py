"""Resumable collection per source scope (roadmap CE-07).

In-progress source/account/region/filter scopes, page counts and outcomes live in SQLite. Raw response pages are
written to object storage as they arrive, so a restart can resume a run without re-reading what is already durable.
A scope counts as complete only when every required page succeeded; a failed or suspended source keeps its partial
coverage record and does not erase the successful sources.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import contracts, rawstore


@dataclass(frozen=True, slots=True)
class ScopeRef:
    account_id: str
    account: str
    region: str
    source: str
    filter_hash: str = ""

    @property
    def key(self) -> str:
        return f"{self.account_id}/{self.region}/{self.source}/{self.filter_hash}"


class CollectionPaused(rawstore.RawStoreError):
    """The raw buffer is full; collection must pause rather than drop a response."""


class CollectionRun:
    def __init__(self, cache, raw: rawstore.RawStore, run_id: str):
        self.cache = cache
        self.raw = raw
        self.run_id = run_id
        self.paused = False
        self.result_refs: dict[str, contracts.RawRef] = {}

    @staticmethod
    def scope(account: dict, region: str, source: str, filter_hash: str = "") -> ScopeRef:
        return ScopeRef(account_id=str(account.get("account_id") or account.get("name") or ""),
                        account=str(account.get("name") or ""), region=region, source=source,
                        filter_hash=filter_hash)

    def begin_scope(self, scope: ScopeRef) -> dict:
        if self.paused:
            raise CollectionPaused("collection is paused: the raw buffer is full")
        record = self.cache.load_progress(self.run_id + ":" + scope.key)
        if record and record["run_id"] == self.run_id and record["status"] == "complete":
            return record
        self.cache.save_progress(self.run_id + ":" + scope.key, run_id=self.run_id, account=scope.account_id,
                                 region=scope.region, source=scope.source, filter_hash=scope.filter_hash,
                                 pages=(record or {}).get("pages", 0), items=(record or {}).get("items", 0),
                                 status="in_progress", completeness="unknown")
        return self.cache.load_progress(self.run_id + ":" + scope.key)

    def record_page(self, scope: ScopeRef, operation: str, page, parameters=None) -> contracts.RawRef:
        try:
            result = self.raw.put_json(page, scope=contracts.Scope(account=scope.account_id, region=scope.region,
                                                                   source=scope.source, filter_hash=scope.filter_hash),
                                       operation=operation, observed_at=contracts.format_time(contracts.utc_now()),
                                       parameters=parameters)
        except rawstore.BufferFull as exc:
            self.paused = True
            self.cache.save_progress(self.run_id + ":" + scope.key, run_id=self.run_id, account=scope.account_id,
                                     region=scope.region, source=scope.source, filter_hash=scope.filter_hash,
                                     status="failed", completeness="unknown")
            raise CollectionPaused(str(exc)) from exc
        current = self.cache.load_progress(self.run_id + ":" + scope.key) or {}
        self.cache.save_progress(self.run_id + ":" + scope.key, run_id=self.run_id, account=scope.account_id,
                                 region=scope.region, source=scope.source, filter_hash=scope.filter_hash,
                                 pages=int(current.get("pages", 0)) + 1, items=int(current.get("items", 0)),
                                 status="in_progress", completeness="unknown")
        return result.ref

    def record_result(self, scope: ScopeRef, findings: list[dict], meta: dict | None = None) -> contracts.RawRef:
        """The normalized scope result is raw evidence too; facts reference these bytes."""
        result = self.raw.put_json({"findings": findings, "meta": meta or {}},
                                   scope=contracts.Scope(account=scope.account_id, region=scope.region,
                                                         source=scope.source, filter_hash=scope.filter_hash),
                                   operation="ScopeResult", observed_at=contracts.format_time(contracts.utc_now()))
        self.result_refs[scope.key] = result.ref
        current = self.cache.load_progress(self.run_id + ":" + scope.key) or {}
        self.cache.save_progress(self.run_id + ":" + scope.key, run_id=self.run_id, account=scope.account_id,
                                 region=scope.region, source=scope.source, filter_hash=scope.filter_hash,
                                 pages=int(current.get("pages", 0)), items=len(findings),
                                 status="in_progress", completeness="unknown")
        return result.ref

    def complete_scope(self, scope: ScopeRef, *, count: int, truncated: bool = False, note: str = "") -> None:
        completeness = "partial" if truncated else "ok"
        self.cache.save_progress(self.run_id + ":" + scope.key, run_id=self.run_id, account=scope.account_id,
                                 region=scope.region, source=scope.source, filter_hash=scope.filter_hash,
                                 pages=(self.cache.load_progress(self.run_id + ":" + scope.key) or {}).get("pages", 0),
                                 items=count, status="complete", completeness=completeness)

    def fail_scope(self, scope: ScopeRef, *, status: str = "error", note: str = "") -> None:
        completeness = {"denied": "denied", "not_enabled": "not_enabled"}.get(status, "error")
        self.cache.save_progress(self.run_id + ":" + scope.key, run_id=self.run_id, account=scope.account_id,
                                 region=scope.region, source=scope.source, filter_hash=scope.filter_hash,
                                 status="failed", completeness=completeness)

    def pending(self) -> list[dict]:
        return [row for row in self.cache.progress_for_run(self.run_id) if row["status"] != "complete"]

    def complete(self) -> bool:
        return bool(self.cache.progress_for_run(self.run_id)) and not self.pending()