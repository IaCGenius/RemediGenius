"""Timeline, campaign and graph views with evidence, completeness and cutoff (roadmap CE-23)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rgtriage import campaigns, queries, relationships, views

IMAGE = "sha256:" + "a" * 64
PROOF = "sha256:" + "e" * 64
ACCOUNT = "111122223333"
NOW = datetime(2026, 6, 20, 10, 0, tzinfo=timezone.utc)


class _Cache:
    """The four pieces of the cache the query service reads; a view test never needs the rest."""

    def installation_id(self):
        return "inst-1"

    def pending_count(self):
        return 0

    def undurable_decisions(self):
        return 0

    def watermark(self):
        return None


class _Storage:
    def __init__(self, campaign_rows, member_rows):
        self.campaigns = campaign_rows
        self.members = member_rows
        self.receipts = []

    def scan_rows(self, name, *, limit=None, snapshot_id=None):
        return {"campaigns": self.campaigns, "campaign_members": self.members,
                "computation_receipts": self.receipts}.get(name, [])

    def last_snapshot_id(self, name):
        return 7

    def snapshot_at(self, name, as_of):
        return 7

    def append_rows(self, name, rows, *, batch_id="", content_hash=""):
        if name == "computation_receipts":
            self.receipts.extend(rows)
        return "snapshot-8"


def fixture(n: int = 1000, verified: int = 930, applied: int = 20):
    members = campaigns.plan("camp-1", [
        campaigns.Member(target_id=f"{ACCOUNT}:api-{i}@7", finding_key=f"key{i}", target_kind="workload",
                         account_id=ACCOUNT, region="us-east-1", resource_id=f"api-{i}", resource_generation="7")
        for i in range(n)])
    states, evidence = {}, {}
    for i in range(verified):
        states[f"{ACCOUNT}:api-{i}@7"] = "verified"
        evidence[f"{ACCOUNT}:api-{i}@7"] = PROOF
    for i in range(verified, verified + applied):
        states[f"{ACCOUNT}:api-{i}@7"] = "applied"
    rows = campaigns.rows(members, state_by_target=states, evidence_by_target=evidence)
    return rows["campaigns"], rows["campaign_members"]


def test_the_june_10_application_and_the_june_15_verification_are_different_facts():
    result = {"complete": True, "as_of": None, "event_count": 4, "findings": {"abc123": [{
        "finding_key": "abc123", "episode": 1, "first_observed_at": "2026-06-10T09:00:00+00:00",
        "last_observed_at": "2026-06-10T09:00:00+00:00", "first_ingested_at": "2026-06-16T08:00:00+00:00",
        "status": "verified", "applied_at": "2026-06-10T12:00:00+00:00", "verified_at": "2026-06-15T09:00:00+00:00",
        "closure_at": "2026-06-15T09:00:00+00:00", "closure_basis": "target-bound proof",
        "recurrence_at": None, "visibility": "complete", "manual_closed": False, "evidence_ids": ["e1"]}]}}
    view = views.finding_timeline(result, coverage={"inspector": "ok"}, watermark={"sequence": 12})
    row = view["findings"][0]
    assert row["observed_at"] == "2026-06-10T09:00:00+00:00"
    assert row["applied_at"] == "2026-06-10T12:00:00+00:00"
    assert row["verified_at"] == "2026-06-15T09:00:00+00:00"
    assert row["ingested_at"] == "2026-06-16T08:00:00+00:00"
    assert row["application_is_not_verification"] is True and row["verification_required"] is False
    assert row["late_ingestion"] is True and row["ingestion_delay_seconds"] == 514800.0
    assert row["source_coverage"] == {"inspector": "ok"} and row["projection_watermark"] == {"sequence": 12}
    assert view["state"] == views.STATE_OK and view["usable_for_decision"] is True


def test_an_incomplete_evidence_set_is_a_partial_view_not_a_current_one():
    view = views.finding_timeline({"complete": False, "reason": "one source was truncated", "findings": {}})
    assert view["state"] == views.STATE_PARTIAL
    assert view["usable_for_decision"] is False and view["is_current_operational_state"] is False
    assert "truncated" in view["reason"]


def test_all_thousand_members_are_paged_without_the_board_preview():
    campaign_rows, member_rows = fixture()
    storage = _Storage(campaign_rows, member_rows)
    service = queries.QueryService(_Cache(), storage)
    seen, cursor, rounds = [], 0, 0
    while True:
        page = service.dispatch("campaign", {"campaign_id": "camp-1", "after": cursor, "limit": 100})
        view = views.campaign_page(page)
        assert view["board_preview_used"] is False and view["source"] == "campaign_members"
        assert view["authoritative"] is False and view["counts_source"] == "membership_page"
        assert view["counts_note"]
        seen += [member["target_id"] for member in view["members"]]
        rounds += 1
        if not view["has_more"]:
            break
        cursor = view["next_cursor"]
    assert rounds == 10 and len(seen) == 1000 and len(set(seen)) == 1000
    assert view["total_members"] == 1000 and view["member_count"] == 1000


def test_only_an_attested_receipt_makes_the_campaign_counts_authoritative():
    campaign_rows, member_rows = fixture()
    storage = _Storage(campaign_rows, member_rows)
    service = queries.QueryService(_Cache(), storage)
    summary = service.dispatch("summary", {"campaign_id": "camp-1", "record": True})
    assert summary["attested"] is True
    assert summary["counts"] == {"verified": 930, "applied_pending_verification": 20, "open": 50,
                                 "verified_not_applied": 0, "member_count": 1000}
    page = service.dispatch("campaign", {"campaign_id": "camp-1", "limit": 10})
    view = views.campaign_page(page, receipt=summary["receipt"])
    assert view["authoritative"] is True and view["counts_source"] == "attested_computation"
    assert view["counts"] == {"verified": 930, "applied_pending_verification": 20, "open": 50}
    assert view["receipt_id"] == summary["receipt"]["receipt_id"]
    # recording is idempotent: the same inputs produce the same receipt id
    again = service.dispatch("summary", {"campaign_id": "camp-1", "record": True})
    assert again["receipt_recorded"] is False and len(storage.receipts) == 1
    # a receipt from a failed attestation is never authoritative
    failed = dict(summary["receipt"], attested=False, result="failed_attestation")
    assert views.campaign_page(page, receipt=failed)["authoritative"] is False


def test_the_scoped_service_reports_a_campaign_it_cannot_compute():
    campaign_rows, member_rows = fixture(3, 1, 1)
    service = queries.QueryService(_Cache(), _Storage(campaign_rows, member_rows))
    empty = service.dispatch("campaign", {"campaign_id": "missing"})
    assert views.campaign_page(empty)["state"] == views.STATE_UNAVAILABLE
    assert views.denied("campaign", "another installation owns this campaign")["state"] == views.STATE_DENIED
    assert views.unavailable("graph", "the graph has not been built")["usable_for_decision"] is False


def test_a_hypothesis_is_labelled_and_blocks_trusted_actions():
    image = relationships.image_entity(IMAGE)
    package = relationships.package_entity("pkg:apk/openssl@3.1.4")
    observed = relationships.Assertion(image, "contains", package, status="observed", evidence=("e" * 64,))
    guess = relationships.Assertion(image, "affected_by", relationships.scoped_entity("finding", "key1"),
                                    status="hypothesis")
    result = {"center": image.key, "depth": 1, "truncated": False,
              "edges": [relationships.row(observed), relationships.row(guess)]}
    view = views.graph_view(result, cutoff="2026-06-20T09:00:00Z", now=NOW)
    by_predicate = {edge["predicate"]: edge for edge in view["edges"]}
    assert by_predicate["contains"]["may_authorize"] is True
    assert by_predicate["affected_by"]["label"] == "hypothesis"
    assert by_predicate["affected_by"]["may_authorize"] is False
    assert by_predicate["affected_by"]["trusted_action_allowed"] is False
    assert view["trusted_actions_allowed"] is False
    assert view["hypotheses"] == [guess.id]
    assert {node["kind"] for node in view["nodes"]} == {"image", "package", "finding"}


def test_a_stale_graph_reports_its_cutoff_and_is_not_current_state():
    old = (NOW - timedelta(hours=9)).isoformat()
    result = {"center": "abc", "depth": 1, "edges": [], "graph": {"newest_assertion_at": old}}
    view = views.graph_view(result, now=NOW)
    assert view["state"] == views.STATE_STALE
    assert view["cutoff"] == old
    assert view["is_current_operational_state"] is False and view["usable_for_decision"] is False
    assert view["trusted_actions_allowed"] is True  # no edge claims anything


def test_a_fresh_derived_graph_is_usable_and_says_how_it_was_learned():
    image = relationships.image_entity(IMAGE)
    package = relationships.package_entity("pkg:apk/openssl@3.1.4")
    derived = relationships.Assertion(image, "contains", package, status="derived",
                                      derivation="ce.image-contains-package/v1")
    view = views.graph_view({"center": image.key, "depth": 1, "edges": [relationships.row(derived)]}, now=NOW)
    edge = view["edges"][0]
    assert edge["may_authorize"] is True and edge["label"] == "derived by ce.image-contains-package/v1"
    assert view["state"] == views.STATE_OK and view["trusted_actions_allowed"] is True