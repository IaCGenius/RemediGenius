"""Lifecycle correctness: complete coverage, unknown visibility and persisted proof attempts (CE-02…CE-04)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rgtriage import fixes, store

ACCOUNT = "111122223333"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PROOF = {"service": "s3", "operation": "get-public-access-block", "parameters": {"Bucket": "b"},
         "expect": {"PublicAccessBlockConfiguration.BlockPublicPolicy": True}}


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))


def profile(accounts=(ACCOUNT,)) -> dict:
    return {"accounts": [{"name": f"desk-{n}", "account_id": a} for n, a in enumerate(accounts)]}


def decisions(state="deployed", account=ACCOUNT, proof=PROOF, status="fixing") -> dict:
    return {"key1": {"status": status, "reason": "we are fixing it", "by": "owner", "at": NOW,
                     "fix": {"state": state, "account": account, "source": "inspector", "region": "us-east-1",
                             "proof": proof, "owner": "team", "title": "t", "changed_at": NOW}}}


def coverage(status="ok", truncated=False, completeness="ok", account=ACCOUNT) -> list[dict]:
    return [{"source": "inspector", "account": f"desk-{account}", "account_id": account, "region": "us-east-1",
             "status": status, "truncated": truncated, "completeness": completeness, "count": 0}]


def finding() -> dict:
    return {"key": "key1", "source": "inspector", "account": ACCOUNT, "region": "us-east-1",
            "title": "open finding", "workflow": "NEW", "resource": {"name": "i-1", "id": "i-1"}}


def run(scan, data, check):
    records = fixes.advance(scan, profile(), data, check=check)
    return records[0], store.load_decisions()["key1"]


def test_truncated_absence_never_verifies_or_resolves():
    data = decisions()
    record, persisted = run({"findings": [], "coverage": coverage(truncated=True)}, data,
                            lambda *_: {"passed": True, "observed": {}})
    assert record["state"] == "deployed"
    assert persisted["status"] == "fixing"
    assert persisted["fix"]["visibility"] == "unknown"
    assert persisted["fix"]["last_check"]["outcome"] == "pass"


def test_a_complete_read_can_verify_and_resolve():
    record, persisted = run({"findings": [], "coverage": coverage()}, decisions(),
                            lambda *_: {"passed": True, "observed": {"ok": True}})
    assert record["state"] == "verified"
    assert persisted["status"] == "resolved"
    assert persisted["fix"]["visibility"] == "absent"


def test_an_unknown_tracked_account_never_uses_another_account():
    data = decisions(account="999999999999")
    seen = []

    def check(proof, account, region):
        seen.append(account)
        return {"passed": True, "observed": {}}

    record, persisted = run({"findings": [], "coverage": coverage()}, data, check)
    assert seen == []
    assert record["state"] == "deployed"
    assert persisted["fix"]["last_check"]["outcome"] == "inconclusive"
    assert "not configured" in persisted["fix"]["last_check"]["error"]


def test_verified_history_survives_denied_visibility():
    data = decisions(state="verified", status="resolved")
    data["key1"]["fix"]["last_check"] = {"at": "2026-06-14T10:00:00Z", "passed": True, "outcome": "pass"}
    record, persisted = run({"findings": [], "coverage": coverage(status="denied", completeness="denied")}, data,
                            lambda *_: {"passed": True, "observed": {}})
    assert record["state"] == "verified"
    assert persisted["status"] == "resolved"
    assert persisted["fix"]["visibility"] == "unknown"
    assert "reopened_at" not in persisted["fix"]


def test_new_positive_evidence_reopens():
    data = decisions(state="verified", status="resolved")
    record, persisted = run({"findings": [finding()], "coverage": coverage()}, data,
                            lambda *_: {"passed": True, "observed": {}})
    assert record["state"] == "reopened"
    assert persisted["status"] == "fixing"
    assert persisted["fix"]["reopened_at"]


def test_failed_attempt_is_persisted_even_when_state_does_not_move():
    data = decisions(state="deployed")
    data["key1"]["fix"]["last_check"] = {"at": "2026-06-14T10:00:00Z", "passed": True, "outcome": "pass"}
    record, persisted = run({"findings": [], "coverage": coverage()}, data,
                            lambda *_: {"passed": False, "observed": {"ok": False}})
    assert record["state"] == "deployed"
    assert persisted["fix"]["last_check"]["outcome"] == "fail"
    assert persisted["fix"]["last_check"]["passed"] is False
    assert persisted["fix"]["last_check"]["at"] > "2026-06-14T10:00:00Z"
    assert persisted["fix"]["visibility"] == "absent"


def test_no_proof_means_no_fabricated_attempt():
    data = decisions(proof=None)
    record, persisted = run({"findings": [], "coverage": coverage()}, data, lambda *_: pytest.fail("must not run"))
    assert "last_check" not in persisted["fix"]
    assert record["state"] == "deployed"


# ------------------------------------------------------------------ mark_changes uses the same predicate

def previous_scan(truncated=False, completeness="ok") -> dict:
    return {"scanned_at": "2026-06-15T09:00:00Z",
            "findings": [{"key": "abc", "source": "inspector", "account": ACCOUNT, "region": "us-east-1",
                          "title": "t", "priority": "P2", "resource": {"name": "i-1"},
                          "collected_from": ["inspector", ACCOUNT, "us-east-1"]}],
            "coverage": coverage(truncated=truncated, completeness=completeness)}


def scan(truncated=False, completeness="ok") -> dict:
    return {"scanned_at": "2026-06-15T10:00:00Z", "findings": [],
            "coverage": coverage(truncated=truncated, completeness=completeness)}


def test_no_longer_active_requires_complete_reads_on_both_sides(monkeypatch, tmp_path):
    store._write(store.latest_path(), previous_scan())
    marked = store.mark_changes(scan())
    assert marked["changes"]["no_longer_active_count"] == 1

    store._write(store.latest_path(), previous_scan())
    assert store.mark_changes(scan(truncated=True))["changes"]["no_longer_active_count"] == 0

    store._write(store.latest_path(), previous_scan(truncated=True))
    assert store.mark_changes(scan())["changes"]["no_longer_active_count"] == 0

    store._write(store.latest_path(), previous_scan())
    assert store.mark_changes(scan(completeness="partial"))["changes"]["no_longer_active_count"] == 0


def test_legacy_coverage_without_completeness_keeps_the_old_rule():
    assert store.coverage_complete({"status": "ok", "truncated": False}) is True
    assert store.coverage_complete({"status": "ok", "truncated": True}) is False
    assert store.coverage_complete({"status": "denied"}) is False
    assert store.coverage_complete({"status": "ok", "completeness": "unknown"}) is False