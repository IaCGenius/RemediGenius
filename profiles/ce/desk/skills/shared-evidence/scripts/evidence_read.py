"""Deterministic, bounded read-only inspection of staged CE evidence. No SDKs."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

LAYERS = ("raw", "normalized", "receipts", "knowledge", "derived")
MAX_BYTES = 2_000_000


def selected(root, name):
    if not name or "\\" in name or "\x00" in name:
        raise ValueError("Use a shared-root relative path")
    parts = PurePosixPath(name)
    if parts.is_absolute() or any(p == ".." or ":" in p for p in parts.parts):
        raise ValueError("Path is outside shared evidence")
    if root.is_symlink():
        raise ValueError("Symlinks are not shared evidence")
    base = root.resolve(strict=True)
    path = base
    for component in parts.parts:
        path = path / component
        if path.is_symlink():
            raise ValueError("Symlinks are not shared evidence")
    if not path.resolve(strict=True).is_relative_to(base):
        raise ValueError("Path is outside shared evidence")
    return path


def read(root, name):
    path = selected(root, name)
    if not path.is_file():
        raise ValueError("Select a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
            raise ValueError("File exceeds inspection limit or is not regular text")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or b"\x00" in data:
        raise ValueError("File exceeds inspection limit or is binary")
    text = data.decode("utf-8-sig")
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}, text


def inspect(root, command, path=None, offset=1, limit=100):
    root = Path(root)
    if command == "list":
        if path not in LAYERS:
            raise ValueError("Select a known evidence layer")
        try:
            directory = selected(root, path)
        except FileNotFoundError:
            return {"status": "NOT_RUN", "layer": path, "files": []}
        files = []
        for parent, directories, names in os.walk(directory, followlinks=False):
            if any((Path(parent) / n).is_symlink() for n in directories + names):
                raise ValueError("Symlinks are not shared evidence")
            for name in sorted(names):
                item = Path(parent) / name
                if not item.is_file():
                    continue
                files.append({"path": item.relative_to(root.resolve()).as_posix(), "bytes": item.stat().st_size})
                if len(files) >= 200:
                    return {"status": "OK", "layer": path, "files": files, "truncated": True}
        return {"status": "OK", "layer": path, "files": files, "truncated": False}
    if command == "catalog":
        path = "catalog.json"
    try:
        meta, text = read(root, path)
    except FileNotFoundError:
        return {"status": "NOT_RUN", "path": path, "reason": "No staged file; do not infer coverage"}
    if command == "catalog":
        data = json.loads(text)
        if not isinstance(data, (dict, list)):
            raise ValueError("Catalog must be a JSON object or array")
        if len(text) <= 24_000:
            return {"status": "OK", **meta, "catalog": data, "truncated": False}
    if offset < 1 or not 1 <= limit <= 200:
        raise ValueError("Invalid line range")
    lines = text.splitlines()
    excerpt = "\n".join(lines[offset - 1:offset - 1 + limit])
    return {"status": "OK", **meta, "offset": offset, "total_lines": len(lines),
            "text": excerpt[:24_000], "truncated": len(excerpt) > 24_000 or offset - 1 + limit < len(lines)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("/opt/data/shared"))
    ap.add_argument("command", choices=("catalog", "list", "show"))
    ap.add_argument("path", nargs="?")
    ap.add_argument("--offset", type=int, default=1)
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    try:
        output = inspect(args.root, args.command, args.path, args.offset, args.limit)
    except (OSError, ValueError, TypeError, UnicodeError):
        output = {"status": "ERROR", "reason": "Selected evidence is missing, invalid or exceeds inspection limits"}
    print(json.dumps(output, ensure_ascii=False))
    return 1 if output["status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
