"""The board card and page: one snapshot, no invented numbers, no score."""
from datetime import datetime, timedelta, timezone

from rgtriage import board

NOW = datetime(2026, 10, 30, 12, 30, tzinfo=timezone.utc)


def scan(**overrides):
    data = {
        "scanned_at": "2026-10-30T12:00:00Z",
        "profile": {"name": "acme", "accounts": [{"name": "prod", "account_id": "111122223333"}]},
        "issues": [
            {"priority": "P1", "score": 90, "title": "Public S3 bucket", "product": "Security Hub",
             "severity": "CRITICAL", "resources": ["payroll-export"], "accounts": ["prod"],
             "reasons": ["base", "configuration allows access from outside the account (+15)", "toxic combination (+10)"],
             "top_key": "3f9c2a7b1d04"},
            {"priority": "P1", "score": 80, "title": "Root without MFA", "product": "Security Hub",
             "severity": "HIGH", "resources": ["root"], "accounts": ["prod"],
             "reasons": ["base", "identity takeover risk (+10)"], "top_key": "cd82b0a18529"},
            {"priority": "P2", "score": 60, "title": "GuardDuty anomaly", "product": "GuardDuty",
             "severity": "MEDIUM", "resources": ["bucket"], "accounts": ["prod"],
             "reasons": ["base", "possible exfiltration (+20)"], "top_key": "286702ceefd8"},
        ],
        "coverage": [
            {"source": "securityhub", "account": "prod", "region": "us-east-1", "status": "ok"},
            {"source": "guardduty", "account": "prod", "region": "us-east-1", "status": "ok"},
            {"source": "health", "account": "prod", "region": "us-east-1", "status": "not_available"},
        ],
        "onboarding": {"known_accounts": 4, "not_covered": ["a", "b", "c"], "findings_only": []},
        "footprint": {"prod": {"enabled_regions": ["us-east-1", "eu-west-1"]}},
        "fixes": [],
        "changes": {"new": 2, "new_urgent": 1, "no_longer_active_count": 3,
                    "previous_scan": "2026-10-30T06:00:00Z"},
        "knowledge": {},
    }
    data.update(overrides)
    return data


def test_counts_and_coverage_are_read_over_known_not_readable():
    snap = board.snapshot(scan(), now=NOW)
    assert snap["counts"] == {"P1": 2, "P2": 1, "P3": 0, "P4": 0}
    assert snap["open"] == 3
    assert snap["state"] == "live"
    assert (snap["coverage"]["accounts"], snap["coverage"]["accounts_known"]) == (1, 4)


def test_card_keeps_the_count_and_the_bar_separate():
    issues = [dict(scan()["issues"][0], priority="P1")] + [
        {"priority": "P3", "score": 40, "title": f"Backlog {n}", "product": "Config", "severity": "LOW",
         "resources": [f"r{n}"], "accounts": ["prod"], "reasons": ["base"], "top_key": f"ref{n:08d}"}
        for n in range(44)
    ]
    snap = board.snapshot(scan(issues=issues), now=NOW)
    text = board.card(snap)
    assert "P1   1  █" in text
    assert "P3  44  ████████████" in text
    rules = [line for line in text.splitlines() if line and set(line) == {"─"}]
    assert rules and all(len(line) == 46 for line in rules)
    assert "None" not in text


def test_stale_card_refuses_to_call_itself_current():
    old = (NOW - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap = board.snapshot(scan(scanned_at=old), now=NOW)
    text = board.card(snap)
    assert snap["state"] == "stale"
    assert "○ STALE" in text
    assert "NOT CURRENT OPERATIONAL STATE." in text
    assert "● LIVE" not in text


def test_page_escapes_text_and_strips_score_arithmetic():
    data = scan()
    data["issues"][0]["title"] = "<script>alert(1)</script>"
    page = board.page(board.snapshot(data, now=NOW))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "(+15)" not in page and "(+10)" not in page
    assert "Static snapshot" in page


def test_page_does_not_invent_a_verified_fix():
    page = board.page(board.snapshot(scan(fixes=[]), now=NOW))
    assert "No fix has been proven by read-back yet." in page
    assert "0 fix verified" in page or "0 fixes verified" in page


def test_page_states_the_snapshot_and_the_coverage_gap():
    snap = board.snapshot(scan(), now=NOW)
    page = board.page(snap)
    assert snap["snapshot"] in page
    assert "1/4" in page
    assert "health" in page.lower()