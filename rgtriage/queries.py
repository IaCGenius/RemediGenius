"""Scoped current and historical facts through the existing desk surface (roadmap CE-14).

Reads use the SQLite cache for current state and PyIceberg scans for committed history, including time travel to a
snapshot. Every answer carries the commit watermark, what is not yet durable, the raw evidence reference and the
completeness of the evidence set. There is no separate network query server and no LLM write path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import attest, campaigns, contracts, lifecycle, relationships

HANDLERS = ("current", "history", "timeline", "evidence", "campaign", "campaigns", "receipts",
            "relationships", "graph", "verifications", "summary")
UNSUPPORTED = ()
MAX_LIMIT = 500
MAX_GRAPH_DEPTH = 2


class QueryError(ValueError):
    """A query parameter is not allowed or is malformed."""


def _limit(value, default: int = 50) -> int:
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise QueryError("limit must be an integer") from exc
    if number < 1:
        raise QueryError("limit must be at least 1")
    return min(number, MAX_LIMIT)


def _as_of(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    text = str(value)
    if len(text) == 10:  # a date means the end of that day
        text += "T23:59:59Z"
    return contracts.parse_time(text)


def _at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        return contracts.parse_time(str(value))
    except contracts.ContractError:
        return None


def _finding_key(row: dict) -> str:
    ce = row.get("ce") or {}
    return str(row.get("finding_key") or ce.get("finding_key") or row.get("key") or "")


class QueryService:
    def __init__(self, cache, storage, raw=None, *, installation_id: str | None = None):
        self.cache = cache
        self.storage = storage
        self.raw = raw
        self.installation_id = installation_id or cache.installation_id()

    def _durability(self) -> dict:
        return {"outbox_events": self.cache.pending_count(),
                "undurable_decisions": self.cache.undurable_decisions(),
                "watermark": self.cache.watermark().as_dict() if self.cache.watermark() else None}

    def current(self, finding_key: str | None = None, account: str | None = None, region: str | None = None,
                limit: int | None = None) -> dict:
        limit = _limit(limit)
        view = self.cache.get_view("current_findings")
        if view is not None:
            payload = view["payload"]
            rows = payload.get("findings") if isinstance(payload, dict) else payload
            rows = list(rows or [])
            view_watermark = view["watermark"]
        else:
            rows = self.storage.scan_rows("current_findings") if self.storage else []
            view_watermark = rows[0].get("watermark") if rows else None
        rows = [row for row in rows
                if (not finding_key or _finding_key(row) == finding_key)
                and (not account or str(row.get("account_id") or row.get("account") or "") == account)
                and (not region or str(row.get("region") or "") == region)]
        return {"query": "current", "installation_id": self.installation_id, "view_watermark": view_watermark,
                "durability": self._durability(), "count": len(rows), "rows": rows[:limit],
                "truncated": len(rows) > limit, "uncommitted_rows_included": False}

    def history(self, finding_key: str | None = None, as_of=None, account: str | None = None,
                region: str | None = None, limit: int | None = None) -> dict:
        limit = _limit(limit, 100)
        when = _as_of(as_of)
        snapshot_id = self.storage.snapshot_at("findings", when) if when else self.storage.last_snapshot_id("findings")
        if snapshot_id is None:
            rows = []
        else:
            rows = self.storage.scan_rows("findings", snapshot_id=snapshot_id)
        rows = [row for row in rows
                if str(row.get("installation_id")) == str(self.installation_id)
                and (not finding_key or _finding_key(row) == finding_key)
                and (not account or str(row.get("account_id") or "") == account)
                and (not region or str(row.get("region") or "") == region)]
        rows.sort(key=lambda row: _at(row.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        batch_id = self.storage.snapshot_summary("findings", snapshot_id).get("ce.batch_id", "") if snapshot_id else ""
        manifest = self.manifest(when, batch_id=batch_id)
        return {"query": "history", "installation_id": self.installation_id, "as_of": when.isoformat() if when else None,
                "snapshot_id": snapshot_id, "durability": self._durability(), "manifest": manifest,
                "evidence_set_complete": manifest["complete"], "count": len(rows), "rows": rows[:limit],
                "truncated": len(rows) > limit, "uncommitted_rows_included": False}

    def manifest(self, when: datetime | None = None, batch_id: str = "") -> dict:
        """The completed scan run and coverage that the historical answer is bound to.

        When the answer comes from one committed batch, the manifest is read from that same batch's scan_runs and
        coverage snapshots. That is exact even though Iceberg commits each table separately.
        """
        try:
            if batch_id:
                runs_snapshot = self.storage.snapshot_for_batch("scan_runs", batch_id)
                coverage_snapshot = self.storage.snapshot_for_batch("coverage", batch_id)
                if runs_snapshot is None:
                    return {"complete": False, "reason": "this batch has no committed scan run"}
                runs = self.storage.scan_rows("scan_runs", snapshot_id=runs_snapshot)
                coverage = (self.storage.scan_rows("coverage", snapshot_id=coverage_snapshot)
                            if coverage_snapshot is not None else [])
            else:
                scan_when = when + timedelta(seconds=5) if when else None
                runs = (self.storage.scan_rows_as_of("scan_runs", as_of=scan_when) if scan_when
                        else self.storage.scan_rows("scan_runs"))
                coverage = (self.storage.scan_rows_as_of("coverage", as_of=scan_when) if scan_when
                            else self.storage.scan_rows("coverage"))
        except Exception as exc:
            return {"complete": False, "reason": f"cannot read the evidence manifest: {type(exc).__name__}: {exc}"[:300]}
        runs = [run for run in runs if str(run.get("installation_id")) == str(self.installation_id)
                and run.get("status") == "complete"]
        if not runs:
            return {"complete": False, "reason": "no completed scan run is recorded at this cutoff"}
        run = max(runs, key=lambda item: _at(item.get("completed_at")) or _at(item.get("observed_at"))
                  or datetime.min.replace(tzinfo=timezone.utc))
        entries = [row for row in coverage if str(row.get("installation_id")) == str(self.installation_id)
                   and row.get("run_id") == run.get("run_id")]
        blind = [{"source": row.get("source"), "account_id": row.get("account_id"), "region": row.get("region"),
                  "status": row.get("status"), "truncated": bool(row.get("truncated"))}
                 for row in entries if row.get("status") != "ok" or row.get("truncated")]
        complete = bool(entries) and not blind
        return {"complete": complete, "run_id": run.get("run_id"),
                "cutoff": (_at(run.get("completed_at")) or _at(run.get("observed_at")) or datetime.min.replace(
                    tzinfo=timezone.utc)).isoformat(),
                "coverage": [{key: row.get(key) for key in ("source", "account_id", "region", "status", "truncated")}
                             for row in entries],
                "blind_spots": blind, "reason": "" if complete else "coverage is missing sources or was not complete"}

    def timeline(self, finding_key: str | None = None, as_of=None, limit: int | None = None) -> dict:
        limit = _limit(limit, 200)
        result = lifecycle.from_storage(self.storage, finding_key=finding_key, as_of=_as_of(as_of), limit=limit)
        result.update({"query": "timeline", "installation_id": self.installation_id,
                       "durability": self._durability()})
        return result

    def _campaign_rows(self) -> list:
        return self.storage.scan_rows("campaigns") if self.storage else []

    def campaigns(self, status: str | None = None, limit: int | None = None) -> dict:
        """Campaign versions, newest first, one entry per campaign with its latest version."""
        limit = _limit(limit, 50)
        rows = [row for row in self._campaign_rows() if not status or row.get("status") == status]
        latest = {}
        for row in rows:
            current = latest.get(row.get("campaign_id"))
            if current is None or int(row.get("version") or 0) > int(current.get("version") or 0):
                latest[row.get("campaign_id")] = row
        ordered = sorted(latest.values(), key=lambda row: (_at(row.get("updated_at")) or
                                                          datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return {"query": "campaigns", "installation_id": self.installation_id, "durability": self._durability(),
                "count": len(ordered), "rows": ordered[:limit], "truncated": len(ordered) > limit}

    def campaign(self, campaign_id: str = "", version: int | None = None, after: int | None = None,
                 limit: int | None = None) -> dict:
        """Full paginated membership of one campaign version, with per-target progress from its stored states."""
        if not campaign_id or not isinstance(campaign_id, str):
            raise QueryError("campaign_id is required")
        limit = _limit(limit, 100)
        versions = [row for row in self._campaign_rows() if row.get("campaign_id") == campaign_id]
        if not versions:
            return {"query": "campaign", "campaign_id": campaign_id, "found": False, "members": [],
                    "reason": "no campaign with this id is committed", "installation_id": self.installation_id,
                    "durability": self._durability()}
        chosen = int(version) if version is not None else max(int(row.get("version") or 0) for row in versions)
        record = next((row for row in versions if int(row.get("version") or 0) == chosen), None)
        if record is None:
            raise QueryError(f"campaign {campaign_id} has no version {chosen}")
        rows = [row for row in (self.storage.scan_rows("campaign_members") if self.storage else [])
                if row.get("campaign_id") == campaign_id and int(row.get("version") or 0) == chosen]
        page = campaigns.page(rows, after=int(after or 0), limit=limit)
        states = {row.get("state") for row in rows}
        page.update({"query": "campaign", "found": True, "campaign_id": campaign_id, "version": chosen,
                     "title": record.get("title"), "status": record.get("status"),
                     "membership_digest": record.get("membership_digest"), "member_count": record.get("member_count"),
                     "approved_by": record.get("approved_by"), "approved_at": record.get("approved_at"),
                     "progress": {"verified": sum(1 for row in rows if row.get("state") == "verified"),
                                  "applied_pending_verification": sum(1 for row in rows if row.get("state") == "applied"),
                                  "open": sum(1 for row in rows if row.get("state") == "open"),
                                  # A proof for an undeployed target is its own bucket, exactly as in CE-21/CE-22.
                                  "verified_not_applied": sum(1 for row in rows
                                                              if row.get("state") == "verified_not_applied"),
                                  "membership_digest": record.get("membership_digest")},
                     "states_seen": sorted(state for state in states if state),
                     "installation_id": self.installation_id, "durability": self._durability()})
        return page

    def summary(self, campaign_id: str = "", version: int | None = None, as_of=None, accounts=None,
                record: bool = False) -> dict:
        """The one attested computation: campaign counts, re-derived from retained rows before they are shown.

        The receipt is always returned. `record=True` appends it to `computation_receipts` once (the id is
        deterministic), including a failed attestation, so a refusal is retained as its own result.
        """
        if not campaign_id or not isinstance(campaign_id, str):
            raise QueryError("campaign_id is required")
        versions = [row for row in self._campaign_rows() if row.get("campaign_id") == campaign_id]
        if not versions:
            raise QueryError(f"no committed campaign with id {campaign_id}")
        chosen = int(version) if version is not None else max(int(row.get("version") or 0) for row in versions)
        if not any(int(row.get("version") or 0) == chosen for row in versions):
            raise QueryError(f"campaign {campaign_id} has no version {chosen}")
        when = _as_of(as_of)
        snapshot_id = (self.storage.snapshot_at("campaign_members", when) if when
                       else self.storage.last_snapshot_id("campaign_members"))
        if snapshot_id is None:
            raise QueryError("campaign membership has no committed snapshot to compute over")
        rows = [row for row in self.storage.scan_rows("campaign_members", snapshot_id=snapshot_id)
                if row.get("campaign_id") == campaign_id and int(row.get("version") or 0) == chosen]
        evidence_set = contracts.payload_hash(sorted({str(row.get("evidence_sha256") or "") for row in rows}))
        params = attest.params(campaign_id=campaign_id, version=chosen, installation_id=self.installation_id,
                               as_of=when.isoformat() if when else "", evidence_set=evidence_set)
        execution = attest.execute(rows, params=params, snapshot_id=snapshot_id)
        verdict = attest.attest(execution, retained_rows=rows, accounts=accounts, snapshot_id=snapshot_id)
        receipt = attest.receipt_row(execution, verdict, installation_id=self.installation_id)
        recorded = False
        if record:
            existing = {str(row.get("receipt_id"))
                        for row in self.storage.scan_rows("computation_receipts")}
            if receipt["receipt_id"] not in existing:
                self.storage.append_rows("computation_receipts", [receipt], batch_id=receipt["receipt_id"],
                                         content_hash=receipt["output_digest"])
                recorded = True
        return {"query": "summary", "installation_id": self.installation_id, "campaign_id": campaign_id,
                "version": chosen, "snapshot_id": snapshot_id, "attested": verdict["attested"],
                "result": verdict["result"], "authoritative": verdict["authoritative"],
                "counts": verdict["counts"], "problems": verdict["problems"], "reason": verdict["reason"],
                "explain": attest.explain(receipt), "receipt": receipt, "receipt_recorded": recorded,
                "durability": self._durability()}

    def receipts(self, target_id: str = "", campaign_id: str = "", limit: int | None = None) -> dict:
        """The receipt chain for one target or campaign, oldest first, with producer and evidence provenance."""
        if not target_id and not campaign_id:
            raise QueryError("target_id or campaign_id is required")
        limit = _limit(limit, 100)
        rows = [row for row in (self.storage.scan_rows("deployment_receipts") if self.storage else [])
                if (not target_id or row.get("target_id") == target_id)
                and (not campaign_id or row.get("campaign_id") == campaign_id)]
        rows.sort(key=lambda row: _at(row.get("received_at")) or datetime.min.replace(tzinfo=timezone.utc))
        return {"query": "receipts", "installation_id": self.installation_id, "durability": self._durability(),
                "target_id": target_id, "campaign_id": campaign_id, "count": len(rows), "rows": rows[:limit],
                "truncated": len(rows) > limit,
                "steps": sorted({row.get("kind") for row in rows if row.get("status") in ("accepted", "duplicate")})}

    def _assertion_rows(self) -> list:
        return self.storage.scan_rows("relationships") if self.storage else []

    @staticmethod
    def _on_side(row: dict, side: str, value: str) -> bool:
        if not value:
            return True
        return value in (str(row.get(f"{side}_key") or ""), str(row.get(f"{side}_identity") or ""))

    def relationships(self, subject: str = "", object: str = "", predicate: str = "", status: str = "",
                      as_of=None, limit: int | None = None) -> dict:
        """Authoritative edges (or hypotheses, when asked) with their evidence and validity."""
        limit = _limit(limit, 100)
        when = _as_of(as_of)
        every = self._assertion_rows()
        rows = []
        for row in every:
            if not self._on_side(row, "subject", subject) or not self._on_side(row, "object", object):
                continue
            if predicate and row.get("predicate") != predicate:
                continue
            if status:
                if row.get("status") != status:
                    continue
            elif row.get("status") == "retracted":
                continue
            if when is not None:
                start, end = _at(row.get("valid_from")), _at(row.get("valid_to"))
                if start and when < start:
                    continue
                if end and when >= end:
                    continue
            rows.append(row)
        rows.sort(key=lambda row: _at(row.get("recorded_at")) or datetime.min.replace(tzinfo=timezone.utc),
                  reverse=True)
        newest = max((_at(row.get("recorded_at")) for row in every if _at(row.get("recorded_at"))), default=None)
        return {"query": "relationships", "installation_id": self.installation_id, "as_of":
                when.isoformat() if when else None, "durability": self._durability(), "count": len(rows),
                "rows": [{**row, "authoritative": row.get("status") in relationships.AUTHORITATIVE}
                         for row in rows[:limit]],
                "truncated": len(rows) > limit,
                # Graph freshness is reported on its own: it says nothing about whether AWS is healthy.
                "graph": {"newest_assertion_at": newest.isoformat() if newest else None,
                          "age_seconds": round((datetime.now(timezone.utc) - newest).total_seconds(), 3)
                          if newest else None}}

    def graph(self, entity: str = "", depth: int | None = 1, limit: int | None = None) -> dict:
        """Bounded neighbourhood around one entity: depth is capped and the edge count is capped."""
        if not entity:
            raise QueryError("entity (a key or an identity) is required")
        try:
            depth = int(depth if depth is not None else 1)
        except (TypeError, ValueError) as exc:
            raise QueryError("depth must be an integer") from exc
        if depth < 1:
            raise QueryError("depth must be at least 1")
        depth = min(depth, MAX_GRAPH_DEPTH)
        limit = _limit(limit, 100)
        rows = [row for row in self._assertion_rows() if row.get("status") != "retracted"]
        nodes = {entity}
        edges, seen = [], set()
        frontier = {entity}
        for _ in range(depth):
            found = []
            for row in rows:
                if row.get("assertion_id") in seen:
                    continue
                if str(row.get("subject_key")) in frontier or str(row.get("object_key")) in frontier:
                    found.append(row)
            if not found:
                break
            for row in found:
                seen.add(row.get("assertion_id"))
                edges.append({**row, "authoritative": row.get("status") in relationships.AUTHORITATIVE})
                nodes.update({str(row.get("subject_key")), str(row.get("object_key"))})
            frontier = {str(row.get("subject_key")) for row in found} | {str(row.get("object_key")) for row in found}
            if len(edges) >= limit:
                break
        return {"query": "graph", "installation_id": self.installation_id, "center": entity, "depth": depth,
                "durability": self._durability(), "nodes": sorted(nodes), "edges": edges[:limit],
                "count": len(edges[:limit]), "truncated": len(edges) > limit}

    def verifications(self, target_id: str = "", limit: int | None = None) -> dict:
        """Every proof attempt for one target, newest first, with the verifier and rule version that made it."""
        if not target_id:
            raise QueryError("target_id is required")
        limit = _limit(limit, 50)
        rows = [row for row in (self.storage.scan_rows("target_verifications") if self.storage else [])
                if row.get("target_id") == target_id]
        rows.sort(key=lambda row: _at(row.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc),
                  reverse=True)
        latest = rows[0] if rows else None
        return {"query": "verifications", "installation_id": self.installation_id, "durability": self._durability(),
                "target_id": target_id, "count": len(rows), "rows": rows[:limit], "truncated": len(rows) > limit,
                "latest": {key: latest.get(key) for key in ("outcome", "verified", "verifier", "predicate_version",
                                                           "observed_at", "reason")} if latest else None,
                "verified": bool(latest and latest.get("verified"))}

    def evidence(self, sha256: str) -> dict:
        """Resolve a raw evidence reference without returning the object bytes to the agent."""
        if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise QueryError("evidence id must be 64 lowercase hex characters")
        ref = self.cache.raw_ref_for_sha256(sha256)
        if ref is None:
            return {"query": "evidence", "sha256": sha256, "exists": False, "verified": False,
                    "reason": "no raw object with this id is referenced by this installation"}
        try:
            verified = bool(self.raw and self.raw.verify(ref))
        except Exception as exc:
            verified = False
            reason = f"raw store unavailable: {type(exc).__name__}: {exc}"[:200]
        else:
            reason = "" if verified else "the object is missing or does not match its SHA-256"
        return {"query": "evidence", "sha256": sha256, "exists": True, "verified": verified,
                "key": ref.key, "scope": ref.scope.as_dict(), "observed_at": ref.observed_at,
                "parameters_hash": ref.parameters_hash, "reason": reason}

    def dispatch(self, handler: str, params: dict | None = None) -> dict:
        params = params or {}
        if handler in UNSUPPORTED:
            return {"status": "unsupported", "handler": handler,
                    "reason": "not part of the core storage release"}
        if handler not in HANDLERS:
            raise QueryError(f"unknown query handler {handler!r}")
        allowed = {"current": {"finding_key", "account", "region", "limit"},
                   "history": {"finding_key", "as_of", "account", "region", "limit"},
                   "timeline": {"finding_key", "as_of", "limit"},
                   "campaign": {"campaign_id", "version", "after", "limit"},
                   "campaigns": {"status", "limit"},
                   "summary": {"campaign_id", "version", "as_of", "accounts", "record"},
                   "receipts": {"target_id", "campaign_id", "limit"},
                   "relationships": {"subject", "object", "predicate", "status", "as_of", "limit"},
                   "graph": {"entity", "depth", "limit"},
                   "verifications": {"target_id", "limit"},
                   "evidence": {"sha256"}}[handler]
        unknown = set(params) - allowed
        if unknown:
            raise QueryError(f"{handler} does not accept {', '.join(sorted(unknown))}")
        return getattr(self, handler)(**params)