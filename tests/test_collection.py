"""Resumable collection scopes and raw page recording (roadmap CE-07)."""
from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from rgtriage import cache as cache_module
from rgtriage import collect, collection, rawstore

ACCOUNT = "111122223333"


def setup(tmp_path):
    cache = cache_module.Cache(tmp_path / "desk.sqlite3", timeout=1)
    raw = rawstore.RawStore(rawstore.FolderBackend(tmp_path / "raw"))
    return cache, raw


def account() -> dict:
    return {"name": "desk", "account_id": ACCOUNT}


def finding(n: int = 1) -> dict:
    return {"key": f"key{n}", "source": "inspector", "native_id": f"n{n}", "account": ACCOUNT,
            "region": "us-east-1", "title": f"t{n}", "severity": "HIGH", "resource": {"id": f"i-{n}"}}


def test_scope_progress_and_resume(tmp_path):
    cache, raw = setup(tmp_path)
    run = collection.CollectionRun(cache, raw, "run-1")
    scope = run.scope(account(), "us-east-1", "inspector")
    run.begin_scope(scope)
    page = run.record_page(scope, "ListFindings", {"Findings": [{"Id": "one"}]}, {"severity": "HIGH"})
    assert raw.verify(page)
    assert run.record_page(scope, "ListFindings", {"Findings": []}).sha256 != page.sha256
    result = run.record_result(scope, [finding(n) for n in range(1000)], {"truncated": False})
    assert len(raw.get_json(result)["findings"]) == 1000
    run.complete_scope(scope, count=1000)
    progress = cache.progress_for_run("run-1")
    assert len(progress) == 1 and progress[0]["status"] == "complete"
    assert progress[0]["pages"] == 2 and progress[0]["items"] == 1000 and progress[0]["completeness"] == "ok"
    assert run.complete() is True

    resumed = collection.CollectionRun(cache, raw, "run-1")
    again = resumed.begin_scope(scope)
    assert again["status"] == "complete"
    assert resumed.pending() == []


def test_one_failed_source_does_not_erase_the_others(tmp_path):
    cache, raw = setup(tmp_path)
    run = collection.CollectionRun(cache, raw, "run-2")
    good = run.scope(account(), "us-east-1", "inspector")
    bad = run.scope(account(), "us-east-1", "securityhub")
    run.begin_scope(good)
    run.record_result(good, [finding(1)], {"truncated": False})
    run.complete_scope(good, count=1)
    run.begin_scope(bad)
    run.fail_scope(bad, status="denied", note="AccessDenied")
    progress = {row["source"]: row for row in cache.progress_for_run("run-2")}
    assert progress["inspector"]["status"] == "complete"
    assert progress["securityhub"]["status"] == "failed" and progress["securityhub"]["completeness"] == "denied"
    assert run.complete() is False
    assert [row["source"] for row in run.pending()] == ["securityhub"]


class FakeClient:
    def get_paginator(self, operation):
        return FakePaginator()


class FakePaginator:
    resume_token = None

    def paginate(self, **kwargs):
        return self

    def __iter__(self):
        yield {"Items": [1]}
        yield {"Items": [2]}


def test_run_one_records_pages_and_the_scope_result(tmp_path, monkeypatch):
    cache, raw = setup(tmp_path)
    run = collection.CollectionRun(cache, raw, "run-3")

    def collector(session, account, region, opts):
        collect.paginate(FakeClient(), "list_things", "Items", 10, Foo="bar")
        return [finding(1)], {"truncated": False}

    monkeypatch.setitem(collect.COLLECTORS, "inspector", collector)
    findings, entry = collect.run_one("inspector", None, account(), "us-east-1", {}, run)
    assert entry["status"] == "ok" and len(findings) == 1
    assert findings[0]["collected_from"] == ["inspector", ACCOUNT, "us-east-1"]
    progress = cache.progress_for_run("run-3")[0]
    assert progress["status"] == "complete" and progress["pages"] == 2 and progress["items"] == 1
    objects = [path for path in (tmp_path / "raw").rglob("*.json.gz")]
    assert len(objects) == 3  # two recorded pages and the normalized scope result
    assert run.result_refs["111122223333/us-east-1/inspector/"]


def test_concurrent_collection_scopes_share_the_cache(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    cache, raw = setup(tmp_path)
    run = collection.CollectionRun(cache, raw, "run-5")

    def collect_scope(source):
        scope = run.scope(account(), "us-east-1", source)
        run.begin_scope(scope)
        run.record_page(scope, "ListFindings", {"Findings": []})
        run.record_result(scope, [finding(1)], {"truncated": False})
        run.complete_scope(scope, count=1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(collect_scope, ("inspector", "guardduty", "config", "accessanalyzer")))
    progress = cache.progress_for_run("run-5")
    assert len(progress) == 4 and all(row["status"] == "complete" for row in progress)
    assert run.pending() == []


def test_run_one_failure_keeps_partial_coverage(tmp_path, monkeypatch):
    cache, raw = setup(tmp_path)
    run = collection.CollectionRun(cache, raw, "run-4")

    def collector(session, account, region, opts):
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "ListFindings")

    monkeypatch.setitem(collect.COLLECTORS, "inspector", collector)
    findings, entry = collect.run_one("inspector", None, account(), "us-east-1", {}, run)
    assert findings == [] and entry["status"] == "denied"
    progress = cache.progress_for_run("run-4")[0]
    assert progress["status"] == "failed" and progress["completeness"] == "denied"