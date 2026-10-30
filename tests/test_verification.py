"""Versioned, target-bound independent verification (roadmap CE-18)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rgtriage import cache as cache_module, contracts, iceberg_store, queries, verification as ver

NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
EVIDENCE = "e" * 64


def predicate(version="v1", **kw):
    return ver.Predicate("ce.public-bucket", version, "s3-no-public-policy", {"bucket": "b"}, **kw)


def target(generation="gen-1", digest="sha256:" + "a" * 64, account="111122223333", region="us-east-1"):
    return ver.Target("t-1", "inst-1", account, region, generation, digest)


def observation(outcome="pass", *, pred=None, tgt=None, **kw):
    base = dict(target=tgt or target(), predicate=pred or predicate(), outcome=outcome, verifier="rgcheck",
                observed_at=NOW, evidence_sha256=EVIDENCE)
    base.update(kw)
    return ver.Observation(**base)


def test_a_bound_passing_proof_verifies_the_current_target():
    verdict = ver.evaluate(observation(), approved=target(), now=NOW)
    assert verdict["verified"] is True and verdict["problems"] == []
    assert verdict["predicate_version"] == "v1" and verdict["verifier"] == "rgcheck"


@pytest.mark.parametrize("changed,problem", [
    ({"account": "999988887777"}, "account"),
    ({"region": "eu-west-1"}, "region"),
    ({"generation": "gen-2"}, "generation"),
    ({"digest": "sha256:" + "b" * 64}, "artifact"),
])
def test_a_proof_for_another_target_cannot_verify_the_approved_one(changed, problem):
    other = target(**changed) if changed.keys() & {"generation", "digest", "account", "region"} else target()
    verdict = ver.evaluate(observation(tgt=other), approved=target(), now=NOW)
    assert verdict["verified"] is False and problem in verdict["reason"]


def test_the_account_never_falls_back_to_another_configured_one():
    verdict = ver.evaluate(observation(account_id="999988887777"), approved=target(), now=NOW)
    assert verdict["verified"] is False and "another account" in verdict["reason"]


def test_a_truncated_or_partial_read_never_closes_and_stays_an_attempt():
    truncated = ver.evaluate(observation(truncated=True), approved=target(), now=NOW)
    partial = ver.evaluate(observation(partial=True), approved=target(), now=NOW)
    assert truncated["verified"] is False and "truncated" in truncated["reason"]
    assert partial["verified"] is False and "partial" in partial["reason"]
    row = ver.attempt_row(observation(truncated=True), truncated)
    assert row["verified"] is False and row["truncated"] is True and row["outcome"] == "pass"


def test_stale_evidence_and_unaccepted_clock_skew_cannot_verify():
    stale = ver.evaluate(observation(observed_at=NOW - timedelta(hours=8)), approved=target(), now=NOW)
    assert stale["verified"] is False and "stale" in stale["reason"]
    skewed = ver.evaluate(observation(clock_skew_seconds=900), approved=target(), now=NOW)
    assert skewed["verified"] is False and "clock skew" in skewed["reason"]
    future = ver.evaluate(observation(observed_at=NOW + timedelta(hours=1)), approved=target(), now=NOW)
    assert future["verified"] is False and "future" in future["reason"]


def test_failed_error_and_inconclusive_attempts_are_persisted_with_their_verifier():
    for outcome in ("fail", "error", "inconclusive"):
        verdict = ver.evaluate(observation(outcome), approved=target(), now=NOW)
        row = ver.attempt_row(observation(outcome), verdict)
        assert row["verified"] is False and row["outcome"] == outcome
        assert row["verifier"] == "rgcheck" and row["predicate_version"] == "v1" and row["predicate_digest"]


def test_a_provider_resolution_is_a_separate_event_and_never_upgrades_a_proof():
    failed = ver.evaluate(observation("fail"), approved=target(), now=NOW)
    resolution = ver.provider_resolution(observation("fail"), resolved_at=NOW, evidence_sha256=EVIDENCE)
    assert failed["verified"] is False
    assert resolution["kind"] == "provider_resolution" and resolution["affects_technical_proof"] is False
    passing = ver.evaluate(observation(), approved=target(), now=NOW)
    assert passing["provider_acknowledged"] is False and passing["verified"] is True


def test_the_policy_decides_whether_a_targeted_check_may_close():
    passing = ver.evaluate(observation(), approved=target(), now=NOW)
    provider_only = dict(passing, provider_acknowledged=False)
    assert ver.may_close(passing, ver.POLICY_TARGETED) is True
    assert ver.may_close(provider_only, ver.POLICY_PROVIDER) is False
    assert ver.may_close({**passing, "provider_acknowledged": True}, ver.POLICY_PROVIDER) is True
    with pytest.raises(ver.VerificationError, match="unknown verification policy"):
        ver.may_close(passing, "whatever")


def test_attempt_ids_are_deterministic_and_attempts_are_queryable(tmp_path):
    item = observation()
    verdict = ver.evaluate(item, approved=target(), now=NOW)
    first, second = ver.attempt_row(item, verdict), ver.attempt_row(item, verdict)
    assert first["attempt_id"] == second["attempt_id"]

    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = iceberg_store.IcebergStore.open(profile)
    store.ensure_tables()
    later = observation("fail", observed_at=NOW + timedelta(minutes=5))
    failures = ver.evaluate(later, approved=target(), now=NOW + timedelta(minutes=5))
    store.append_rows("target_verifications", [first, ver.attempt_row(later, failures)], batch_id="batch_proofs")
    service = queries.QueryService(_Cache(tmp_path / "desk.sqlite3"), store)
    answer = service.verifications(target_id="t-1")
    assert answer["count"] == 2 and answer["verified"] is False  # newest attempt is the failure
    assert {row["verifier"] for row in answer["rows"]} == {"rgcheck"}
    with pytest.raises(queries.QueryError, match="target_id is required"):
        service.verifications()


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