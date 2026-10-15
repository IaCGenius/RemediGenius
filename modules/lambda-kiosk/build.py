#!/usr/bin/env python3
"""Build the kiosk's zips, deterministically (sorted entries, fixed timestamps), so the same inputs
always give the same hash and a saved Terraform plan never drifts.

  python build.py            -> build/runtime-layer.zip, build/test-layer.zip, build/gate.zip, build/sandbox.zip

Layers are installed from hash-pinned locks for Lambda's platform (manylinux x86_64, Python 3.13),
whatever OS this runs on. Needs `uv`. tf.sh runs this before every kiosk plan.
"""
import io
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
PY, PLATFORM = "3.13", "x86_64-manylinux_2_28"


def add_tree(files, root, prefix):
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            files[f"{prefix}{p.relative_to(root).as_posix()}"] = p.read_bytes()


def write_zip(path, files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[name])
    data = buf.getvalue()
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
    print(f"{path.name}: {len(files)} files, {len(data) // 1024} KiB")


def layer(lock, extra=None):
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "python"
        subprocess.run(["uv", "pip", "install", "-q", "--target", str(target), "--python-version", PY,
                        "--python-platform", PLATFORM, "--only-binary", ":all:", "--require-hashes", "--no-deps",
                        "--no-compile", "-r", str(HERE / "layers" / lock)], check=True)
        files = {}
        add_tree(files, target, "python/")
        # installer metadata that differs per machine (absolute paths, installer name) is dropped
        files = {k: v for k, v in files.items() if not k.endswith(("/INSTALLER", "/REQUESTED", "/direct_url.json"))}
        if extra:
            add_tree(files, extra, f"python/{extra.name}/")
        return files


def main():
    BUILD.mkdir(exist_ok=True)
    write_zip(BUILD / "runtime-layer.zip", layer("runtime.lock", HERE / "src" / "runtime" / "kiosk_runtime"))
    write_zip(BUILD / "test-layer.zip", layer("test.lock"))
    for fn in ("gate", "sandbox"):
        files = {}
        add_tree(files, HERE / "src" / fn, "")
        write_zip(BUILD / f"{fn}.zip", files)


if __name__ == "__main__":
    if not shutil.which("uv"):
        sys.exit("build.py needs uv (https://docs.astral.sh/uv/)")
    main()
