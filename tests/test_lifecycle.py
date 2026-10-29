"""Finding episodes: applied vs verified, late evidence, recurrence and closure (roadmap CE-08)."""
from __future__ import annotations

import random

from rgtriage import lifecycle


def event(kind: str, *, key: str = "key1", observed: str, ingested: str | None = None, **fields) -> dict:
    return {"kind": kind, "finding_key": key, "observed_at": observed, "ingested_at": ingested or observed,
            "event_id": f"{kind}-{observed}-{len(fields)}", **fields}


def episodes(events: list[dict], **kwargs):
    result = lifecycle.timeline(events, **kwargs)
    return result, result["findings"].get("key1", [])


def test_observed_applied_and_verified_are_separate():
    _, rows = episodes([
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("fix", observed="2026-06-15T10:00:00Z", state="deployed", applied_receipt=True),
        event("verification", observed="2026-06-15T11:00:00Z", passed=True, target_state="absent",
              visibility="complete"),
    ])
    assert len(rows) == 1
    episode = rows[0]
    assert episode["first_observed_at"] == "2026-06-10T10:00:00.000000Z"
    assert episode["applied_at"] == "2026-06-15T10:00:00.000000Z"
    assert episode["verified_at"] == "2026-06-15T11:00:00.000000Z"
    assert episode["closure_at"] == "2026-06-15T11:00:00.000000Z"
    assert episode["status"] == "verified"


def test_a_proof_without_an_application_receipt_leaves_applied_time_unknown():
    _, rows = episodes([
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("fix", observed="2026-06-15T10:00:00Z", state="deployed", applied_receipt=False),
        event("verification", observed="2026-06-15T11:00:00Z", passed=True, target_state="absent",
              visibility="complete"),
    ])
    assert rows[0]["applied_at"] is None
    assert rows[0]["verified_at"] is not None


def test_late_evidence_is_not_known_before_it_was_ingested():
    events = [
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("verification", observed="2026-06-15T10:00:00Z", ingested="2026-06-16T09:00:00Z",
              passed=True, target_state="absent", visibility="complete"),
    ]
    before = lifecycle.timeline(events, as_of="2026-06-15T23:59:59Z")
    assert before["findings"]["key1"][0]["verified_at"] is None
    after = lifecycle.timeline(events, as_of="2026-06-16T23:59:59Z")
    assert after["findings"]["key1"][0]["verified_at"] is not None


def test_newer_positive_evidence_overrides_an_older_passing_proof():
    _, rows = episodes([
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("verification", observed="2026-06-15T10:00:00Z", passed=True, target_state="absent",
              visibility="complete"),
        event("observation", observed="2026-06-16T10:00:00Z", active=True),
    ])
    assert len(rows) == 2
    assert rows[0]["status"] == "verified"
    assert rows[1]["status"] == "open" and rows[1]["recurrence_at"] == "2026-06-16T10:00:00.000000Z"


def test_unknown_visibility_never_closes():
    _, rows = episodes([
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("verification", observed="2026-06-15T10:00:00Z", passed=True, target_state="absent",
              visibility="unknown"),
    ])
    assert rows[0]["verified_at"] is None
    assert rows[0]["visibility"] == "unknown"
    assert rows[0]["status"] == "open"


def test_suppression_accepted_risk_and_manual_closure_do_not_fabricate_remediation():
    for status, expected in (("suppressed", "suppressed"), ("accepted_risk", "accepted_risk"),
                             ("false_positive", "false_positive"), ("resolved", "closed_manual")):
        _, rows = episodes([
            event("observation", observed="2026-06-10T10:00:00Z", active=True),
            event("decision", observed="2026-06-11T10:00:00Z", status=status),
        ])
        assert rows[0]["status"] == expected
        assert rows[0]["verified_at"] is None
        assert rows[0]["closure_at"] is None


def test_repeated_verification_keeps_the_first_closure_time():
    _, rows = episodes([
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("verification", observed="2026-06-15T10:00:00Z", passed=True, target_state="absent",
              visibility="complete"),
        event("verification", observed="2026-06-16T10:00:00Z", passed=True, target_state="absent",
              visibility="complete"),
    ])
    assert rows[0]["verified_at"] == "2026-06-15T10:00:00.000000Z"


def test_the_same_inputs_produce_the_same_projection_and_can_be_marked_incomplete():
    events = [
        event("observation", observed="2026-06-10T10:00:00Z", active=True),
        event("fix", observed="2026-06-15T10:00:00Z", state="deployed", applied_receipt=True),
        event("verification", observed="2026-06-15T11:00:00Z", passed=True, target_state="absent",
              visibility="complete"),
    ]
    first = lifecycle.timeline(events)
    shuffled = list(events)
    random.Random(4).shuffle(shuffled)
    assert lifecycle.timeline(shuffled) == first
    assert lifecycle.timeline(events, complete=False)["complete"] is False


def test_events_from_rows_keeps_observed_and_ingested_time_apart():
    events = lifecycle.events_from_rows(
        findings=[{"event_id": "e1", "ce": {"finding_key": "key1"}, "status_id": 1,
                   "observed_at": "2026-06-10T10:00:00Z", "ingested_at": "2026-06-11T10:00:00Z"}],
        verification_attempts=[{"event_id": "e2", "finding_key": "key1", "attempt_at": "2026-06-15T10:00:00Z",
                                "ingested_at": "2026-06-16T10:00:00Z", "passed": True,
                                "visibility": "complete", "target_state": "absent"}],
        decisions=[{"event_id": "e3", "finding_key": "key1", "status": "fixing",
                    "decided_at": "2026-06-12T10:00:00Z", "ingested_at": "2026-06-12T11:00:00Z"}],
        fix_events=[{"event_id": "e4", "finding_key": "key1", "state": "deployed",
                     "changed_at": "2026-06-15T09:00:00Z", "ingested_at": "2026-06-15T09:30:00Z",
                     "evidence": '{"applied_receipt": true}'}],
    )
    assert len(events) == 4
    observation = next(item for item in events if item["kind"] == "observation")
    assert observation["observed_at"] == "2026-06-10T10:00:00.000000Z"
    assert observation["ingested_at"] == "2026-06-11T10:00:00.000000Z"
    proof = next(item for item in events if item["kind"] == "verification")
    assert proof["ingested_at"] == "2026-06-16T10:00:00.000000Z"
    applied = next(item for item in events if item["kind"] == "fix")
    assert applied["applied_receipt"] is True