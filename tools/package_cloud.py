"""Build a cloud-first CE sharing bundle from committed source and pinned archives.

No AWS access, model calls, secret discovery, Docker execution or publication.
Packaging verifies Docker archive identities; it does not certify live acceptance.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    from .package_preview import inspect_source, sha
except ImportError:
    from package_preview import inspect_source, sha

ROOT = Path(__file__).resolve().parents[1]


def inspect_image(path, expected):
    """Check the actual Docker-save config digest without extracting image layers."""
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", expected):
        raise ValueError("Use an exact sha256 Docker image ID")
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate Docker archive member")
        for member in members:
            part = PurePosixPath(member.name)
            if part.is_absolute() or ".." in part.parts or "\\" in member.name:
                raise ValueError("Unsafe Docker archive path")
        def read_json(name, limit):
            member = archive.getmember(name)
            if not member.isfile() or member.size > limit:
                raise ValueError("Invalid Docker archive metadata")
            stream = archive.extractfile(member)
            raw = stream.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("Oversized Docker metadata")
            return raw, json.loads(raw)
        _, manifest = read_json("manifest.json", 1_048_576)
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise ValueError("Each archive must contain exactly one Docker image")
        raw, config = read_json(manifest[0]["Config"], 2_097_152)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Docker archive does not match the supplied image ID")
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError("Cloud runtime requires Linux amd64 images")
        for line in config.get("config", {}).get("Env", []):
            key, _, value = line.partition("=")
            if value and (key.endswith(("API_KEY", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "SESSION_TOKEN")) or key in ("RGCE_AUTH_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")):
                raise ValueError("Credential-like environment value in Docker image configuration")
        return {"image_id": expected, "archive_sha256": sha(path), "platform": "linux/amd64"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--console-archive", type=Path, required=True)
    parser.add_argument("--hermes-archive", type=Path, required=True)
    parser.add_argument("--console-image-id", required=True)
    parser.add_argument("--hermes-image-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/cloud-preview")
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise SystemExit("Commit the reviewed source before packaging")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    version = re.search(r'__version__ = "([0-9A-Za-z.]+)"', (ROOT / "rgce/__init__.py").read_text()).group(1)
    console = inspect_image(args.console_archive, args.console_image_id)
    hermes = inspect_image(args.hermes_archive, args.hermes_image_id)
    parent = args.output_dir.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle = parent / f"remedigenius-ce-cloud-{version}-{stamp}-{uuid.uuid4().hex[:8]}"
    bundle.mkdir(exist_ok=False)
    source = bundle / "source.zip"
    subprocess.run(["git", "archive", "--format=zip", "--output=" + str(source), commit], cwd=ROOT, check=True)
    pattern_file = ROOT / ".rgce/private-patterns.json"
    private_patterns = json.loads(pattern_file.read_text()) if pattern_file.exists() else []
    count = inspect_source(source, private_patterns)
    shutil.copyfile(args.console_archive, bundle / "console.tar.gz")
    shutil.copyfile(args.hermes_archive, bundle / "hermes.tar.gz")
    if sha(bundle / "console.tar.gz") != console["archive_sha256"] or sha(bundle / "hermes.tar.gz") != hermes["archive_sha256"]:
        raise ValueError("An image archive changed while packaging")
    with zipfile.ZipFile(source) as snapshot:
        for source_name, target in [("LICENSE", "LICENSE"), ("NOTICE", "NOTICE"), ("docs/FEEDBACK.md", "FEEDBACK.md")]:
            (bundle / target).write_bytes(snapshot.read(source_name))
        start = snapshot.read("docs/CLOUD-START-HERE.md").decode("utf-8").replace("__VERSION__", version)
    (bundle / "START-HERE.md").write_text(start, encoding="utf-8")
    release = {
        "version": version, "channel": "cloud-private-preview", "source_commit": commit,
        "source_members_checked": count, "created_at": datetime.now(timezone.utc).isoformat(),
        "console": {**console, "archive": "console.tar.gz"},
        "hermes": {**hermes, "archive": "hermes.tar.gz"},
        "acceptance_status": "Packaging verifies identities only; it does not assert live acceptance or image-to-source equivalence.",
        "files": {path.name: sha(path) for path in sorted(bundle.iterdir()) if path.is_file()},
    }
    (bundle / "RELEASE.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    members = sorted(path for path in bundle.iterdir() if path.is_file())
    (bundle / "SHA256SUMS").write_text("".join(sha(path) + "  " + path.name + "\n" for path in members), encoding="utf-8")
    output = parent / (bundle.name + ".zip")
    with zipfile.ZipFile(output, "x", zipfile.ZIP_STORED) as archive:
        for path in sorted(bundle.iterdir()):
            archive.write(path, bundle.name + "/" + path.name)
    digest = sha(output)
    output.with_suffix(".zip.sha256").write_text(digest + "  " + output.name + "\n", encoding="utf-8")
    print(json.dumps({"bundle": str(output), "sha256": digest, "source_commit": commit, "source_members_checked": count}))


if __name__ == "__main__":
    main()
