"""Package RemediGenius Community Edition (RemediGenius-CE).

  python tools/package_release.py --spot dist/spot.zip          # Spot host archive only (for Terraform source_zip)
  python tools/package_release.py --release 0.3.0               # dist/v0.3.0: spot zip, source zip, wheel, SHA256SUMS, RELEASE.json

Archives use fixed timestamps so identical source gives identical bytes. Nothing is uploaded and
no credentials are read.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPOT_PARTS = ["rgtriage", "profiles/remedigenius", "deploy/aws-single/host.py", "deploy/aws-single/member-read-role.yaml",
              "LICENSE", "NOTICE"]
SKIP = {"__pycache__", ".terraform", ".pytest_cache"}


def files(parts):
    for part in parts:
        path = ROOT / part
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for p in candidates:
            if not any(s in p.parts for s in SKIP) and not p.name.endswith((".pyc", "local.json")):
                yield p


def write_zip(output: Path, paths, prefix: str = "") -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            entry = zipfile.ZipInfo(prefix + path.relative_to(ROOT).as_posix(), (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, path.read_bytes())
    return hashlib.sha256(output.read_bytes()).hexdigest()


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [ROOT / p for p in out if (ROOT / p).is_file()]


def release(version: str) -> dict:
    out = ROOT / "dist" / f"v{version}"
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    digests = {
        f"remedigenius-ce-{version}-spot.zip": write_zip(out / f"remedigenius-ce-{version}-spot.zip", files(SPOT_PARTS)),
        f"remedigenius-ce-{version}-source.zip": write_zip(out / f"remedigenius-ce-{version}-source.zip", tracked_files(),
                                                            prefix=f"remedigenius-ce-{version}/"),
    }
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(out), str(ROOT)], check=True)
    for wheel in out.glob(f"remedigenius_community-{version}-*.whl"):
        digests[wheel.name] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text("".join(f"{d}  {n}\n" for n, d in sorted(digests.items())))
    manifest = {"product": "RemediGenius Community Edition (RemediGenius-CE)", "version": version, "source_commit": commit,
                "hermes_image": "nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b",
                "validated_model": "deepseek-v4.1-flash", "validation": "docs/RELEASE-VALIDATION.md", "files": digests}
    (out / "RELEASE.json").write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--spot", type=Path, help="write only the Spot host archive to this path")
    group.add_argument("--release", metavar="VERSION")
    args = parser.parse_args()
    if args.spot:
        print(json.dumps({"archive": str(args.spot), "sha256": write_zip(args.spot, files(SPOT_PARTS))}))
    else:
        print(json.dumps(release(args.release), indent=1))
