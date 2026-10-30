"""Evidence-backed shared-cause campaigns and partial-rollout reconciliation (roadmap CE-21)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rgtriage import campaigns, rollout

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
PACKAGE = "pkg:apk/openssl@3.1.4"
PROOF = "sha256:" + "e" * 64
NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def entry(n: int, **kw) -> rollout.InventoryEntry:
    values = {"workload_id": f"api-{n}", "revision": "7", "account_id": "111122223333",
              "region": "us-east-1", "image": DIGEST, "findings": (f"key{n}",), "package": PACKAGE}
    values.update(kw)
    return rollout.InventoryEntry(**values)


def candidate(entries, **kw):
    return rollout.derive_campaign("camp-1", base_image=DIGEST, package=PACKAGE, inventory=entries, **kw)


def membership(n: int) -> campaigns.Membership:
    return campaigns.plan("camp-1", [entry(i).member(f"key{i}") for i in range(n)])


def test_only_workloads_running_the_campaign_image_become_members():
    good = entry(1)
    other_image, tagged = entry(2, image=OTHER), entry(3, image="team/app:latest")
    no_finding, app_layer = entry(4, findings=()), entry(5, origin="application")
    uncovered, unseen = entry(6, account_id="444455556666"), entry(7, observed=False)
    name_only = entry(8, package="pkg:apk/openssl@3.0.1")
    entries = [good, other_image, tagged, no_finding, app_layer, uncovered, unseen, name_only]
    result = candidate(entries, covered_accounts=["111122223333"])
    assert [member.target_id for member in result.membership.members] == [good.target_id]
    reasons = {item["target_id"]: item["reason"] for item in result.exclusions}
    assert reasons[other_image.target_id] == rollout.EX_OTHER_IMAGE
    assert reasons[tagged.target_id] == rollout.EX_IMAGE_UNPROVEN
    assert reasons[no_finding.target_id] == rollout.EX_NO_FINDING
    assert reasons[app_layer.target_id] == rollout.EX_OTHER_LAYER
    assert reasons[uncovered.target_id] == rollout.EX_ACCOUNT_UNCOVERED
    assert reasons[unseen.target_id] == rollout.EX_INVENTORY_MISSING
    assert reasons[name_only.target_id] == rollout.EX_NAME_ONLY
    assert result.excluded_count == 7
    assert all(item["detail"] for item in result.exclusions)  # every exclusion is inspectable


def test_a_campaign_without_a_proven_image_admits_nobody():
    result = rollout.derive_campaign("camp-1", base_image="team/app:latest", package=PACKAGE, inventory=[entry(1)])
    assert result.membership.count == 0
    assert {item["reason"] for item in result.exclusions} == {rollout.EX_IMAGE_UNPROVEN}


def test_the_plan_names_the_artifact_membership_stops_and_per_target_proof():
    plan = rollout.plan_for(candidate([entry(1), entry(2)]), predicate_id="ce.target-absent", predicate_version="3",
                            rule="the package is absent from the running image")
    body = plan.as_dict()
    assert body["artifact"]["digest"] == DIGEST and body["artifact"]["immutable"] is True
    assert body["membership_digest"] == candidate([entry(1), entry(2)]).membership.digest
    assert body["member_count"] == 2
    assert body["steps"] == list(rollout.STEPS)
    assert body["required_receipts"] == ["build", "build", "deploy", "verify"]
    assert body["required_per_target_proof"]["closes_all_members"] is False
    assert body["closes_all_members_on_patch"] is False
    assert any("approved one" in stop for stop in body["stop_conditions"])


def test_a_plan_needs_an_approved_predicate_and_a_proven_member():
    with pytest.raises(rollout.RolloutError, match="approved proof predicate"):
        rollout.plan_for(candidate([entry(1)]), predicate_id="", predicate_version="1", rule="r")
    with pytest.raises(rollout.RolloutError, match="no proven member"):
        rollout.plan_for(candidate([entry(2, image=OTHER)]), predicate_id="p", predicate_version="1", rule="r")


def test_a_thousand_target_rollout_reports_930_verified_20_awaiting_and_50_open():
    members = membership(1000)
    events = [rollout.TargetEvent(entry(i).target_id, "deploy", NOW, artifact_digest=DIGEST) for i in range(950)]
    events += [rollout.TargetEvent(entry(i).target_id, "proof", NOW + timedelta(minutes=5), passed=True,
                                   evidence_sha256=PROOF) for i in range(930)]
    result = rollout.reconcile(members, events, artifact_digest=DIGEST)
    assert result["counts"] == {"members": 1000, "verified": 930, "applied_pending_verification": 20,
                                "open": 50, "verified_not_applied": 0}
    assert result["closes_all_members_on_patch"] is False


def test_a_campaign_level_patch_or_tag_update_closes_nothing():
    members = membership(3)
    patched = rollout.reconcile(members, [rollout.TargetEvent(entry(0).target_id, "deploy", NOW,
                                                              artifact_digest=OTHER)], artifact_digest=DIGEST)
    assert patched["counts"]["open"] == 3
    assert patched["events"][0]["outcome"] == "rejected"
    # A tag or platform string is not the approved artifact either.
    with pytest.raises(rollout.RolloutError, match="immutable artifact"):
        rollout.reconcile(members, [], artifact_digest="team/app:latest")


def test_a_proof_without_a_deployment_is_counted_separately():
    members = membership(2)
    events = [rollout.TargetEvent(entry(0).target_id, "proof", NOW, passed=True, evidence_sha256=PROOF),
              rollout.TargetEvent(entry(1).target_id, "deploy", NOW, artifact_digest=DIGEST)]
    result = rollout.reconcile(members, events, artifact_digest=DIGEST)
    assert result["counts"] == {"members": 2, "verified": 0, "applied_pending_verification": 1, "open": 0,
                                "verified_not_applied": 1}
    proof = next(item for item in result["events"] if item["kind"] == "proof")
    assert proof["outcome"] == "rejected" and "counted separately" in proof["reason"]


def test_a_proof_without_evidence_is_refused():
    with pytest.raises(rollout.RolloutError, match="retained evidence"):
        rollout.TargetEvent(entry(0).target_id, "proof", NOW, passed=True)


def test_rollback_reopens_the_target_without_erasing_the_success():
    members = membership(1)
    target = entry(0).target_id
    events = [rollout.TargetEvent(target, "deploy", NOW, artifact_digest=DIGEST),
              rollout.TargetEvent(target, "proof", NOW + timedelta(minutes=1), passed=True, evidence_sha256=PROOF),
              rollout.TargetEvent(target, "rollback", NOW + timedelta(hours=2), reason="error rate rose")]
    result = rollout.reconcile(members, events, artifact_digest=DIGEST)
    assert result["counts"]["open"] == 1 and result["counts"]["verified"] == 0
    assert [item["kind"] for item in result["history"][target]] == ["deploy", "proof", "rollback"]
    assert result["history"][target][1]["outcome"] == "accepted"
    assert result["recurrences"][0]["reason"] == "error rate rose"


def test_a_new_occurrence_is_open_and_a_stranger_needs_a_new_version():
    members = membership(1)
    target = entry(0).target_id
    events = [rollout.TargetEvent(target, "deploy", NOW, artifact_digest=DIGEST),
              rollout.TargetEvent(target, "proof", NOW + timedelta(minutes=1), passed=True, evidence_sha256=PROOF),
              rollout.TargetEvent(target, "recurrence", NOW + timedelta(days=1), reason="the finding returned"),
              rollout.TargetEvent("111122223333:api-999@7", "deploy", NOW, artifact_digest=DIGEST)]
    result = rollout.reconcile(members, events, artifact_digest=DIGEST)
    assert result["counts"]["open"] == 1 and len(result["recurrences"]) == 1
    stranger = [item for item in result["events"] if item["outcome"] == "ignored"]
    assert stranger and "new version" in stranger[0]["reason"]


def test_reconcile_is_deterministic_regardless_of_event_order():
    members = membership(3)
    events = [rollout.TargetEvent(entry(i).target_id, "deploy", NOW, artifact_digest=DIGEST) for i in range(3)]
    events += [rollout.TargetEvent(entry(0).target_id, "proof", NOW + timedelta(minutes=1), passed=True,
                                   evidence_sha256=PROOF)]
    assert rollout.reconcile(members, events, artifact_digest=DIGEST) == \
        rollout.reconcile(members, list(reversed(events)), artifact_digest=DIGEST)


def test_state_rows_keep_the_reconciled_state_and_the_proof_evidence():
    members = membership(2)
    target = entry(0).target_id
    result = rollout.reconcile(members, [rollout.TargetEvent(target, "deploy", NOW, artifact_digest=DIGEST),
                                         rollout.TargetEvent(target, "proof", NOW, passed=True,
                                                             evidence_sha256=PROOF)], artifact_digest=DIGEST)
    rows = rollout.state_rows(result, members)
    by_target = {row["target_id"]: row for row in rows["campaign_members"]}
    assert by_target[target]["state"] == "verified"
    assert by_target[target]["evidence_sha256"] == PROOF
    assert by_target[entry(1).target_id]["state"] == "open"
    assert [row["ordinal"] for row in rows["campaign_members"]] == [1, 2]