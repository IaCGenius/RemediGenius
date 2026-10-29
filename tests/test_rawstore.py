"""Raw evidence: content-addressed, write-once, buffered through an outage (roadmap CE-06)."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from rgtriage import contracts, rawstore

SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")
NOW = "2026-06-15T10:00:00Z"
PAGE = {"Findings": [{"Id": "one"}], "NextToken": None}


class Unreachable(BotoCoreError):
    fmt = "object store unreachable"


class MemoryBackend:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, dict]] = {}

    def put_if_absent(self, key, body, metadata):
        if key in self.objects:
            return "exists"
        self.objects[key] = (body, dict(metadata))
        return "created"

    def head(self, key):
        if key not in self.objects:
            return None
        body, metadata = self.objects[key]
        return rawstore.Head(size=len(body), metadata=dict(metadata))

    def get(self, key):
        return self.objects[key][0] if key in self.objects else None


class FakeS3:
    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.fail = None
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs["Key"]))
        if self.fail:
            raise self.fail
        key = kwargs["Key"]
        if key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}},
                              "PutObject")
        self.objects[key] = {"body": kwargs["Body"], "metadata": kwargs.get("Metadata") or {},
                             "sse": kwargs.get("ServerSideEncryption")}
        return {"ETag": '"x"'}

    def head_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")
        item = self.objects[key]
        return {"ContentLength": len(item["body"]), "Metadata": item["metadata"]}

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[key]["body"])}


@pytest.fixture
def memory():
    return MemoryBackend()


def store(backend, buffer=None, prefix="raw"):
    return rawstore.RawStore(backend, prefix=prefix, buffer=buffer)


def put(item, page=PAGE, observed_at=NOW, parameters=None):
    return item.put_json(page, scope=SCOPE, operation="ListFindings", observed_at=observed_at, parameters=parameters)


def test_put_is_content_addressed_and_write_once(memory):
    item = store(memory)
    first = put(item)
    second = put(item)
    assert first.durable and not first.buffered
    assert first.ref == second.ref
    assert len(memory.objects) == 1
    assert first.ref.key.startswith("raw/111122223333/us-east-1/inspector/2026/06/15/")
    assert first.ref.key.endswith(".json.gz")
    later = put(item, observed_at="2026-06-16T00:00:00Z")
    assert later.ref.key != first.ref.key
    assert len(memory.objects) == 2


def test_get_returns_the_original_page_and_verification_is_hash_based(memory):
    item = store(memory)
    result = put(item)
    assert item.get_json(result.ref) == PAGE
    assert item.verify(result.ref) is True
    key = result.ref.key
    memory.objects[key] = (b"tampered", memory.objects[key][1])
    assert item.verify(result.ref) is False
    with pytest.raises(rawstore.IntegrityError):
        item.get(result.ref)


def test_producer_metadata_is_stored(memory):
    item = store(memory)
    result = put(item, parameters={"severity": "HIGH"})
    metadata = memory.objects[result.ref.key][1]
    assert metadata["sha256"] == result.ref.sha256
    assert metadata["operation"] == "ListFindings"
    assert metadata["scope-account"] == "111122223333"
    assert metadata["parameters-hash"] == contracts.payload_hash({"severity": "HIGH"})
    assert result.ref.parameters_hash == contracts.payload_hash({"severity": "HIGH"})


def test_existing_key_with_other_bytes_is_an_integrity_error(memory):
    item = store(memory)
    first = put(item)
    memory.objects[first.ref.key] = (b"other bytes", {"sha256": "f" * 64})
    with pytest.raises(rawstore.IntegrityError):
        put(item)


def test_folder_backend_writes_once_and_refuses_traversal(tmp_path):
    backend = rawstore.FolderBackend(tmp_path / "raw")
    item = store(backend)
    first = put(item)
    second = put(item)
    assert first.ref == second.ref
    files = [p for p in (tmp_path / "raw").rglob("*") if p.is_file()]
    assert len([p for p in files if p.name.endswith(".json.gz")]) == 1
    assert item.get_json(first.ref) == PAGE
    with pytest.raises(rawstore.RawStoreError):
        backend.put_if_absent("../escape", b"x", {})


def test_s3_backend_uses_conditional_writes_and_sse():
    client = FakeS3()
    backend = rawstore.S3Backend("bucket", client=client)
    assert backend.put_if_absent("raw/a.json.gz", b"body", {"sha256": "a" * 64}) == "created"
    assert backend.put_if_absent("raw/a.json.gz", b"body", {"sha256": "a" * 64}) == "exists"
    head = backend.head("raw/a.json.gz")
    assert head.size == 4 and head.metadata["sha256"] == "a" * 64
    assert client.objects["raw/a.json.gz"]["sse"] == "AES256"
    assert backend.get("raw/a.json.gz") == b"body"
    assert backend.head("raw/missing.json.gz") is None


def test_s3_server_errors_are_temporary_and_client_errors_are_not():
    client = FakeS3()
    backend = rawstore.S3Backend("bucket", client=client)
    client.fail = ClientError({"Error": {"Code": "SlowDown"}, "ResponseMetadata": {"HTTPStatusCode": 503}}, "PutObject")
    with pytest.raises(rawstore.BackendUnavailable):
        backend.put_if_absent("raw/a.json.gz", b"body", {})
    client.fail = ClientError({"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}}, "PutObject")
    with pytest.raises(rawstore.RawStoreError) as denied:
        backend.put_if_absent("raw/a.json.gz", b"body", {})
    assert not isinstance(denied.value, rawstore.BackendUnavailable)
    client.fail = Unreachable()
    with pytest.raises(rawstore.BackendUnavailable):
        backend.put_if_absent("raw/a.json.gz", b"body", {})


def test_outage_buffers_then_flushes_in_order(tmp_path):
    client = FakeS3()
    client.fail = Unreachable()
    buffer = rawstore.RawBuffer(tmp_path / "buffer", limit_bytes=1024 * 1024)
    item = store(rawstore.S3Backend("bucket", client=client), buffer=buffer)
    first = put(item, page={"n": 1})
    second = put(item, page={"n": 2})
    assert first.buffered and second.buffered and not first.durable
    assert item.buffer_status()["objects"] == 2
    assert client.objects == {}
    client.fail = None
    result = item.flush()
    assert result == {"uploaded": 2, "remaining": 0}
    assert len(client.objects) == 2
    assert item.verify(first.ref) and item.verify(second.ref)


def test_buffer_limit_pauses_instead_of_dropping(tmp_path):
    client = FakeS3()
    client.fail = Unreachable()
    buffer = rawstore.RawBuffer(tmp_path / "buffer", limit_bytes=10)
    item = store(rawstore.S3Backend("bucket", client=client), buffer=buffer)
    with pytest.raises(rawstore.BufferFull):
        put(item)
    assert buffer.status()["objects"] == 0


def test_buffer_detects_corruption_before_upload(tmp_path):
    client = FakeS3()
    client.fail = Unreachable()
    buffer = rawstore.RawBuffer(tmp_path / "buffer", limit_bytes=1024)
    item = store(rawstore.S3Backend("bucket", client=client), buffer=buffer)
    result = put(item)
    meta = json.loads((tmp_path / "buffer" / f"{result.ref.sha256}.meta.json").read_text(encoding="utf-8"))
    assert meta["ref"]["sha256"] == result.ref.sha256
    (tmp_path / "buffer" / f"{result.ref.sha256}.json.gz").write_bytes(b"corrupt")
    client.fail = None
    with pytest.raises(rawstore.IntegrityError):
        item.flush()


def test_verify_many_reports_every_missing_object(memory):
    item = store(memory)
    present = put(item, page={"n": 1})
    missing = put(item, page={"n": 2})
    memory.objects.pop(missing.ref.key)
    problems = item.verify_many([present.ref, missing.ref])
    assert [p["sha256"] for p in problems] == [missing.ref.sha256]


def test_profile_factories_and_prefix(tmp_path):
    aws = contracts.StorageProfile(kind="aws", namespace="remedigenius", warehouse="s3://my-bucket/warehouse",
                                   catalog="glue")
    backend = rawstore.s3_backend(aws, client=FakeS3())
    assert backend.bucket == "my-bucket"
    local = contracts.StorageProfile(kind="local", namespace="remedigenius", warehouse=str(tmp_path / "warehouse"),
                                     catalog="sql", catalog_uri=str(tmp_path / "catalog.db"))
    folder = rawstore.folder_backend(local)
    assert folder.root == tmp_path
    prefixed = store(rawstore.FolderBackend(tmp_path / "raw"), prefix="evidence/raw")
    result = put(prefixed)
    assert result.ref.key.startswith("evidence/raw/111122223333/")
    assert rawstore.from_config({"storage": {"buffer_limit_mb": 1}}, local, home=tmp_path).buffer.limit_bytes == 1024 * 1024