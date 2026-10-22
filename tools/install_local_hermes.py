#!/usr/bin/env python3
"""Install RemediGenius Community Edition (RemediGenius-CE) into an existing local Hermes.

Creates (or updates) a Hermes profile that reuses the model settings of one of your
existing profiles, then adds the RemediGenius-CE SOUL, skills and the rg-triage plugin.

    python tools/install_triage.py --clone-from default
    hermes -p remedigenius chat

Run it with the Python that has boto3 + PyYAML (the plugin reuses that interpreter).
Only the profile folder and the rgtriage home folder are written. config.yaml is
merged key-by-key and the previous file is kept as a timestamped backup.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "profiles" / "remedigenius"
TOOLSETS = ["skills", "clarify", "file", "rg_triage"]
WATCH_SCRIPT = '''"""Hermes cron script: print new P1/P2 security findings; print nothing when there is nothing new."""
import os, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
env = dict(os.environ, RGTRIAGE_HOME={home!r}, PYTHONPATH={src!r} + os.pathsep + os.environ.get("PYTHONPATH", ""),
           PYTHONIOENCODING="utf-8")
proc = subprocess.run([{python!r}, "-m", "rgtriage", "watch", "--min-priority", "P2"], env=env,
                      capture_output=True, text=True, encoding="utf-8", errors="replace")
sys.stdout.write(proc.stdout)
if proc.returncode:
    sys.stdout.write("rgtriage watch failed: " + proc.stderr[-800:])
'''


def hermes_root() -> Path:
    if os.environ.get("HERMES_ROOT"):
        return Path(os.environ["HERMES_ROOT"])
    if os.name == "nt" and os.environ.get("LOCALAPPDATA") and (Path(os.environ["LOCALAPPDATA"]) / "hermes").exists():
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".hermes"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("+ " + " ".join(cmd))
    return subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace")


def merge_config(path: Path, model_from_template: bool) -> None:
    current = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    current = current or {}
    if path.exists():
        backup = path.with_name(f"config.yaml.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
        print(f"  backed up {path.name} -> {backup.name}")
    template = yaml.safe_load((SOURCE / "config.yaml").read_text(encoding="utf-8"))
    if model_from_template:
        current["model"] = template["model"]
    plugins = current.setdefault("plugins", {}) or {}
    current["plugins"] = plugins
    enabled = plugins.setdefault("enabled", []) or []
    for name in ("rg-triage", "rg-knowledge"):
        if name not in enabled:
            enabled.append(name)
    plugins["enabled"] = enabled
    pts = current.setdefault("platform_toolsets", {}) or {}
    for platform, toolsets in template["platform_toolsets"].items():
        pts[platform] = list(toolsets)
    current["platform_toolsets"] = pts
    agent = current.setdefault("agent", {}) or {}
    agent["max_turns"] = max(int(agent.get("max_turns") or 0), template["agent"]["max_turns"])
    current["agent"] = agent
    path.write_text(yaml.safe_dump(current, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="remedigenius", help="Hermes profile name to create/update")
    ap.add_argument("--clone-from", default="default", help="existing profile whose model/provider settings to reuse")
    ap.add_argument("--hermes", default=shutil.which("hermes") or "hermes")
    ap.add_argument("--rgtriage-home", default=os.environ.get("RGTRIAGE_HOME") or str(Path.home() / ".rgtriage"))
    ap.add_argument("--aws-profile", default=None, help="AWS CLI profile for the initial triage.yaml")
    ap.add_argument("--region", default=None)
    args = ap.parse_args()

    try:
        import boto3  # noqa: F401
    except ImportError:
        sys.exit(f"{sys.executable} has no boto3. Run: {sys.executable} -m pip install boto3 PyYAML")

    root = hermes_root()
    profile_home = root / "profiles" / args.profile
    created = False
    if not profile_home.exists():
        result = run([args.hermes, "profile", "create", args.profile, "--clone-from", args.clone_from, "--no-alias",
                      "--description", "AWS security triage desk: prioritized findings, read-only investigation, IaC fix proposals."])
        if result.returncode != 0 or not profile_home.exists():
            sys.exit(f"profile create failed:\n{result.stdout}\n{result.stderr}")
        created = True
    print(f"Profile folder: {profile_home}")

    shutil.copy2(SOURCE / "SOUL.md", profile_home / "SOUL.md")
    for skill in (SOURCE / "skills").iterdir():
        dest = profile_home / "skills" / skill.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill, dest)
    plugin_dest = profile_home / "plugins" / "rg-triage"
    if plugin_dest.exists():
        shutil.rmtree(plugin_dest)
    shutil.copytree(SOURCE / "plugins" / "rg-triage", plugin_dest, ignore=shutil.ignore_patterns("__pycache__", "local.json"))
    home = Path(args.rgtriage_home).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    (home / "proposals").mkdir(exist_ok=True)
    (plugin_dest / "local.json").write_text(json.dumps({"python": sys.executable, "src": str(REPO), "home": str(home)}, indent=1),
                                            encoding="utf-8")
    merge_config(profile_home / "config.yaml", model_from_template=False)
    scripts = profile_home / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "rgtriage-watch.py").write_text(WATCH_SCRIPT.format(home=str(home), src=str(REPO), python=sys.executable),
                                               encoding="utf-8")
    tab = root / "plugins" / "rg-knowledge"
    if tab.exists():
        shutil.rmtree(tab)
    shutil.copytree(SOURCE / "dashboard-plugins" / "rg-knowledge", tab, ignore=shutil.ignore_patterns("__pycache__", "local.json"))
    (tab / "local.json").write_text(json.dumps({"python": sys.executable, "src": str(REPO), "home": str(home),
                                                "proposals": str(home / "proposals"), "inbox": str(home / "knowledge-inbox"),
                                                "files": str(home / "knowledge-files"), "profile": args.profile}, indent=1),
                                    encoding="utf-8")
    for folder in ("proposals/knowledge", "knowledge-inbox", "knowledge-files"):
        (home / folder).mkdir(parents=True, exist_ok=True)
    print("  installed SOUL.md, skills rg-*, plugin rg-triage, scripts/rgtriage-watch.py, dashboard Knowledge tab")

    env = dict(os.environ, RGTRIAGE_HOME=str(home), PYTHONPATH=str(REPO))
    # The dashboard serves user plugins only when they are enabled at its launch scope too.
    enabled = run([args.hermes, "-p", "default", "plugins", "enable", "rg-knowledge"])
    print("  enabled the Knowledge tab for the dashboard" if enabled.returncode == 0 else
          f"  could not enable rg-knowledge at the default scope: {enabled.stdout[-200:]} {enabled.stderr[-200:]}")
    seeded = subprocess.run([sys.executable, "-m", "rgtriage", "knowledge-edit", "seed"], env=env, text=True, capture_output=True)
    print(f"  knowledge bundle: {home / 'knowledge'}" if seeded.returncode == 0 else f"  knowledge seed failed: {seeded.stderr[-300:]}")
    if not (home / "triage.yaml").exists():
        cmd = [sys.executable, "-m", "rgtriage", "init"]
        if args.aws_profile:
            cmd += ["--profile", args.aws_profile]
        if args.region:
            cmd += ["--region", args.region]
        result = subprocess.run(cmd, env=env, text=True, capture_output=True)
        print(result.stdout.strip() or result.stderr.strip())
    else:
        print(f"  keeping existing {home / 'triage.yaml'}")

    print(f"""
Done{' (new profile)' if created else ''}.
  1. Check access:       {sys.executable} -m rgtriage doctor     (set RGTRIAGE_HOME={home})
  2. Start the desk:     hermes -p {args.profile} chat   -> it opens with your attention board
  3. Optional alerts:    hermes -p {args.profile} cron create "every 2h" --name security-watch --no-agent --script rgtriage-watch.py --deliver local
""")


if __name__ == "__main__":
    main()
