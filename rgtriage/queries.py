"""Scoped current and historical facts through the existing desk surface (roadmap CE-14).

Reads use the SQLite cache for current state and PyIceberg scans for committed history, including time travel to a
snapshot. Every answer carries the commit watermark, what is not yet durable, the raw evidence reference and the
completeness of the evidence set. There is no separate network query server and no LLM write path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import campaigns, contracts, lifecycle

HANDLERS = ("current", "history", "timeline", "evidence", "campaign", "campaigns", "receipts")
UNSUPPORTED = ("relationships", "graph")
MAX_LIMIT = 500


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
                                  "membership_digest": record.get("membership_digest")},
                     "states_seen": sorted(state for state in states if state),
                     "installation_id": self.installation_id, "durability": self._durability()})
        return page

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
                   "receipts": {"target_id", "campaign_id", "limit"},
                   "evidence": {"sha256"}}[handler]
        unknown = set(params) - allowed
        if unknown:
            raise QueryError(f"{handler} does not accept {', '.join(sorted(unknown))}")
        return getattr(self, handler)(**params)