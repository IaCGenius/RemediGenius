"""Versioned campaign membership, approvals and per-target progress (roadmap CE-16)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rgtriage import campaigns, cache as cache_module, contracts, iceberg_store, queries

NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def members(count: int, *, start: int = 1, account: str = "111122223333"):
    return [campaigns.Member(target_id=f"t-{n}", finding_key=f"key{n}", account_id=account,
                             region="us-east-1", resource_id=f"i-{n}", resource_generation="g1")
            for n in range(start, start + count)]


def profile(tmp_path):
    return contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                    catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))


# ---------------------------------------------------------------- membership and approvals

def test_a_thousand_targets_are_all_members_while_the_preview_stays_bounded():
    membership = campaigns.plan("camp-1", members(1000), title="Image CVE")
    assert membership.count == 1000 and len(membership.targets()) == 1000
    preview = membership.preview()
    assert preview["member_count"] == 1000 and preview["preview_count"] == campaigns.PREVIEW_LIMIT
    assert preview["truncated"] is True and len(preview["members"]) == campaigns.PREVIEW_LIMIT
    assert preview["membership_digest"] == membership.digest


def test_the_digest_depends_on_membership_not_on_order_or_preview():
    forward = campaigns.plan("camp-1", members(100))
    backward = campaigns.plan("camp-1", list(reversed(members(100))))
    assert forward.digest == backward.digest
    extended = campaigns.plan("camp-1", members(101))
    assert extended.digest != forward.digest


def test_an_approval_matches_only_the_version_it_froze():
    first = campaigns.plan("camp-1", members(950))
    approval = campaigns.approve(first, "raj", at=NOW)
    campaigns.check_approval(approval, first)  # no raise

    grown = first.next_version(members(1000))
    assert grown.version == 2 and grown.digest != first.digest
    assert grown.added_since(first) == {f"t-{n}" for n in range(951, 1001)}
    with pytest.raises(campaigns.CampaignError, match="does not match the current membership"):
        campaigns.check_approval(approval, grown)


def test_a_changed_or_missing_person_cannot_approve():
    membership = campaigns.plan("camp-1", members(3))
    with pytest.raises(campaigns.CampaignError, match="needs a person"):
        campaigns.approve(membership, "")


def test_the_same_target_twice_with_two_identities_is_refused():
    duplicated = members(2) + [campaigns.Member(target_id="t-1", finding_key="other", account_id="999988887777")]
    with pytest.raises(campaigns.CampaignError, match="appears twice"):
        campaigns.plan("camp-1", duplicated)


def test_identical_duplicate_deliveries_do_not_inflate_the_scope():
    membership = campaigns.plan("camp-1", members(10) + members(10))
    assert membership.count == 10


# ---------------------------------------------------------------- progress

def test_progress_counts_verified_applied_and_open_separately():
    membership = campaigns.plan("camp-1", members(1000))
    applied = [f"t-{n}" for n in range(1, 951)]          # 950 deployed
    verified = [f"t-{n}" for n in range(1, 931)]          # 930 of those proved
    progress = campaigns.progress(membership, applied=applied, verified=verified)
    assert progress["verified"] == 930
    assert progress["applied_pending_verification"] == 20
    assert progress["open"] == 50
    assert progress["verified_not_applied"] == 0
    assert progress["membership_digest"] == membership.digest


def test_a_proof_for_something_never_deployed_does_not_reduce_open_work():
    membership = campaigns.plan("camp-1", members(10))
    progress = campaigns.progress(membership, applied=["t-1", "t-2"], verified=["t-1", "t-2", "t-9"])
    assert progress["verified"] == 2 and progress["open"] == 8
    assert progress["verified_not_applied"] == 1


def test_repeated_delivery_of_the_same_evidence_is_counted_once():
    membership = campaigns.plan("camp-1", members(5))
    progress = campaigns.progress(membership, applied=["t-1"] * 5, verified=["t-1"] * 5)
    assert progress["verified"] == 1 and progress["applied_pending_verification"] == 0 and progress["open"] == 4


def test_evidence_for_a_target_outside_the_campaign_is_ignored():
    membership = campaigns.plan("camp-1", members(3))
    progress = campaigns.progress(membership, applied=["t-99"], verified=["t-99"])
    assert progress["verified"] == 0 and progress["open"] == 3


# ---------------------------------------------------------------- rows, pagination and storage

def test_rows_are_ordinal_and_survive_paging_in_pages_of_one_hundred():
    membership = campaigns.plan("camp-1", members(1000), title="Image CVE")
    approval = campaigns.approve(membership, "raj", at=NOW)
    rows = campaigns.rows(membership, approval=approval,
                          state_by_target={f"t-{n}": "verified" for n in range(1, 6)})
    assert rows["campaigns"][0]["status"] == "approved" and rows["campaigns"][0]["approval_digest"] == membership.digest
    assert [row["ordinal"] for row in rows["campaign_members"][:3]] == [1, 2, 3]
    assert rows["campaign_members"][0]["state"] == "verified"

    seen, after = [], 0
    while True:
        page = campaigns.page(rows["campaign_members"], after=after, limit=100)
        seen.extend(row["target_id"] for row in page["members"])
        if not page["has_more"]:
            break
        after = page["next_cursor"]
    assert len(seen) == 1000 and len(set(seen)) == 1000
    replay = campaigns.page(rows["campaign_members"], after=0, limit=100)
    assert replay == campaigns.page(rows["campaign_members"], after=0, limit=100)


def test_the_membership_round_trips_through_iceberg(tmp_path):
    store = iceberg_store.IcebergStore.open(profile(tmp_path))
    store.ensure_tables()
    membership = campaigns.plan("camp-1", members(1000), title="Image CVE")
    approval = campaigns.approve(membership, "raj", at=NOW)
    rows = campaigns.rows(membership, approval=approval)
    store.append_rows("campaigns", rows["campaigns"], batch_id="batch_camp")
    store.append_rows("campaign_members", rows["campaign_members"], batch_id="batch_camp")

    service = queries.QueryService(_Cache(tmp_path / "desk.sqlite3"), store)
    listed = service.campaigns()
    assert listed["count"] == 1 and listed["rows"][0]["member_count"] == 1000
    first = service.campaign("camp-1", limit=100)
    assert first["found"] is True and first["version"] == 1 and first["member_count"] == 1000
    assert first["membership_digest"] == membership.digest and first["returned"] == 100
    second = service.campaign("camp-1", after=first["next_cursor"], limit=100)
    assert second["members"][0]["ordinal"] == 101
    assert service.campaign("missing")["found"] is False


class _Cache:
    """The three cache facts QueryService needs; campaigns are read from committed storage."""

    def __init__(self, path):
        self._cache = cache_module.Cache(path, timeout=1)

    def installation_id(self):
        return self._cache.installation_id()

    def pending_count(self):
        return 0

    def undurable_decisions(self):
        return 0

    def watermark(self):
        return None


def test_campaign_queries_are_registered_and_scoped():
    assert {"campaign", "campaigns", "relationships", "graph"} <= set(queries.HANDLERS)
    assert "campaign" not in queries.UNSUPPORTED
    service = queries.QueryService.__new__(queries.QueryService)
    service.cache, service.storage, service.raw, service.installation_id = None, None, None, "inst"
    with pytest.raises(queries.QueryError, match="does not accept"):
        service.dispatch("campaign", {"nope": 1})
    with pytest.raises(queries.QueryError, match="campaign_id is required"):
        service.campaign("")
    with pytest.raises(queries.QueryError, match="entity"):
        service.dispatch("graph")