"""Deterministic checks for a proposed change, run on a scratch copy of the repository with no credentials.

`validate_overlay(tree, changes)` writes the proposed files over a copy of the repository and runs, per kind of file:

  Terraform (*.tf)       terraform init (no backend) + validate + fmt -check, tflint (core rules) on the changed files
  CloudFormation         cfn-lint on the changed templates (YAML or JSON that declare AWS resources)
  other YAML / JSON      a parse check

Each result is {check, result, detail} with result pass | fail | warn | skipped. A missing tool is `skipped` and says so: the change
is then **not** validated by that tool, and the PR says it. `fail` blocks publishing; `warn` (formatting, linter advice) does not.
Nothing here plans or applies, and AWS_*, GITHUB_* and token variables are removed from the environment of every tool.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

TIMEOUT = 600


def find_tool(name: str) -> str | None:
    """A tool on PATH, or next to this interpreter (pip puts cfn-lint in the venv's bin, which a systemd service does not have on PATH)."""
    import sys
    return shutil.which(name) or shutil.which(name, path=str(Path(sys.executable).parent))
SECRET_ENV = re.compile(r"^(AWS_|GITHUB_|GH_|RGGITHUB_|MODEL_API_KEY|.*(TOKEN|SECRET|PASSWORD|PRIVATE_KEY)).*", re.I)


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.match(k)}
    env.update(TF_IN_AUTOMATION="1", TF_INPUT="0", CHECKPOINT_DISABLE="1", NO_COLOR="1")
    return env


def _run(cmd: list[str], cwd: Path, env: dict) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {TIMEOUT}s"
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _row(check: str, result: str, detail: str = "") -> dict:
    return {"check": check, "result": result, "detail": detail[-600:]}


def is_cloudformation(path: str, text: str) -> bool:
    return path.lower().endswith((".yaml", ".yml", ".json", ".template")) and ("AWSTemplateFormatVersion" in text or
                                                                              (re.search(r"^Resources\s*:", text, re.M) and "AWS::" in text) or
                                                                              ('"Resources"' in text and "AWS::" in text))


def validate_overlay(tree: Path, changes: dict[str, bytes], which=find_tool) -> list[dict]:
    env, results = clean_env(), []
    changed = sorted(changes)
    for rel, data in changes.items():
        target = (tree / rel).resolve()
        if tree.resolve() not in target.parents:
            results.append(_row(f"path {rel}", "fail", "outside the repository"))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    tf = [p for p in changed if p.endswith(".tf")]
    if tf:
        terraform, tflint = which("terraform"), which("tflint")
        for folder in sorted({str(Path(p).parent).replace("\\", "/") for p in tf}):
            module, label = tree / folder, f"terraform {folder or '.'}"
            if not terraform:
                results.append(_row(label, "skipped", "terraform is not installed: this change was NOT validated by Terraform"))
                continue
            rc, out = _run([terraform, "init", "-backend=false", "-input=false", "-no-color"], module, env)
            if rc != 0:
                results.append(_row(f"{label} init", "fail", out))
                continue
            rc, out = _run([terraform, "validate", "-no-color"], module, env)
            results.append(_row(f"{label} validate", "pass" if rc == 0 else "fail", "" if rc == 0 else out))
            files = [Path(p).name for p in tf if str(Path(p).parent).replace("\\", "/") == folder]
            rc, out = _run([terraform, "fmt", "-check", "-diff", "-no-color", *files], module, env)
            results.append(_row(f"{label} fmt", "pass" if rc == 0 else "warn", "" if rc == 0 else "formatting differs from `terraform fmt`\n" + out))
            if not tflint:
                results.append(_row(f"{label} tflint", "skipped", "tflint is not installed"))
            else:
                args = [tflint, "--no-color", "--format=compact"] + [f"--filter={f}" for f in files]
                rc, out = _run(args, module, env)
                results.append(_row(f"{label} tflint", "pass" if rc == 0 else "warn", "" if rc == 0 else out))

    cfn = [p for p in changed if is_cloudformation(p, changes[p].decode("utf-8", "replace"))]
    for rel in cfn:
        linter = which("cfn-lint")
        if not linter:
            results.append(_row(f"cfn-lint {rel}", "skipped", "cfn-lint is not installed: this template was NOT linted"))
            continue
        rc, out = _run([linter, "--format", "parseable", rel], tree, env)
        results.append(_row(f"cfn-lint {rel}", "pass" if rc == 0 else ("fail" if rc & 2 else "warn"), "" if rc == 0 else out))

    for rel in changed:
        if rel in cfn or rel.endswith(".tf"):
            continue
        text = changes[rel].decode("utf-8", "replace")
        if rel.lower().endswith(".json"):
            try:
                json.loads(text)
                results.append(_row(f"json {rel}", "pass"))
            except ValueError as exc:
                results.append(_row(f"json {rel}", "fail", str(exc)))
        elif rel.lower().endswith((".yaml", ".yml")):
            try:
                import yaml
                list(yaml.safe_load_all(text))
                results.append(_row(f"yaml {rel}", "pass"))
            except Exception as exc:
                results.append(_row(f"yaml {rel}", "fail", str(exc)[:300]))
    if not results:
        results.append(_row("validation", "skipped", "no Terraform, CloudFormation, JSON or YAML file in this change: not validated"))
    return results


def available(which=find_tool) -> dict:
    """Which deterministic tools this desk can run (reported by `rgtriage github status` and doctor)."""
    return {name: bool(which(name)) for name in ("terraform", "tflint", "cfn-lint")}
