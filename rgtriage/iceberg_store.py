"""Iceberg storage profiles and table maintenance (roadmap CE-12).

Two profiles, both authoritative for their installation:

* ``aws`` — S3 warehouse in the deployment bucket, AWS Glue catalog, the desk's own identity;
* ``local`` — a SQL catalog file and filesystem warehouse inside the workstation durable folder.

PyIceberg runs in the desk process. There is no Spark, no always-on service and no Athena requirement. History is
read in-process with Arrow; Athena is optional for operators.

Maintenance is deliberately conservative: compaction, snapshot expiry that keeps a recent window for batch
reconciliation and time travel, and orphan-data cleanup that only removes files no remaining snapshot references.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import contracts, schemas

DEFAULT_NAMESPACE = "remedigenius"


@dataclass(frozen=True, slots=True)
class MaintenanceSettings:
    target_file_size_mb: int = 128
    snapshot_retention_days: int = 14
    min_snapshots: int = 5
    orphan_retention_hours: int = 72
    interval_hours: int = 24
    max_compact_rows: int = 200_000

    @classmethod
    def from_dict(cls, data: dict | None) -> "MaintenanceSettings":
        data = data or {}
        return cls(target_file_size_mb=int(data.get("target_file_size_mb", 128)),
                   snapshot_retention_days=int(data.get("snapshot_retention_days", 14)),
                   min_snapshots=max(1, int(data.get("min_snapshots", 5))),
                   orphan_retention_hours=max(0, int(data.get("orphan_retention_hours", 72))),
                   interval_hours=max(1, int(data.get("interval_hours", 24))),
                   max_compact_rows=max(1, int(data.get("max_compact_rows", 200_000))))

    def as_dict(self) -> dict:
        return {"target_file_size_mb": self.target_file_size_mb,
                "snapshot_retention_days": self.snapshot_retention_days,
                "min_snapshots": self.min_snapshots,
                "orphan_retention_hours": self.orphan_retention_hours,
                "interval_hours": self.interval_hours, "max_compact_rows": self.max_compact_rows}


class IcebergUnavailable(RuntimeError):
    """The catalog or warehouse cannot be reached or does not belong to this installation."""


def _sqlite_uri(path: str) -> str:
    if path.startswith("sqlite:"):
        return path
    return "sqlite:///" + Path(path).as_posix()


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").split("://", 1)[-1].lstrip("/")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class IcebergStore:
    def __init__(self, catalog, profile: contracts.StorageProfile, *, namespace: str | None = None,
                 region: str = "", maintenance: MaintenanceSettings | None = None):
        self.catalog = catalog
        self.profile = profile
        self.namespace = namespace or profile.namespace or DEFAULT_NAMESPACE
        self.region = region
        self.maintenance_settings = maintenance or MaintenanceSettings()

    @classmethod
    def open(cls, profile: contracts.StorageProfile, *, region: str = "",
             maintenance: MaintenanceSettings | dict | None = None) -> "IcebergStore":
        from pyiceberg.catalog import load_catalog

        if isinstance(maintenance, dict) or maintenance is None:
            maintenance = MaintenanceSettings.from_dict(maintenance)
        properties: dict[str, str]
        if profile.kind == "aws":
            properties = {
                "type": "glue", "warehouse": profile.warehouse, "glue.region": region or "us-east-1",
                "s3.region": region or "us-east-1", "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            }
        elif profile.kind == "local":
            properties = {
                "type": "sql", "uri": _sqlite_uri(profile.catalog_uri), "warehouse": profile.warehouse,
                "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            }
        else:
            raise IcebergUnavailable(f"unknown storage profile {profile.kind!r}")
        try:
            catalog = load_catalog("ce", **properties)
        except Exception as exc:  # configuration, credentials, sqlalchemy or network
            raise IcebergUnavailable(f"cannot open the {profile.kind} Iceberg catalog: {exc}") from exc
        return cls(catalog, profile, namespace=profile.namespace, region=region, maintenance=maintenance)

    @classmethod
    def from_config(cls, data: dict | None = None, *, region: str = "", home: Path | str | None = None) -> "IcebergStore":
        data = data or {}
        profile = contracts.storage_profile(data, home)
        return cls.open(profile, region=region, maintenance=(data.get("storage") or {}).get("maintenance"))

    # ---------------------------------------------------------------- setup
    def ensure_tables(self) -> dict:
        try:
            return schemas.create_tables(self.catalog, self.namespace)
        except schemas.SchemaMismatch as exc:
            raise IcebergUnavailable(f"storage does not match this release: {exc}") from exc

    def table(self, name: str):
        if name not in schemas.TABLES:
            raise KeyError(f"unknown CE table {name!r}")
        try:
            return self.catalog.load_table(f"{self.namespace}.{name}")
        except Exception as exc:
            raise IcebergUnavailable(f"cannot load {self.namespace}.{name}: {exc}") from exc

    # ---------------------------------------------------------------- writes and reads
    def append_rows(self, name: str, rows: list[dict], *, batch_id: str = "", content_hash: str = "") -> str:
        """Append rows with the batch ID in the snapshot summary; a committed batch is not appended twice."""
        if not rows:
            return "empty"
        if batch_id and self.batch_in_history(name, batch_id):
            return "already-committed"
        import pyarrow as pa

        table = self.table(name)
        arrow = pa.Table.from_pylist(rows, schema=schemas.pyarrow_schema(name, table.schema()))
        properties = {}
        if batch_id:
            properties["ce.batch_id"] = batch_id
        if content_hash:
            properties["ce.content_hash"] = content_hash
        table.append(arrow, snapshot_properties=properties)
        return "appended"

    def append_many(self, rows_by_table: dict[str, list[dict]], *, batch_id: str = "",
                    content_hash: str = "") -> dict:
        return {name: self.append_rows(name, rows, batch_id=batch_id, content_hash=content_hash)
                for name, rows in rows_by_table.items() if rows}

    def scan_rows(self, name: str, *, limit: int | None = None, snapshot_id: int | None = None) -> list[dict]:
        table = self.table(name)
        scan = table.scan(snapshot_id=snapshot_id, limit=limit)
        return scan.to_arrow().to_pylist()

    def snapshots(self, name: str) -> list:
        return self.table(name).snapshots()

    def batch_in_history(self, name: str, batch_id: str) -> bool:
        return any((snapshot.summary or {}).get("ce.batch_id") == batch_id for snapshot in self.snapshots(name))

    def last_batch(self, name: str) -> str:
        snapshots = self.snapshots(name)
        return str((snapshots[-1].summary or {}).get("ce.batch_id", "")) if snapshots else ""

    # ---------------------------------------------------------------- maintenance
    def maintenance(self, *, dry_run: bool = False, now: datetime | None = None) -> dict:
        """Compact small files, expire old snapshots and remove unreferenced data files."""
        now = now or datetime.now(timezone.utc)
        results = {}
        for name in schemas.TABLES:
            try:
                results[name] = self._maintain_table(self.table(name), name, now, dry_run)
            except Exception as exc:  # one table must not stop the others; the operator sees the failure
                results[name] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        return {"at": contracts.format_time(now), "dry_run": dry_run, "settings": self.maintenance_settings.as_dict(),
                "tables": results}

    def _maintain_table(self, table, name: str, now: datetime, dry_run: bool) -> dict:
        result = {"compacted_files": 0, "expired_snapshots": 0, "orphan_files": 0}
        settings = self.maintenance_settings
        files = table.inspect.data_files().to_pylist()
        small = [item for item in files if int(item.get("file_size_in_bytes") or 0) < settings.target_file_size_mb * 1024 * 1024]
        total_rows = sum(int(item.get("record_count") or 0) for item in files)
        if len(files) > 1 and len(small) > 1 and total_rows <= settings.max_compact_rows:
            if not dry_run:
                from pyiceberg.expressions import AlwaysTrue

                data = table.scan().to_arrow()
                table.overwrite(data, overwrite_filter=AlwaysTrue(),
                                snapshot_properties={"ce.maintenance": "compact"})
                table.refresh()
            result["compacted_files"] = len(files)
        elif len(files) > 1:
            result["skipped_compaction"] = "too many rows" if total_rows > settings.max_compact_rows else "files are large enough"

        snapshots = sorted(table.snapshots(), key=lambda item: item.timestamp_ms)
        if len(snapshots) > settings.min_snapshots:
            keep_from = snapshots[-settings.min_snapshots]
            keep_at = datetime.fromtimestamp(keep_from.timestamp_ms / 1000, tz=timezone.utc)
            cutoff = min(now - timedelta(days=settings.snapshot_retention_days), keep_at)
            expired = [item for item in snapshots if datetime.fromtimestamp(item.timestamp_ms / 1000, tz=timezone.utc) < cutoff]
            if expired and not dry_run:
                table.maintenance.expire_snapshots().older_than(cutoff).commit()
                table.refresh()
            result["expired_snapshots"] = len(expired)

        referenced = self._referenced_files(table)
        cutoff_orphan = now - timedelta(hours=settings.orphan_retention_hours)
        try:
            fs, root = self._filesystem(table)
            from pyarrow.fs import FileSelector, FileType
        except Exception as exc:
            result["orphan_cleanup"] = f"unavailable: {type(exc).__name__}: {exc}"[:200]
            return result
        removed = 0
        try:
            infos = fs.get_file_info(FileSelector(f"{root.rstrip('/')}/data", recursive=True))
        except FileNotFoundError:
            result["orphan_files"] = 0
            return result
        for info in infos:
            if info.type != FileType.File or not info.path.endswith(".parquet"):
                continue
            if _norm(info.path) in referenced:
                continue
            if _utc(info.mtime) > cutoff_orphan:
                continue
            if not dry_run:
                fs.delete_file(info.path)
            removed += 1
        result["orphan_files"] = removed
        return result

    def _referenced_files(self, table) -> set[str]:
        referenced = set()
        for snapshot in table.snapshots():
            try:
                for task in table.scan(snapshot_id=snapshot.snapshot_id).plan_files():
                    referenced.add(_norm(task.file.file_path))
            except Exception:
                continue  # a broken snapshot cannot authorize deleting data
        return referenced

    @staticmethod
    def _filesystem(table):
        from pyarrow.fs import FileSystem, LocalFileSystem

        location = str(table.location())
        if location.startswith("s3://") or location.startswith("s3a://"):
            fs, path = FileSystem.from_uri(location)
            return fs, path
        return LocalFileSystem(), str(Path(location))

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        tables = {}
        for name in schemas.TABLES:
            try:
                table = self.table(name)
                tables[name] = {"snapshots": len(table.snapshots()),
                                "data_files": len(table.inspect.data_files().to_pylist())}
            except Exception as exc:
                tables[name] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        return {"profile": self.profile.kind, "namespace": self.namespace, "region": self.region,
                "warehouse": self.profile.warehouse, "tables": tables}


def from_env(data: dict | None = None, *, region: str | None = None) -> IcebergStore:
    """Convenience for the desk service: region from the deployment environment when not configured."""
    return IcebergStore.from_config(data, region=region or os.environ.get("AWS_REGION", ""))