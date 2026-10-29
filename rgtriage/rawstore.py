"""Content-addressed raw evidence in S3 or the workstation durable folder (roadmap CE-06).

Every collected AWS response is written once, before any fact derived from it is committed. The object key is
derived from the SHA-256 of the stored bytes, so an existing key means the same bytes are already there. S3
conditional writes (``If-None-Match: *``) make that write-once even with two writers. A short outage does not
drop data: responses wait in a bounded local buffer and collection pauses when it is full.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import config, contracts

META_SHA = "sha256"


class RawStoreError(RuntimeError):
    """Raw evidence could not be stored or verified."""


class BackendUnavailable(RawStoreError):
    """The object store is temporarily unreachable; the local buffer may hold the object."""


class BufferFull(RawStoreError):
    """The bounded local buffer is full; collection must pause rather than drop evidence."""


class IntegrityError(RawStoreError):
    """An object under a content-addressed key does not match the bytes that key promises."""


@dataclass(frozen=True, slots=True)
class Head:
    size: int
    metadata: dict


@dataclass(frozen=True, slots=True)
class RawPut:
    ref: contracts.RawRef
    durable: bool
    buffered: bool = False


@dataclass(frozen=True, slots=True)
class BufferedObject:
    ref: contracts.RawRef
    body_path: Path
    meta_path: Path
    size: int


def _relative_key(key: str) -> str:
    if not key or key.startswith("/") or "\\" in key or ".." in key.split("/"):
        raise RawStoreError(f"raw key must be a safe relative key: {key!r}")
    return key


class S3Backend:
    def __init__(self, bucket: str, *, prefix: str = "", client=None, sse: str = "AES256",
                 kms_key_id: str = ""):
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client or boto3.client("s3")
        self.sse = sse
        self.kms_key_id = kms_key_id

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{_relative_key(key)}" if self.prefix else _relative_key(key)

    def put_if_absent(self, key: str, body: bytes, metadata: dict) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        extra: dict[str, Any] = {"ServerSideEncryption": self.sse, "Metadata": metadata}
        if self.sse == "aws:kms" and self.kms_key_id:
            extra["SSEKMSKeyId"] = self.kms_key_id
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=body, IfNoneMatch="*", **extra)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            status = int((exc.response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
            if code in ("PreconditionFailed", "412") or status == 412:
                return "exists"
            if status >= 500 or code in ("SlowDown", "Throttling", "RequestTimeout", "ServiceUnavailable"):
                raise BackendUnavailable(f"S3 put failed temporarily: {code or status}") from exc
            raise RawStoreError(f"S3 put was refused: {code or status}: {exc}") from exc
        except BotoCoreError as exc:
            raise BackendUnavailable(f"S3 is unreachable: {exc}") from exc
        return "created"

    def head(self, key: str) -> Head | None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            result = self.client.head_object(Bucket=self.bucket, Key=self._key(key))
        except ClientError as exc:
            status = int((exc.response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if status == 404 or code in ("404", "NoSuchKey", "NotFound"):
                return None
            if status >= 500:
                raise BackendUnavailable(f"S3 head failed temporarily: {code or status}") from exc
            raise RawStoreError(f"S3 head was refused: {code or status}") from exc
        except BotoCoreError as exc:
            raise BackendUnavailable(f"S3 is unreachable: {exc}") from exc
        return Head(size=int(result.get("ContentLength", 0)), metadata=dict(result.get("Metadata") or {}))

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except ClientError as exc:
            status = int((exc.response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if status == 404 or code in ("404", "NoSuchKey", "NotFound"):
                return None
            if status >= 500:
                raise BackendUnavailable(f"S3 get failed temporarily: {code or status}") from exc
            raise RawStoreError(f"S3 get was refused: {code or status}") from exc
        except BotoCoreError as exc:
            raise BackendUnavailable(f"S3 is unreachable: {exc}") from exc


class FolderBackend:
    """The workstation durable folder. Write-once with O_EXCL; a sidecar keeps the same metadata S3 stores."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / _relative_key(key)).resolve()
        if self.root.resolve() not in path.parents:
            raise RawStoreError("raw key escapes the durable folder")
        return path

    def _meta_path(self, key: str) -> Path:
        return self._path(key + ".meta.json")

    def put_if_absent(self, key: str, body: bytes, metadata: dict) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return "exists"
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            path.unlink(missing_ok=True)
            raise
        tmp = self._meta_path(key).with_name(self._meta_path(key).name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(metadata, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self._meta_path(key))
        return "created"

    def head(self, key: str) -> Head | None:
        path = self._path(key)
        if not path.is_file():
            return None
        metadata = {}
        try:
            metadata = json.loads(self._meta_path(key).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            pass
        return Head(size=path.stat().st_size, metadata=metadata)

    def get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
        self._meta_path(key).unlink(missing_ok=True)


class RawBuffer:
    """Bounded local queue for raw objects during an object-store outage."""

    def __init__(self, root: Path | str, limit_bytes: int):
        self.root = Path(root)
        self.limit_bytes = max(0, int(limit_bytes))

    def _paths(self, sha: str) -> tuple[Path, Path]:
        return self.root / f"{sha}.json.gz", self.root / f"{sha}.meta.json"

    def put(self, ref: contracts.RawRef, body: bytes, metadata: dict) -> BufferedObject:
        used = self.status()["bytes"]
        if used + len(body) > self.limit_bytes:
            raise BufferFull(f"raw buffer limit reached ({used + len(body)} > {self.limit_bytes} bytes); "
                             "collection must pause")
        self.root.mkdir(parents=True, exist_ok=True)
        body_path, meta_path = self._paths(ref.sha256)
        if not body_path.exists():
            tmp = body_path.with_name(body_path.name + f".{os.getpid()}.tmp")
            tmp.write_bytes(body)
            os.replace(tmp, body_path)
        tmp = meta_path.with_name(meta_path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"ref": ref.as_dict(), "metadata": metadata}, sort_keys=True), encoding="utf-8")
        os.replace(tmp, meta_path)
        return BufferedObject(ref=ref, body_path=body_path, meta_path=meta_path, size=len(body))

    def items(self) -> list[BufferedObject]:
        if not self.root.is_dir():
            return []
        objects = []
        for meta_path in sorted(self.root.glob("*.meta.json")):
            sha = meta_path.name[: -len(".meta.json")]
            body_path, _ = self._paths(sha)
            if not body_path.is_file():
                continue
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                ref = contracts.RawRef.from_dict(data["ref"])
            except (ValueError, KeyError):
                continue
            objects.append(BufferedObject(ref=ref, body_path=body_path, meta_path=meta_path,
                                          size=body_path.stat().st_size))
        return objects

    def remove(self, item: BufferedObject) -> None:
        item.body_path.unlink(missing_ok=True)
        item.meta_path.unlink(missing_ok=True)

    def status(self) -> dict:
        items = self.items()
        return {"objects": len(items), "bytes": sum(item.size for item in items), "limit_bytes": self.limit_bytes}


