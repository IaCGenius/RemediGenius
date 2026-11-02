import pytest
from rgtriage.athena_analytics import query
from rgtriage.athena_worker import unpack


def test_scoped_trend_pins_snapshot_and_keeps_values_out_of_sql():
    sql = query("trend", 7, "installation-test", {"findings": 123}, "111122223333", "us-east-1")
    assert "FOR VERSION AS OF 123" in sql
    assert "account_id = '111122223333'" in sql
    assert "count(DISTINCT ce.finding_key)" in sql
    assert "INTERVAL '7' DAY" in sql
    with pytest.raises(ValueError):
        query("trend", 7, "installation-test", {"findings": 123}, "' OR 1=1 --")


def test_cannot_silently_broaden_scan_counts():
    with pytest.raises(ValueError, match="installation-wide"):
        query("scan_coverage", 30, "test", {"coverage": 1, "scan_runs": 2}, "111122223333")


@pytest.mark.parametrize("days", [0, 91, "30; DROP TABLE findings"])
def test_bounds_query_window(days):
    with pytest.raises(ValueError):
        query("trend", days, "test", {"findings": 1})


def test_verification_uses_nested_scope_not_finding_count():
    sql = query("verification", 30, "test", {"verification_attempts": None}, "111122223333", "us-east-1")
    assert "target.account_id" in sql and "target.region" in sql
    assert "count(DISTINCT event_id) AS attempts" in sql


def test_vendor_sdk_alias_and_failure_are_handled():
    class Response:
        def __init__(self, failed):
            self.failed = failed

        def model_dump(self, **kwargs):
            assert kwargs == {"by_alias": True}
            return {"isError": self.failed, "content": [{"type": "text", "text": '{"rows": []}'}]}

    assert unpack(Response(False)) == {"rows": []}
    with pytest.raises(RuntimeError, match="rejected"):
        unpack(Response(True))


def test_coverage_units_are_checks_not_days():
    sql = query("coverage", 30, "test", {"coverage": 123})
    assert "AS collection_checks" in sql and "AS truncated_checks" in sql
