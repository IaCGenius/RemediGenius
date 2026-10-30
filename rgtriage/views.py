"""Explore views: finding timeline, campaign membership and bounded graph (roadmap CE-23).

These are view models, not a second query engine. Each one takes a structured response from `QueryService` and adds the
three things a person needs to read it honestly:

- **separate times.** Observed, applied, verified and ingested are different facts. Applying a change is not a proof,
  and a late ingestion is visible instead of looking like a late fix.
- **authoritative counts only from an attested receipt.** Membership pages are paginated and the board preview is
  bounded; neither is a count. Without an attested computation the numbers are labelled as page-derived.
- **completeness and cutoff.** A stale graph, a partial evidence set or an interrupted recovery says so, and says that
  it is not current operational state. A hypothetical edge is labelled and cannot authorise a trusted action.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import relationships

MAX_STALE_SECONDS = 3600
LATE_INGESTION_SECONDS = 3600

STATE_OK = "ok"
STATE_LOADING = "loading"
STATE_PARTIAL = "partial"
STATE_STALE = "stale"
STATE_RECOVERY = "recovery_incomplete"
STATE_DENIED = "denied"
STATE_UNAVAILABLE = "unavailable"

ADMINISTRATIVE = ("suppressed", "accepted_risk", "false_positive", "closed_manual")


def _at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _load(value):
    if isinstance(value, (list, dict)):
        return value
    if not value:
        return []
    import json

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return []


def _seconds_between(left, right) -> float | None:
    first, second = _at(left), _at(right)
    return round((second - first).total_seconds(), 3) if first and second else None


def _cutoff(result: dict, cutoff=None) -> str:
    if cutoff:
        return str(cutoff)
    for key in ("cutoff", "as_of"):
        if result.get(key):
            return str(result[key])
    return ""


def freshness(result: dict, *, cutoff=None, now: datetime | None = None, max_age: int = MAX_STALE_SECONDS,
              complete: bool | None = None, recovery_incomplete: bool = False) -> dict:
    """The state of one answer: is it usable for a decision, and is it current operational state?"""
    when = _cutoff(result, cutoff)
    parsed = _at(when)
    age = None
    if parsed:
        age = round(((now or datetime.now(timezone.utc)) - parsed).total_seconds(), 3)
    complete = bool(result.get("complete", True)) if complete is None else bool(complete)
    if recovery_incomplete:
        state = STATE_RECOVERY
    elif not complete:
        state = STATE_PARTIAL
    elif result.get("loading"):
        state = STATE_LOADING
    elif age is not None and age > max_age:
        state = STATE_STALE
    else:
        state = STATE_OK
    return {"state": state, "cutoff": when or None, "age_seconds": age,
            "usable_for_decision": state == STATE_OK,
            "is_current_operational_state": state in (STATE_OK, STATE_LOADING),
            "reason": {STATE_RECOVERY: "recovery did not complete; the projection is not active",
                       STATE_PARTIAL: result.get("reason") or "the evidence set is not complete",
                       STATE_STALE: f"the answer is {int(age or 0)}s old; its cutoff is reported, not now",
                       STATE_LOADING: "the view is still loading"}.get(state, "")}


def denied(query: str, reason: str) -> dict:
    return {"query": f"view.{query}", "state": STATE_DENIED, "cutoff": None, "age_seconds": None,
            "usable_for_decision": False, "is_current_operational_state": False,
            "reason": reason or "this installation may not read that scope"}


def unavailable(query: str, reason: str) -> dict:
    return {"query": f"view.{query}", "state": STATE_UNAVAILABLE, "cutoff": None, "age_seconds": None,
            "usable_for_decision": False, "is_current_operational_state": False,
            "reason": reason or "the requested artifact is not available"}


def finding_timeline(result: dict, *, coverage=None, watermark=None, dispositions=None, cutoff=None,
                     now: datetime | None = None, late_seconds: int = LATE_INGESTION_SECONDS) -> dict:
    """One row per episode with application, verification and ingestion kept apart.

    `result` is a `lifecycle.timeline` answer: `{"complete", "as_of", "findings": {key: [episodes]}}`.
    """
    if not isinstance(result, dict):
        return unavailable("timeline", "no timeline was returned")
    state = freshness(result, cutoff=cutoff, now=now)
    decided = dict(dispositions or {})
    rows = []
    for key, episodes in sorted((result.get("findings") or {}).items()):
        for episode in episodes:
            status = str(episode.get("status") or "open")
            delay = _seconds_between(episode.get("first_observed_at"), episode.get("first_ingested_at"))
            rows.append({
                "finding_key": key, "episode": episode.get("episode"),
                "status": status,
                "observed_at": episode.get("first_observed_at"), "last_observed_at": episode.get("last_observed_at"),
                "applied_at": episode.get("applied_at"), "verified_at": episode.get("verified_at"),
                "ingested_at": episode.get("first_ingested_at"),
                "recurrence_at": episode.get("recurrence_at"),
                "application_is_not_verification": True,
                "verification_required": episode.get("verified_at") is None,
                "ingestion_delay_seconds": delay,
                "late_ingestion": bool(delay is not None and delay > late_seconds),
                "administrative_disposition": status in ADMINISTRATIVE,
                "disposition": decided.get(key) or status,
                "source_coverage": coverage or {},
                "projection_watermark": watermark or {},
                "evidence_ids": list(episode.get("evidence_ids") or []),
            })
    return {"query": "view.timeline", **state, "as_of": result.get("as_of"),
            "event_count": result.get("event_count", 0), "count": len(rows), "findings": rows}


def campaign_page(page: dict, *, receipt: dict | None = None, cutoff=None) -> dict:
    """A membership page plus counts whose authority is stated. Page counts are never presented as attested ones."""
    if not isinstance(page, dict):
        return unavailable("campaign", "no campaign response was returned")
    if page.get("found") is False:
        return {"query": "view.campaign", "state": STATE_UNAVAILABLE, "campaign_id": page.get("campaign_id"),
                "usable_for_decision": False, "is_current_operational_state": False,
                "reason": page.get("reason") or "no committed campaign with this id"}
    from . import attest

    counts = {key: page.get("progress", {}).get(key) for key in
              ("verified", "applied_pending_verification", "open")}
    authoritative = attest.authoritative(receipt)
    if authoritative:
        recorded = _load(receipt.get("counts"))
        if isinstance(recorded, dict):
            counts = {key: recorded.get(key) for key in ("verified", "applied_pending_verification", "open")}
    return {
        "query": "view.campaign", "state": STATE_OK, "cutoff": _cutoff(page, cutoff),
        "usable_for_decision": True, "is_current_operational_state": True,
        "campaign_id": page.get("campaign_id"), "version": page.get("version"), "title": page.get("title"),
        "status": page.get("status"), "membership_digest": page.get("membership_digest"),
        "member_count": page.get("member_count"), "total_members": page.get("total_members", page.get("member_count")),
        "returned": page.get("returned", len(page.get("members") or [])),
        "next_cursor": page.get("next_cursor"), "has_more": page.get("has_more", False),
        # The board preview is bounded on purpose; a full membership never comes from it.
        "board_preview_used": False, "source": "campaign_members",
        "counts": counts,
        "authoritative": authoritative,
        "counts_source": "attested_computation" if authoritative else "membership_page",
        "receipt_id": receipt.get("receipt_id") if authoritative else "",
        "counts_note": ("" if authoritative else
                        "not an attested computation: these numbers come from the stored member states"),
        "members": [{key: member.get(key) for key in
                     ("ordinal", "target_id", "finding_key", "target_kind", "account_id", "region", "resource_id",
                      "resource_generation", "state", "evidence_sha256")}
                    for member in (page.get("members") or [])],
    }


def _node(row: dict, side: str) -> dict:
    scope = _load(row.get(f"{side}_scope"))
    return {"key": row.get(f"{side}_key"), "kind": row.get(f"{side}_kind"),
            "identity": row.get(f"{side}_identity"),
            "scope": scope if isinstance(scope, dict) else {}}


def graph_view(result: dict, *, cutoff=None, now: datetime | None = None, max_age: int = MAX_STALE_SECONDS) -> dict:
    """A bounded neighbourhood where every edge says whether it may authorise anything."""
    if not isinstance(result, dict):
        return unavailable("graph", "no graph response was returned")
    edges = []
    nodes: dict[str, dict] = {}
    for row in result.get("edges") or []:
        status = str(row.get("status") or "hypothesis")
        # Status alone decides authority; a caller that did not annotate the row cannot widen it.
        authoritative = status in relationships.AUTHORITATIVE
        edges.append({
            "assertion_id": row.get("assertion_id"), "subject": row.get("subject_key"),
            "predicate": row.get("predicate"), "object": row.get("object_key"), "status": status,
            "label": ("observed" if status == "observed" else
                      f"derived by {row.get('derivation')}" if status == "derived" else "hypothesis"),
            "authoritative": authoritative, "may_authorize": authoritative,
            "trusted_action_allowed": authoritative,
            "evidence": _load(row.get("evidence")), "derivation": row.get("derivation") or "",
            "recorded_at": row.get("recorded_at"), "valid_from": row.get("valid_from"),
            "valid_to": row.get("valid_to"),
        })
        for side in ("subject", "object"):
            node = _node(row, side)
            if node["key"]:
                nodes.setdefault(str(node["key"]), node)
    center = str(result.get("center") or "")
    if center and center not in nodes:
        nodes[center] = {"key": center, "kind": "unknown", "identity": center, "scope": {}}
    hypotheses = [edge["assertion_id"] for edge in edges if not edge["authoritative"]]
    graph = result.get("graph") or {}
    # A graph answer is only as current as its newest assertion; that is its cutoff, not the wall clock.
    when = cutoff or graph.get("newest_assertion_at")
    state = freshness(result, cutoff=when, now=now, max_age=max_age)
    return {
        "query": "view.graph", **state,
        "center": center or None, "depth": result.get("depth"),
        "nodes": sorted(nodes.values(), key=lambda node: str(node.get("key"))),
        "edges": edges,
        "hypotheses": hypotheses,
        # Fail closed: one hypothetical edge in the neighbourhood blocks trusted actions until a person reviews it.
        "trusted_actions_allowed": not hypotheses,
        "truncated": bool(result.get("truncated")),
        "graph": result.get("graph") or {},
    }