class RawStore:
    def __init__(self, backend, *, prefix: str = "raw", buffer: RawBuffer | None = None):
        self.backend = backend
        self.prefix = _relative_key(prefix.strip("/")) if prefix and prefix.strip("/") else ""
        self.buffer = buffer

    def key(self, scope: contracts.Scope, observed_at: str, sha256: str) -> str:
        base = contracts.raw_key(scope, observed_at, sha256)
        if self.prefix and self.prefix != "raw":
            base = f"{self.prefix}/{base.split('/', 1)[1]}"
        return base

    def put(self, data: bytes, *, scope: contracts.Scope, operation: str, observed_at: str,
            parameters: Any | None = None) -> RawPut:
        """Store one response page (JSON bytes) and return its content-addressed reference."""
        body = gzip.compress(bytes(data), mtime=0)
        sha = contracts.bytes_sha256(body)
        parameters_hash = contracts.payload_hash(parameters) if parameters is not None else ""
        ref = contracts.RawRef(sha256=sha, key=self.key(scope, observed_at, sha), size=len(body), scope=scope,
                               operation=operation, observed_at=observed_at, parameters_hash=parameters_hash)
        metadata = {META_SHA: sha, "operation": operation, "observed-at": observed_at,
                    "scope-account": scope.account, "scope-region": scope.region,
                    "scope-source": scope.source, "parameters-hash": parameters_hash,
                    "producer": "remedigenius-ce"}
        try:
            status = self.backend.put_if_absent(ref.key, body, metadata)
        except BackendUnavailable as exc:
            if self.buffer is None:
                raise
            item = self.buffer.put(ref, body, metadata)
            return RawPut(ref=ref, durable=False, buffered=bool(item))
        if status == "exists":
            self._confirm_existing(ref)
        return RawPut(ref=ref, durable=True)

    def put_json(self, value: Any, **kwargs) -> RawPut:
        return self.put(contracts.canonical_json(contracts.jsonable(value)).encode("utf-8"), **kwargs)

    def _confirm_existing(self, ref: contracts.RawRef) -> None:
        head = self.backend.head(ref.key)
        if head is None:
            raise IntegrityError(f"{ref.key} was reported as existing but cannot be read")
        if head.size != ref.size:
            raise IntegrityError(f"{ref.key} has {head.size} bytes, expected {ref.size}")
        recorded = str(head.metadata.get(META_SHA, ""))
        if recorded and recorded != ref.sha256:
            raise IntegrityError(f"{ref.key} holds another object ({recorded})")
        if not recorded:
            body = self.backend.get(ref.key)
            if body is None or contracts.bytes_sha256(body) != ref.sha256:
                raise IntegrityError(f"{ref.key} does not match its content address")

    def get(self, ref: contracts.RawRef) -> bytes:
        body = self.backend.get(ref.key)
        if body is None:
            raise RawStoreError(f"raw object {ref.key} is missing")
        if contracts.bytes_sha256(body) != ref.sha256:
            raise IntegrityError(f"raw object {ref.key} does not match its SHA-256")
        return body

    def get_json(self, ref: contracts.RawRef) -> Any:
        return json.loads(gzip.decompress(self.get(ref)).decode("utf-8"))

    def verify(self, ref: contracts.RawRef) -> bool:
        head = self.backend.head(ref.key)
        if head is None or head.size != ref.size:
            return False
        recorded = str(head.metadata.get(META_SHA, ""))
        if recorded:
            return recorded == ref.sha256
        body = self.backend.get(ref.key)
        return body is not None and contracts.bytes_sha256(body) == ref.sha256

    def verify_many(self, refs: Iterable[contracts.RawRef]) -> list[dict]:
        problems = []
        for ref in refs:
            if not self.verify(ref):
                problems.append({"sha256": ref.sha256, "key": ref.key, "reason": "missing or does not match"})
        return problems

    def buffer_status(self) -> dict:
        return self.buffer.status() if self.buffer else {"objects": 0, "bytes": 0, "limit_bytes": 0}

    def flush(self) -> dict:
        """Retry buffered objects in order; stop at the first temporary failure so order and content stay intact."""
        if self.buffer is None:
            return {"uploaded": 0, "remaining": 0}
        uploaded = 0
        for item in self.buffer.items():
            body = item.body_path.read_bytes()
            if contracts.bytes_sha256(body) != item.ref.sha256:
                raise IntegrityError(f"buffered object {item.ref.sha256} is corrupt")
            try:
                status = self.backend.put_if_absent(item.ref.key, body, json.loads(item.meta_path.read_text(encoding="utf-8"))["metadata"])
            except BackendUnavailable:
                break
            if status == "exists":
                self._confirm_existing(item.ref)
            self.buffer.remove(item)
            uploaded += 1
        return {"uploaded": uploaded, "remaining": self.buffer.status()["objects"]}


