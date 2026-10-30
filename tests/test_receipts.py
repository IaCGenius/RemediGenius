"""Deployment receipts from existing CI/CD (roadmap CE-17)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rgtriage import cache as cache_module, contracts, iceberg_store, queries, receipts

NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def plan(**kw) -> receipts.Plan:
    base = dict(plan_digest="d" * 64, repo="IaCGenius/Remedigenius", commit="a" * 40, target_id="t-1",
                target_generation="gen-1", account_id="111122223333", campaign_id="camp-1", campaign_version=1,
                proposal="proposal-7")
    base.update(kw)
    return receipts.Plan(**base)


def build(**kw) -> receipts.Receipt:
    payload = {"repo": "IaCGenius/Remedigenius", "commit": "a" * 40, "build_invocation": "run-42",
               "artifact_digest": "sha256:" + "b" * 64}
    payload.update(kw)
    return receipts.Receipt(kind="build", producer="github-actions", external_id="run-42", payload=payload, actor="ci",
                            observed_at=NOW, received_at=NOW, evidence_sha256="e" * 64)


def deploy(**kw) -> receipts.Receipt:
    payload = {"artifact_digest": "sha256:" + "b" * 64, "deployment_revision": "rev-9", "target_id": "t-1",
               "target_generation": "gen-1", "account_id": "111122223333", "repo": "IaCGenius/Remedigenius"}
    payload.update(kw)
    return receipts.Receipt(kind="deploy", producer="codedeploy", external_id="dep-9", payload=payload, actor="ci",
                            observed_at=NOW, received_at=NOW)


def verify(**kw) -> receipts.Receipt:
    payload = {"passed": True, "target_id": "t-1", "target_generation": "gen-1", "account_id": "111122223333",
               "rule_version": "v1"}
    payload.update(kw)
    return receipts.Receipt(kind="verify", producer="rgtriage", external_id="proof-1", payload=payload)


def merge(**kw) -> receipts.Receipt:
    payload = {"pr_number": 48, "merge_commit": "a" * 40, "repo": "IaCGenius/Remedigenius"}
    payload.update(kw)
    return receipts.Receipt(kind="merge", producer="github", external_id="pr-48-merge", payload=payload)


# ---------------------------------------------------------------- matching the approved plan

def test_a_full_chain_satisfies_every_step_without_resubmitting_anything():
    chain = {"merge": merge(), "build": build(), "deploy": deploy(), "verify": verify()}
    result = receipts.reconcile(plan(), chain)
    assert result["resubmitted"] is False
    assert result["steps"] == {"merged": True, "built": True, "deployed": True, "verified": True}
    assert set(result["facts"]) == {"merge", "build", "deploy", "verify"}
    assert result["facts"]["build"]["evidence_sha256"] == "e" * 64


def test_a_merged_pull_request_alone_is_not_a_deployment_or_a_verification():
    result = receipts.reconcile(plan(), {"merge": merge()})
    assert result["steps"]["merged"] is True
    assert result["steps"]["deployed"] is False and result["steps"]["verified"] is False
    assert result["deployed"] is False and result["verified"] is False


def test_a_green_build_alone_does_not_mark_a_target_deployed():
    result = receipts.reconcile(plan(), {"build": build()})
    assert result["steps"]["built"] is True and result["deployed"] is False
    assert receipts.satisfies("deployed", "build") is False
    assert receipts.satisfies("deployed", "deploy") is True


@pytest.mark.parametrize("changed,problem", [
    ({"repo": "someone/else"}, "repository"),
    ({"commit": "c" * 40}, "commit"),
])
def test_a_build_for_another_repository_or_commit_is_rejected(changed, problem):
    outcome = receipts.ingest(plan(), build(**changed))
    assert outcome["action"] == receipts.STATUS_REJECTED
    assert problem in outcome["reason"]


def test_a_deployment_for_another_account_or_generation_is_rejected():
    other_account = receipts.ingest(plan(), deploy(account_id="999988887777"))
    assert other_account["action"] == receipts.STATUS_REJECTED and "account" in other_account["reason"]
    old_generation = receipts.ingest(plan(), deploy(target_generation="gen-0"))
    assert old_generation["action"] == receipts.STATUS_REJECTED and "generation" in old_generation["reason"]
    other_target = receipts.ingest(plan(), deploy(target_id="t-2"))
    assert other_target["action"] == receipts.STATUS_REJECTED and "target" in other_target["reason"]


def test_a_deployment_of_a_different_artifact_cannot_satisfy_the_built_one():
    outcome = receipts.ingest(plan(), deploy(artifact_digest="sha256:" + "c" * 64),
                              expected_artifact="sha256:" + "b" * 64)
    assert outcome["action"] == receipts.STATUS_REJECTED and "artifact" in outcome["reason"]


def test_a_plan_without_approval_or_proposal_identity_stays_unresolved():
    result = receipts.reconcile(plan(plan_digest="", proposal=""), {"deploy": deploy(), "verify": verify()})
    problems = " | ".join(item["problems"][0] for item in result["unresolved"])
    assert "no digest" in problems or "no approved plan digest" in problems
    assert "proposal identity" in problems
    assert result["deployed"] is False and result["verified"] is False


# ---------------------------------------------------------------- idempotency

def test_an_identical_replay_is_a_duplicate_not_a_second_fact():
    first = receipts.ingest(plan(), build())
    second = receipts.ingest(plan(), build(), {first["identity"]: first["payload_digest"]})
    assert first["action"] == receipts.STATUS_ACCEPTED
    assert second["action"] == receipts.STATUS_DUPLICATE


def test_a_changed_payload_under_the_same_identity_is_quarantined():
    first = receipts.ingest(plan(), build())
    changed = receipts.ingest(plan(), build(artifact_digest="sha256:" + "d" * 64),
                              {first["identity"]: first["payload_digest"]})
    assert changed["action"] == receipts.STATUS_QUARANTINED
    assert "different payload" in changed["reason"]


def test_the_identity_is_the_producers_own_id_not_a_timestamp():
    one = build()
    two = build()
    two = receipts.Receipt(kind=two.kind, producer=two.producer, external_id=two.external_id, payload=dict(two.payload),
                           actor=two.actor, observed_at=datetime(2026, 6, 16, tzinfo=timezone.utc))
    assert one.identity == two.identity and one.payload_digest == two.payload_digest


def test_only_configured_producers_are_accepted():
    outcome = receipts.ingest(plan(), build(), trusted={"codedeploy"})
    assert outcome["action"] == receipts.STATUS_REJECTED and "not configured as trusted" in outcome["reason"]
    assert receipts.ingest(plan(), build(), trusted={"github-actions"})["action"] == receipts.STATUS_ACCEPTED
    result = receipts.reconcile(plan(), {"build": build()}, trusted={"codedeploy"})
    assert result["steps"]["built"] is False and result["unresolved"][0]["kind"] == "build"


# ---------------------------------------------------------------- rows and queries

def test_rows_keep_the_outcome_and_the_producer_for_every_receipt():
    item = build()
    outcome = receipts.ingest(plan(), item)
    row = receipts.rows(plan(), item, outcome)[0]
    assert row["status"] == "accepted" and row["producer"] == "github-actions" and row["kind"] == "build"
    assert row["plan_digest"] == "d" * 64 and row["proposal"] == "proposal-7" and row["target_id"] == "t-1"
    assert row["payload_digest"] == item.payload_digest and row["evidence_sha256"] == "e" * 64
    assert '"build_invocation":"run-42"' in row["payload"]
    rejected = receipts.rows(plan(), build(repo="x/y"), receipts.ingest(plan(), build(repo="x/y")))[0]
    assert rejected["status"] == "rejected" and rejected["reason"]


def test_evidence_refs_are_normalised_or_refused():
    assert receipts.evidence_ref("a" * 64) == "sha256:" + "a" * 64
    with pytest.raises(receipts.ReceiptError, match="64 lowercase hex"):
        receipts.evidence_ref("not-a-digest")


def test_the_chain_is_queryable_with_producer_and_evidence_provenance(tmp_path):
    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = iceberg_store.IcebergStore.open(profile)
    store.ensure_tables()
    chain_plan = plan()
    rows = []
    for item in (merge(), build(), deploy(), verify()):
        rows.extend(receipts.rows(chain_plan, item, receipts.ingest(chain_plan, item)))
    store.append_rows("deployment_receipts", rows, batch_id="batch_receipts")

    service = queries.QueryService(_Cache(tmp_path / "desk.sqlite3"), store)
    answer = service.receipts(target_id="t-1")
    assert answer["count"] == 4 and answer["steps"] == ["build", "deploy", "merge", "verify"]
    assert {row["producer"] for row in answer["rows"]} == {"github", "github-actions", "codedeploy", "rgtriage"}
    by_campaign = service.receipts(campaign_id="camp-1")
    assert by_campaign["count"] == 4
    with pytest.raises(queries.QueryError, match="target_id or campaign_id"):
        service.receipts()


class _Cache:
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