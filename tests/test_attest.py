"""One approved, attested computation over campaign membership (roadmap CE-22)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from rgtriage import attest, campaigns, rollout

IMAGE = "sha256:" + "a" * 64
PROOF = "sha256:" + "e" * 64
EVIDENCE_SET = "b" * 64
ACCOUNT = "111122223333"
NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def member_rows(n: int = 1000, *, verified: int = 930, applied: int = 20, version: int = 1) -> list:
    """The synthetic fixture through the real chain: derive, reconcile, then the member rows the table holds."""
    entries = [rollout.InventoryEntry(workload_id=f"api-{i}", revision="7", account_id=ACCOUNT, region="us-east-1",
                                      image=IMAGE, findings=(f"key{i}",), package="pkg:apk/openssl@3.1.4")
               for i in range(n)]
    membership = rollout.derive_campaign("camp-1", base_image=IMAGE, package="pkg:apk/openssl@3.1.4",
                                         inventory=entries).membership
    if version != 1:
        membership = membership.next_version(membership.members)
    deployed = verified + applied
    events = [rollout.TargetEvent(f"{ACCOUNT}:api-{i}@7", "deploy", NOW, artifact_digest=IMAGE) for i in range(deployed)]
    events += [rollout.TargetEvent(f"{ACCOUNT}:api-{i}@7", "proof", NOW + timedelta(minutes=5), passed=True,
                                   evidence_sha256=PROOF) for i in range(verified)]
    result = rollout.reconcile(membership, events, artifact_digest=IMAGE)
    return rollout.state_rows(result, membership)["campaign_members"]


def params(rows, **kw) -> dict:
    values = {"campaign_id": "camp-1", "version": int(rows[0]["version"]), "installation_id": "inst-1",
              "evidence_set": EVIDENCE_SET}
    values.update(kw)
    return attest.params(**values)


def run(rows, **kw):
    execution = attest.execute(rows, params=params(rows, **kw), snapshot_id=42)
    return execution, attest.attest(execution, retained_rows=rows, snapshot_id=42)


def test_the_approved_code_is_the_one_pinned_in_review():
    assert attest.code_digest() == attest.APPROVED_CODE_DIGEST
    assert attest.APPROVED.digest() == attest.APPROVED.digest()
    assert attest.APPROVED.computation == "campaign_verification_summary"


def identity(row: dict) -> dict:
    return {key: row.get(key) or "" for key in ("target_id", "finding_key", "target_kind", "account_id", "region",
                                                "resource_id", "resource_generation")}


def test_the_thousand_target_fixture_produces_930_20_50_through_the_computation():
    rows = member_rows()
    execution, verdict = run(rows)
    assert verdict["attested"] is True and verdict["authoritative"] is True
    assert verdict["counts"] == {"verified": 930, "applied_pending_verification": 20, "open": 50,
                                 "verified_not_applied": 0, "member_count": 1000}
    expected = campaigns.plan("camp-1", [campaigns.Member(**identity(row)) for row in rows]).digest
    assert execution.output["membership_digest"] == expected
    assert execution.output["evidence_complete"] is True


def test_repeated_execution_over_the_same_inputs_is_reproducible():
    rows = member_rows(10, verified=6, applied=3)
    first, _ = run(rows)
    second, _ = run(rows)
    assert first.output_digest == second.output_digest
    assert first.receipt_id == second.receipt_id


def test_changed_code_or_contract_fails_attestation():
    rows = member_rows(10, verified=6, applied=3)
    execution, _ = run(rows)
    changed_code = attest.attest(execution, retained_rows=rows, snapshot_id=42, code="0" * 64)
    assert changed_code["attested"] is False and "code changed" in changed_code["reason"]
    other = attest.Contract(attest.COMPUTATION, "2", dict(attest.PARAMETERS), attest.REQUIRED_PARAMETERS,
                            attest.OUTPUT_FIELDS, "_reduce")
    changed_contract = attest.attest(execution, retained_rows=rows, snapshot_id=42, contract=other)
    assert changed_contract["attested"] is False and "contract changed" in changed_contract["reason"]


def test_another_membership_version_or_snapshot_fails_attestation():
    rows = member_rows(10, verified=6, applied=3)
    execution, _ = run(rows)
    other = attest.attest(execution, retained_rows=rows, snapshot_id=43)
    assert other["attested"] is False and "pinned one" in other["reason"]
    stale = [dict(row, version=2) for row in rows]
    moved = attest.attest(execution, retained_rows=stale, snapshot_id=42)
    assert moved["attested"] is False


def test_an_incomplete_evidence_set_fails_attestation():
    rows = member_rows(10, verified=6, applied=3)
    rows[0]["evidence_sha256"] = ""
    execution, verdict = run(rows)
    assert verdict["attested"] is False and "incomplete" in verdict["reason"]
    assert execution.output["verified"] == 5 and execution.output["applied_pending_verification"] == 4


def test_an_unauthorized_scope_fails_attestation():
    rows = member_rows(10, verified=6, applied=3)
    execution = attest.execute(rows, params=params(rows), snapshot_id=42)
    verdict = attest.attest(execution, retained_rows=rows, snapshot_id=42, accounts=["999999999999"])
    assert verdict["attested"] is False and "approved scope" in verdict["reason"]


def test_a_modified_output_fails_attestation():
    rows = member_rows(10, verified=6, applied=3)
    execution, _ = run(rows)
    tampered = replace(execution, output={**execution.output, "verified": 9})
    verdict = attest.attest(tampered, retained_rows=rows, snapshot_id=42)
    assert verdict["attested"] is False
    assert "does not match the retained inputs" in verdict["reason"]


def test_a_failed_attestation_is_retained_as_its_own_result():
    rows = member_rows(10, verified=6, applied=3)
    rows[0]["evidence_sha256"] = ""
    execution, verdict = run(rows)
    receipt = attest.receipt_row(execution, verdict, installation_id="inst-1")
    assert receipt["result"] == attest.RESULT_FAILED and receipt["attested"] is False
    assert attest.authoritative(receipt) is False
    assert "attested receipt" in attest.explain(receipt)
    assert receipt["receipt_id"] == execution.receipt_id


def test_parameters_are_an_allow_list():
    rows = member_rows(3, verified=1, applied=1)
    with pytest.raises(attest.AttestationError, match="does not accept"):
        attest.params(campaign_id="c", version=1, installation_id="i", sql="select *")
    with pytest.raises(attest.AttestationError, match="version must be an integer"):
        attest.params(campaign_id="c", version="1", installation_id="i")
    with pytest.raises(attest.AttestationError, match="sha256 hex"):
        attest.params(campaign_id="c", version=1, installation_id="i", evidence_set="not-a-digest")
    with pytest.raises(attest.AttestationError, match="campaign_id is required"):
        attest.params(version=1, installation_id="i")
    assert params(rows)["as_of"] == ""


def test_a_computation_needs_a_pinned_snapshot():
    rows = member_rows(3, verified=1, applied=1)
    with pytest.raises(attest.AttestationError, match="pinned input snapshot"):
        attest.execute(rows, params=params(rows), snapshot_id=None)


def test_a_missing_or_unauthorised_receipt_cannot_present_a_count():
    assert attest.authoritative(None) is False
    assert attest.authoritative({"result": attest.RESULT_FAILED, "attested": False}) is False
    assert "No attested receipt" in attest.explain({"problems": "[]"})
    rows = member_rows(10, verified=6, applied=3)
    execution, verdict = run(rows)
    receipt = attest.receipt_row(execution, verdict, installation_id="inst-1")
    assert attest.authoritative(receipt) is True
    assert "6 verified" in attest.explain(receipt)