def s3_backend(profile: contracts.StorageProfile, *, client=None, sse: str = "AES256", kms_key_id: str = "") -> S3Backend:
    if profile.kind != "aws":
        raise RawStoreError("the aws raw backend needs the aws storage profile")
    bucket = profile.warehouse[5:].split("/", 1)[0]
    if not bucket:
        raise RawStoreError("the aws storage profile has no bucket")
    return S3Backend(bucket, client=client, sse=sse, kms_key_id=kms_key_id)


def folder_backend(profile: contracts.StorageProfile) -> FolderBackend:
    if profile.kind != "local":
        raise RawStoreError("the folder raw backend needs the local storage profile")
    return FolderBackend(Path(profile.warehouse).parent)


def from_config(data: dict | None = None, profile: contracts.StorageProfile | None = None, *,
                home: Path | str | None = None, client=None, sse: str = "AES256", kms_key_id: str = "") -> RawStore:
    """Build the raw store for this installation, including its bounded outage buffer."""
    data = data or {}
    profile = profile or contracts.storage_profile(data, home)
    storage = data.get("storage") or {}
    limit = int(storage.get("buffer_limit_mb", 256)) * 1024 * 1024
    base = Path(home or os.environ.get("RGTRIAGE_HOME") or Path.home() / ".rgtriage")
    if profile.kind == "aws":
        backend = s3_backend(profile, client=client, sse=sse, kms_key_id=kms_key_id)
    else:
        backend = folder_backend(profile)
    return RawStore(backend, prefix=profile.raw_prefix, buffer=RawBuffer(base / "cache" / "raw-buffer", limit))