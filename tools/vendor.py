"""Pin, rebuild and verify the upstream copies inside our skills.

Every adapted skill keeps a verbatim copy of the upstream skill it came from in
`references/upstream/`, pinned to one commit in `skills.lock.json` with a sha256 per file.
That makes the skills reconstructable from git alone:

  python tools/vendor.py verify          # local copies match the lock (run in CI / before deploy)
  python tools/vendor.py fetch           # re-download every upstream at its pinned commit, rewrite copies
  python tools/vendor.py fetch --update  # same, and record new hashes (only after a deliberate re-vet)

Bumping a pin = change `commit` in skills.lock.json, `fetch --update`, re-run the vetting
(SkillSpector static + review), re-check our rules against upstream's changes, bump the skill version.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "skills.lock.json"


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def skill_dir(s):
    return ROOT / "profiles" / s["profile"] / "skills" / s["category"] / s["name"]


def upstream_files(base, include):
    out = []
    for inc in include:
        p = base / inc
        out += sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else ([p] if p.is_file() else [])
    return out


def fetch(lock, update):
    by_source = {}
    for s in lock["skills"]:
        by_source.setdefault(s["source"], []).append(s)
    changed = False
    for src, skills in by_source.items():
        meta = lock["sources"][src]
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            # only the paths we pin (big upstream repos have Windows-unsafe long paths elsewhere)
            subprocess.run(["git", "-C", tmp, "config", "core.longpaths", "true"], check=True)
            subprocess.run(["git", "-C", tmp, "sparse-checkout", "set", "--no-cone",
                            *[f"/{s['path']}/" for s in skills], "/" + meta.get("license_file", "LICENSE")], check=True)
            subprocess.run(["git", "-C", tmp, "fetch", "-q", "--depth", "1", meta["url"], meta["commit"]], check=True)
            subprocess.run(["git", "-C", tmp, "checkout", "-q", "FETCH_HEAD"], check=True)
            head = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            if head != meta["commit"]:
                sys.exit(f"{src}: got {head}, lock says {meta['commit']}")
            for s in skills:
                base = Path(tmp) / s["path"]
                dest = skill_dir(s) / "references" / "upstream"
                if dest.exists():
                    shutil.rmtree(dest)
                hashes = {}
                for f in upstream_files(base, s["include"]):
                    rel = f.relative_to(base).as_posix()
                    if Path(rel).name == "SKILL.md":  # never let Hermes load the raw upstream as a skill
                        rel = rel[: -len("SKILL.md")] + "UPSTREAM-SKILL.md"
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    data = f.read_bytes().replace(b"\r\n", b"\n")
                    (dest / rel).write_bytes(data)
                    hashes[rel] = hashlib.sha256(data).hexdigest()
                lic = Path(tmp) / meta.get("license_file", "LICENSE")
                if lic.exists():
                    (dest / "LICENSE").write_bytes(lic.read_bytes().replace(b"\r\n", b"\n"))
                if s.get("files") != hashes:
                    if not update:
                        sys.exit(f"{s['name']}: upstream content differs from the lock; re-vet, then fetch --update")
                    s["files"] = hashes
                    changed = True
                print(f"{s['name']}: {len(hashes)} files from {src}@{meta['commit'][:12]}")
    if changed:
        LOCK.write_bytes((json.dumps(lock, indent=2) + "\n").encode("utf-8"))  # LF on every OS
        print("lock updated")


def verify(lock):
    bad = 0
    for s in lock["skills"]:
        dest = skill_dir(s) / "references" / "upstream"
        for rel, h in s["files"].items():
            f = dest / rel
            if not f.exists() or sha256(f) != h:
                print(f"MISMATCH {s['name']}: {rel}")
                bad += 1
        extra = {f.relative_to(dest).as_posix() for f in dest.rglob("*") if f.is_file()} - set(s["files"]) - {"LICENSE"}
        for rel in sorted(extra):
            print(f"UNPINNED {s['name']}: {rel}")
            bad += 1
    print("verify: OK" if not bad else f"verify: {bad} problems")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "verify"])
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if a.cmd == "fetch":
        fetch(lock, a.update)
    else:
        sys.exit(1 if verify(lock) else 0)


if __name__ == "__main__":
    main()
