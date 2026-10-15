"""Hydrate verified S3 records into Hermes' read-only shared mount."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

import boto3


def hydrate(bucket, prefix, destination):
    s3 = boto3.client("s3")
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)

    def fetch(path, limit):
        response = s3.get_object(Bucket=bucket, Key=f"{prefix.strip('/')}/{path}")
        if response["ContentLength"] > limit:
            raise ValueError("Record exceeds sketch size limit")
        return response["Body"].read(limit + 1)

    body = fetch("catalog.json", 1024 * 1024)
    catalog = json.loads(body)
    if catalog.get("schema_version") != "rgce-source-catalog/1" or len(catalog["files"]) > 30:
        raise ValueError("Unsupported catalogue")
    for item in catalog["files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative) or ":" in str(relative):
            raise ValueError("Unsafe record path")
        if relative.parts[0] not in ("raw", "normalized", "receipts"):
            raise ValueError("Unexpected layer")
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root):
            raise ValueError("Path escapes shared directory")
        data = fetch(str(relative), 8 * 1024 * 1024)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Record integrity mismatch")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".incoming")
        temp.write_bytes(data)
        os.replace(temp, path)
    temp = root / "catalog.incoming"
    temp.write_bytes(body)
    os.replace(temp, root / "catalog.json")
    print(json.dumps({"run_id": catalog["run_id"], "verified_files": len(catalog["files"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["hydrate"])
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    hydrate(args.bucket, args.prefix, args.destination)
