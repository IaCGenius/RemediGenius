"""Finding episodes and temporal lifecycle (roadmap CE-08).

The reducer is deterministic over committed observations, decisions, fix events and verification attempts. It keeps
the technical state, the workflow disposition and the evidence visibility apart:

* observed time is when the source says it happened; ingested time is when the desk received it, and point-in-time
  queries use ingested time;
* applied/deployed time is recorded only from an explicit operator or change receipt, never inferred from a proof;
* a proof closes an episode only when it is a passing, complete, target-bound check and no newer positive evidence
  exists; repeated proofs do not move the first closure time;
* suppression, accepted risk, false-positive and manual resolution never become technical remediation;
* unknown visibility never closes anything.

An interrupted rebuild returns no live projection; the caller activates the new projection only after the whole
reducer completed (``complete=True``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import contracts

STATUS_OPEN = "open"
STATUS_VERIFIED = "verified"
STATUS_SUPPRESSED = "suppressed"
STATUS_ACCEPTED = "accepted_risk"
STATUS_FALSE_POSITIVE = "false_positive"
STATUS_MANUAL = "closed_manual"
STATUS_UNKNOWN = "unknown"


def _at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        return contracts.parse_time(str(value))
    except contracts.ContractError:
        return None


def _iso(value) -> str:
    parsed = _at(value)
    return contracts.format_time(parsed) if parsed else ""


@dataclass
class Episode:
    finding_key: str
    number: int
    first_observed_at: str
    last_observed_at: str
    first_ingested_at: str
    status: str = STATUS_OPEN
    applied_at: str | None = None
    verified_at: str | None = None
    closure_at: str | None = None
    closure_basis: str = ""
    recurrence_at: str | None = None
    visibility: str = "unknown"
    manual_closed: bool = False
    evidence_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"finding_key": self.finding_key, "episode": self.number,
                "first_observed_at": self.first_observed_at, "last_observed_at": self.last_observed_at,
                "first_ingested_at": self.first_ingested_at, "status": self.status,
                "applied_at": self.applied_at, "verified_at": self.verified_at,
                "closure_at": self.closure_at, "closure_basis": self.closure_basis,
                "recurrence_at": self.recurrence_at, "visibility": self.visibility,
                "manual_closed": self.manual_closed, "evidence_ids": list(self.evidence_ids)}


def events_from_rows(findings=(), verification_attempts=(), decisions=(), fix_events=()) -> list[dict]:
    events = []
    for row in findings:
        ce = row.get("ce") or {}
        key = str(ce.get("finding_key") or row.get("finding_key") or "")
        if not key:
            continue
        status = int(row.get("status_id") or 0)
        events.append({"event_id": row.get("event_id") or "", "kind": "observation", "finding_key": key,
                       "observed_at": _iso(row.get("observed_at")), "ingested_at": _iso(row.get("ingested_at")),
                       "active": status not in (3, 4)})
    for row in verification_attempts:
        key = str(row.get("finding_key") or "")
        if not key:
            continue
        events.append({"event_id": row.get("event_id") or "", "kind": "verification", "finding_key": key,
                       "observed_at": _iso(row.get("attempt_at")), "ingested_at": _iso(row.get("ingested_at")),
                       "passed": bool(row.get("passed")), "outcome": row.get("outcome") or "",
                       "visibility": row.get("visibility") or "unknown",
                       "target_state": row.get("target_state") or "unknown"})
    for row in decisions:
        key = str(row.get("finding_key") or "")
        if not key:
            continue
        events.append({"event_id": row.get("event_id") or "", "kind": "decision", "finding_key": key,
                       "observed_at": _iso(row.get("decided_at")), "ingested_at": _iso(row.get("ingested_at")),
                       "status": row.get("status") or ""})
    for row in fix_events:
        key = str(row.get("finding_key") or "")
        if not key:
            continue
        evidence = row.get("evidence") or ""
        receipt = False
        if isinstance(evidence, str) and evidence:
            try:
                import json

                receipt = bool(json.loads(evidence).get("applied_receipt"))
            except ValueError:
                receipt = False
        events.append({"event_id": row.get("event_id") or "", "kind": "fix", "finding_key": key,
                       "observed_at": _iso(row.get("changed_at")), "ingested_at": _iso(row.get("ingested_at")),
                       "state": row.get("state") or "", "applied_receipt": receipt})
    return events


def _sort_key(event: dict) -> tuple:
    return (_at(event.get("observed_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _at(event.get("ingested_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(event.get("event_id") or ""))


def timeline(events: list[dict], *, finding_key: str | None = None, as_of=None,
             complete: bool = True) -> dict:
    """Reduce events into episodes. Returns ``complete=False`` when the caller cannot finish the input."""
    when = _at(as_of) if as_of else None
    known = [dict(event) for event in events
             if (not finding_key or event.get("finding_key") == finding_key)
             and (when is None or (_at(event.get("ingested_at")) or datetime.min.replace(tzinfo=timezone.utc)) <= when)]
    known.sort(key=_sort_key)
    by_finding: dict[str, list[dict]] = {}
    for event in known:
        by_finding.setdefault(str(event.get("finding_key")), []).append(event)

    result = {}
    for key, items in by_finding.items():
        episodes: list[Episode] = []
        current: Episode | None = None
        latest_positive: datetime | None = None
        for event in items:
            kind = event.get("kind")
            observed = _iso(event.get("observed_at"))
            ingested = _iso(event.get("ingested_at"))
            if kind == "observation" and event.get("active"):
                seen = _at(observed) or datetime.min.replace(tzinfo=timezone.utc)
                if current is None:
                    current = Episode(key, 1, observed, observed, ingested)
                    episodes.append(current)
                elif current.closure_at:
                    current = Episode(key, len(episodes) + 1, observed, observed, ingested,
                                      status=STATUS_OPEN, recurrence_at=observed)
                    episodes.append(current)
                else:
                    current.last_observed_at = max(current.last_observed_at, observed)
                latest_positive = max(latest_positive or seen, seen)
            elif kind == "verification":
                if current is None:
                    continue
                proof_time = _at(observed) or datetime.min.replace(tzinfo=timezone.utc)
                if event.get("passed") and event.get("target_state") == "absent" and event.get("visibility") == "complete":
                    if latest_positive and latest_positive > proof_time:
                        continue  # newer positive evidence overrides an older passing proof
                    if current.verified_at is None and not current.manual_closed:
                        current.verified_at = observed
                        current.closure_at = observed
                        current.closure_basis = "target-bound proof on a complete read"
                        current.status = STATUS_VERIFIED
                elif event.get("passed") and event.get("target_state") == "present":
                    if current.closure_at:
                        current = Episode(key, len(episodes) + 1, observed, observed, ingested,
                                          recurrence_at=observed)
                        episodes.append(current)
                elif event.get("visibility") == "unknown":
                    current.visibility = "unknown"
            elif kind == "decision":
                status = str(event.get("status") or "")
                if current is None:
                    continue
                if status == "suppressed":
                    current.status = STATUS_SUPPRESSED
                elif status == "accepted_risk":
                    current.status = STATUS_ACCEPTED
                elif status == "false_positive":
                    current.status = STATUS_FALSE_POSITIVE
                elif status == "resolved" and current.verified_at is None:
                    current.status = STATUS_MANUAL
                    current.manual_closed = True
            elif kind == "fix" and current is not None:
                if event.get("state") in ("deployed", "verified") and event.get("applied_receipt"):
                    current.applied_at = current.applied_at or observed
            if current is not None:
                current.evidence_ids.append(str(event.get("event_id") or ""))
        result[key] = [episode.as_dict() for episode in episodes]
    return {"complete": complete, "as_of": when.isoformat() if when else None,
            "findings": result, "event_count": len(known)}


def from_storage(storage, *, finding_key: str | None = None, as_of=None, limit: int = 500) -> dict:
    """Read the committed fact tables and reduce one bounded timeline."""
    events = events_from_rows(storage.scan_rows("findings", limit=limit),
                              storage.scan_rows("verification_attempts", limit=limit),
                              storage.scan_rows("decisions", limit=limit),
                              storage.scan_rows("fix_events", limit=limit))
    return timeline(events, finding_key=finding_key, as_of=as_of)