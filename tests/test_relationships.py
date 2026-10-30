"""Typed, time-aware relationship assertions (roadmap CE-19)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rgtriage import cache as cache_module, contracts, iceberg_store, queries, relationships as rel

NOW = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
DIGEST = "sha256:" + "a" * 64


def image(digest=DIGEST, **kw):
    return rel.image_entity(digest, **kw)


def workload(name="api", account="111122223333"):
    return rel.scoped_entity("workload", name, account_id=account, region="us-east-1", resource_type="ecs-service")


# ---------------------------------------------------------------- identity

def test_identity_is_scoped_so_equal_names_never_collapse():
    assert workload("api", "111122223333").key != workload("api", "999988887777").key
    assert workload("api", "111122223333").key == workload("api", "111122223333").key


def test_an_image_is_its_digest_and_a_tag_is_refused():
    assert image().key == image().key
    with pytest.raises(rel.RelationshipError, match="immutable sha256"):
        rel.image_entity("repo/app:latest")


def test_a_moving_tag_cannot_be_an_identity():
    """The same tag on two different digests is two entities; only the digest is stored."""
    first, second = image("sha256:" + "a" * 64, platform="linux/amd64"), image("sha256:" + "b" * 64, platform="linux/amd64")
    assert first.key != second.key
    with pytest.raises(rel.RelationshipError):
        rel.package_entity("app")


# ---------------------------------------------------------------- what may be believed

def test_an_observed_edge_needs_evidence_and_a_derived_edge_needs_a_version():
    with pytest.raises(rel.RelationshipError, match="retained evidence"):
        rel.Assertion(workload(), "runs", image(), status="observed")
    with pytest.raises(rel.RelationshipError, match="derivation version"):
        rel.Assertion(workload(), "runs", image(), status="derived")
    with pytest.raises(rel.RelationshipError, match="name the assertion"):
        rel.Assertion(workload(), "runs", image(), status="retracted")


def test_a_hypothesis_is_stored_but_can_never_authorize_anything():
    guess = rel.Assertion(workload(), "runs", image(), status="hypothesis")
    assert guess.authoritative is False and guess.may_authorize() is False
    observed = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "e" * 64,))
    assert observed.authoritative is True and observed.may_authorize() is True
    assert "hypothesis or retracted" in rel.explain(guess)["reason"]


def test_the_same_fact_is_the_same_assertion_id_however_often_it_arrives():
    one = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "e" * 64,), valid_from=NOW)
    two = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "f" * 64,), valid_from=NOW,
                        recorded_at=NOW + timedelta(hours=1))
    assert one.id == two.id
    rows = rel.new_rows([one, two])
    assert len(rows) == 1
    assert rel.new_rows([one], existing_ids=[one.id]) == []


# ---------------------------------------------------------------- history

def test_retraction_keeps_the_history_and_drops_the_edge_from_current():
    observed = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "e" * 64,), recorded_at=NOW)
    gone = rel.retract(observed, evidence=("sha256:" + "f" * 64,), recorded_at=NOW + timedelta(hours=1))
    assert gone.status == "retracted" and gone.supersedes == observed.id
    assert rel.superseded([observed, gone]) == {observed.id}
    assert rel.current([observed, gone]) == []  # nothing authoritative remains
    assert len(rel.new_rows([observed, gone])) == 2  # both rows are still stored


def test_a_correction_is_a_new_edge_and_the_old_one_stays_readable():
    old = rel.Assertion(workload(), "runs", image("sha256:" + "a" * 64), evidence=("sha256:" + "e" * 64,), recorded_at=NOW)
    new = rel.Assertion(workload(), "runs", image("sha256:" + "b" * 64), evidence=("sha256:" + "f" * 64,),
                        recorded_at=NOW + timedelta(hours=2))
    rows = rel.new_rows([old, new])
    assert len(rows) == 2 and {row["object_identity"] for row in rows} == {"sha256:" + "a" * 64, "sha256:" + "b" * 64}


def test_validity_intervals_are_respected_by_current():
    expired = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "e" * 64,),
                            valid_from=NOW - timedelta(days=2), valid_to=NOW - timedelta(days=1), recorded_at=NOW)
    assert rel.current([expired]) == []
    assert rel.current([expired], as_of=NOW - timedelta(days=2)) == [expired]  # inside its validity window
    live = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "e" * 64,), valid_from=NOW - timedelta(days=1))
    assert rel.current([live]) == [live]


# ---------------------------------------------------------------- derivation and rebuild

def test_derived_edges_are_deterministic_and_versioned():
    package = rel.package_entity("pkg:pypi/requests@2.31.0")
    first = rel.derive_image_packages(image(), [package])
    second = rel.derive_image_packages(image(), [package])
    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].derivation == rel.DERIVATION_IMAGE_PACKAGE and first[0].authoritative


def test_an_interrupted_rebuild_leaves_the_previous_complete_graph_active():
    previous = rel.Rebuild(version="v1", last_event="evt-10", complete=True)
    active, cursor = rel.rebuild(previous, [rel.derive_workload_image(workload(), image())],
                                 version="v2", last_event="evt-11", complete=False)
    assert active == [] and cursor == previous
    active, cursor = rel.rebuild(previous, [rel.derive_workload_image(workload(), image())],
                                 version="v2", last_event="evt-11", complete=True)
    assert len(active) == 1 and cursor.version == "v2" and cursor.complete


def test_graph_lag_is_reported_independently_of_operational_state():
    cursor = rel.Rebuild(version="v1", last_event="evt-10", complete=True)
    assert rel.graph_lag(cursor, "evt-10")["behind"] is False
    behind = rel.graph_lag(cursor, "evt-12", NOW)
    assert behind["behind"] is True and behind["graph_version"] == "v1" and behind["latest_event"] == "evt-12"
    assert "operational" not in behind  # the lag block says nothing about AWS health


# ---------------------------------------------------------------- queries

def _rows():
    seen = rel.Assertion(workload(), "runs", image(), evidence=("sha256:" + "e" * 64,), recorded_at=NOW)
    package = rel.package_entity("pkg:pypi/requests@2.31.0")
    derived = rel.derive_image_packages(image(), [package])[0]
    guess = rel.Assertion(workload(), "owned_by", rel.scoped_entity("owner", "team-a"), status="hypothesis")
    return [rel.row(item) for item in (seen, derived, guess)]


class _Storage:
    def __init__(self, rows):
        self._rows = rows

    def scan_rows(self, name, **_):
        return list(self._rows) if name == "relationships" else []


class _StubCache:
    def pending_count(self):
        return 0

    def undurable_decisions(self):
        return 0

    def watermark(self):
        return None


def _service(rows):
    service = queries.QueryService.__new__(queries.QueryService)
    service.cache = _StubCache()
    service.raw = None
    service.storage = _Storage(rows)
    service.installation_id = "inst"
    return service


def test_relationships_are_queryable_by_either_side_and_hypotheses_are_flagged():
    service = _service(_rows())
    answer = service.relationships(subject=workload().key)
    assert answer["count"] == 2  # the observed edge and the hypothesis; the derived edge starts at the image
    assert {row["status"] for row in answer["rows"]} == {"observed", "hypothesis"}
    assert {row["status"]: row["authoritative"] for row in answer["rows"]} == {"observed": True, "hypothesis": False}
    assert service.relationships(subject=workload().key, status="hypothesis")["count"] == 1
    assert service.relationships(subject=image().key)["count"] == 1  # image contains package
    assert service.relationships(object=image().key)["count"] == 1  # workload runs image


def test_a_graph_walk_is_bounded_in_depth_and_size():
    service = _service(_rows())
    one = service.graph(workload().key)
    assert one["depth"] == 1 and one["nodes"] and one["count"] >= 2
    deep = service.graph(workload().key, depth=99)
    assert deep["depth"] == queries.MAX_GRAPH_DEPTH
    capped = service.graph(workload().key, depth=2, limit=1)
    assert capped["count"] == 1 and capped["truncated"] is True
    with pytest.raises(queries.QueryError, match="entity"):
        service.graph("")
    with pytest.raises(queries.QueryError, match="depth"):
        service.graph(workload().key, depth=0)
    assert all(edge["authoritative"] in (True, False) for edge in deep["edges"])


def test_the_graph_round_trips_through_iceberg(tmp_path):
    profile = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                       catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    store = iceberg_store.IcebergStore.open(profile)
    store.ensure_tables()
    store.append_rows("relationships", _rows(), batch_id="batch_graph")
    service = queries.QueryService(_Cache(tmp_path / "desk.sqlite3"), store)
    answer = service.graph(workload().key, depth=2)
    assert answer["count"] >= 2 and answer["nodes"]
    assert service.relationships(subject=workload().identity)["count"] >= 2


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