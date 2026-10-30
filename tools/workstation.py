#!/usr/bin/env python3
"""RemediGenius Community Edition (RemediGenius-CE) on a Docker workstation.

    python tools/workstation.py start --aws-profile default          # build, restore, start, print the dashboard URL
    python tools/workstation.py run   --aws-profile default          # start, then keep AWS credentials fresh (Ctrl+C to stop)
    python tools/workstation.py login | status | stop | refresh

Two containers:
  remedigenius-ce-desk    rgtriage API on a Unix socket; the ONLY place AWS credentials exist (temporary, 1-12 h)
  remedigenius-ce-hermes  pinned Hermes image with the `remedigenius` profile; no AWS credentials
Durable storage is a folder on this machine (default ~/RemediGenius-CE): the desk checkpoints the Hermes
home and the desk state there every 2 minutes and after scans/decisions; empty volumes are restored from it.
Model key: set REMEDIGENIUS_MODEL_KEY in the environment (never pass it on the command line or in chat).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

REPO = Path(__file__).resolve().parents[1]
HERMES_IMAGE = "nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b"
DESK_IMAGE = "remedigenius-ce-desk:local"
DESK, HERMES = "remedigenius-ce-desk", "remedigenius-ce-hermes"
VOLUMES = {"hermes": "remedigenius-ce-hermes", "desk": "remedigenius-ce-state", "socket": "remedigenius-ce-socket",
           "creds": "remedigenius-ce-creds"}
PROFILE = "remedigenius"
SOCKET = "/run/rgtriage/rgtriage.sock"


def docker(*args, check=True, capture=False, input=None):
    return subprocess.run(["docker", *args], check=check, text=True, encoding="utf-8", errors="replace", input=input,
                          stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)


def exists(kind, name):
    return docker(kind, "inspect", name, check=False, capture=True).returncode == 0


def host_path(path: Path) -> str:
    return path.resolve().as_posix()


# ---------------------------------------------------------------- credentials

def mint_credentials(profile: str | None, region: str, role_arn: str | None) -> tuple[dict, str]:
    """Credentials for the desk container: an assumed read-only role (recommended) or the profile's own credentials."""
    session = boto3.Session(profile_name=profile or None, region_name=region)
    if role_arn:
        c = session.client("sts").assume_role(RoleArn=role_arn, RoleSessionName="remedigenius-ce-workstation",
                                              DurationSeconds=3600)["Credentials"]
    else:
        # GetSessionToken credentials cannot call IAM without MFA, so the profile's credentials are passed as they
        # are. They reach only the desk container, never Hermes; a read-only role is still the recommended setup.
        frozen = session.get_credentials().get_frozen_credentials()
        expiry = getattr(session.get_credentials(), "_expiry_time", None)
        c = {"AccessKeyId": frozen.access_key, "SecretAccessKey": frozen.secret_key, "SessionToken": frozen.token,
             "Expiration": expiry or ("unknown" if frozen.token else "never (long-term key; prefer --read-role-arn)")}
    text = f"[default]\naws_access_key_id = {c['AccessKeyId']}\naws_secret_access_key = {c['SecretAccessKey']}\n"
    if c.get("SessionToken"):
        text += f"aws_session_token = {c['SessionToken']}\n"
    return {"credentials": text, "config": f"[default]\nregion = {region}\n"}, str(c["Expiration"])


def push_credentials(args) -> str:
    files, expires = mint_credentials(args.aws_profile, args.region, args.read_role_arn)
    for name, body in files.items():
        docker("run", "--rm", "-i", "--user", "10000:10000", "-v", f"{VOLUMES['creds']}:/creds", "--entrypoint", "sh",
               DESK_IMAGE, "-c", f"umask 077 && cat > /creds/{name}.new && mv /creds/{name}.new /creds/{name}", input=body)
    return expires


# ---------------------------------------------------------------- setup

def build_desk_image():
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(REPO / "rgtriage", Path(tmp) / "rgtriage", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(REPO / "deploy/workstation/Dockerfile", Path(tmp) / "Dockerfile")
        docker("build", "-q", "-t", DESK_IMAGE, tmp)


def prepare_volumes():
    for volume in VOLUMES.values():
        if not exists("volume", volume):
            docker("volume", "create", volume, capture=True)
    # Volumes start root-owned; both containers run as uid 10000.
    docker("run", "--rm", "--user", "0", "--entrypoint", "sh", *sum((["-v", f"{v}:/v/{k}"] for k, v in VOLUMES.items()), []),
           DESK_IMAGE, "-c", "mkdir -p /v/hermes/proposals /v/desk/.home && chown -R 10000:10000 /v && chmod 700 /v/creds")


def restore(data: Path):
    result = docker("run", "--rm", "--user", "10000:10000", "-v", f"{VOLUMES['hermes']}:/opt/data", "-v",
                    f"{VOLUMES['desk']}:/data/rgtriage", "-v", f"{host_path(data / 'durable')}:/durable", DESK_IMAGE,
                    "durable", "restore", "--url", "/durable", "--home", "hermes=/opt/data", "--home", "desk=/data/rgtriage",
                    capture=True)
    for line in result.stdout.splitlines():
        status = json.loads(line)
        if status["status"] == "RESTORED":
            print(f"  restored {status['home']} from checkpoint {status['created_at']}")


def write_desk_profile(args):
    has = docker("run", "--rm", "-v", f"{VOLUMES['desk']}:/data/rgtriage", "--entrypoint", "test", DESK_IMAGE,
                 "-f", "/data/rgtriage/triage.yaml", check=False, capture=True).returncode == 0
    if has:
        return
    account = boto3.Session(profile_name=args.aws_profile or None).client("sts").get_caller_identity()["Account"]
    text = (f"# RemediGenius-CE desk profile (workstation). Edit freely; it is checkpointed to {args.data}.\n"
            f"name: workstation-{account}\nregions: [{', '.join(args.regions or [args.region])}]\n"
            f"accounts:\n  - name: workstation-{account}\n    account_id: '{account}'\n    criticality: business_critical\n"
            "goals:\n  - text: Protect customer data stored in S3 and databases\n"
            "    boost: {resource_types: [AwsS3Bucket, AwsRdsDbInstance, AwsDynamoDbTable], points: 5}\n"
            "  - text: Detect and stop misuse of privileged identities\n"
            "    boost: {resource_types: [AwsIamUser, AwsIamRole, AwsIamAccessKey], signals: [identity_risk, root_usage], points: 5}\n"
            f"iac_paths: [{'/data/iac' if args.iac else ''}]\n"
            f"storage:\n  profile: local\n  namespace: remedigenius\n  installation_id: workstation-{account}\n"
            "  maintenance: {snapshot_retention_days: 14, min_snapshots: 5, target_file_size_mb: 128, interval_hours: 24, orphan_retention_hours: 72}\n")
    docker("run", "--rm", "-i", "-v", f"{VOLUMES['desk']}:/data/rgtriage", "--entrypoint", "sh", DESK_IMAGE, "-c",
           "cat > /data/rgtriage/triage.yaml", input=text)


def login_file(data: Path) -> dict:
    path = data / "login.json"
    if not path.exists():
        path.write_text(json.dumps({"username": "owner", "password": secrets.token_urlsafe(24), "secret": secrets.token_hex(32)}))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return json.loads(path.read_text())


def start_desk(args):
    docker("rm", "-f", DESK, check=False, capture=True)
    run = ["run", "-d", "--name", DESK, "--restart", "unless-stopped", "--read-only", "--tmpfs", "/tmp",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1g",
           "-v", f"{VOLUMES['creds']}:/creds:ro", "-v", f"{VOLUMES['desk']}:/data/rgtriage",
           "-v", f"{VOLUMES['hermes']}:/opt/data:ro", "-v", f"{VOLUMES['socket']}:/run/rgtriage",
           "-v", f"{host_path(args.data / 'durable')}:/durable", "-e", f"AWS_DEFAULT_REGION={args.region}",
           "-e", "RGTRIAGE_DURABLE=1",
           "-e", f"REMEDIGENIUS_MODEL_NAME={args.model_name or ''}", "-e", f"REMEDIGENIUS_MODEL_BASE_URL={args.model_base_url or ''}"]
    if args.iac:
        run += ["-v", f"{host_path(Path(args.iac))}:/data/iac:ro"]
    docker(*run, DESK_IMAGE, "serve", "--socket", SOCKET, "--durable", "/durable", "--home", "hermes=/opt/data",
           "--home", "desk=/data/rgtriage", "--every", "120", "--scan-every-hours", str(args.scan_every_hours), capture=True)
    for _ in range(30):
        if docker("exec", DESK, "test", "-S", SOCKET, check=False, capture=True).returncode == 0:
            return
        time.sleep(1)
    raise SystemExit(f"desk did not start: docker logs {DESK}")


ENABLE_PROFILE_PLUGIN = r'''
from pathlib import Path
from ruamel.yaml import YAML
yaml, path = YAML(), Path("/opt/data/profiles/remedigenius/config.yaml")
data = yaml.load(path.read_text())
enabled = data.setdefault("plugins", {}).setdefault("enabled", [])
if "rg-knowledge" not in enabled:
    enabled.append("rg-knowledge")
    with path.open("w") as f:
        yaml.dump(data, f)
'''
SYNC = r'''
import json, os, shutil
from pathlib import Path
pkg, prof = Path("/opt/remedigenius-package"), Path("/opt/data/profiles/remedigenius")
shutil.copy2(pkg / "SOUL.md", prof / "SOUL.md")
for skill in (pkg / "skills").iterdir():
    t = prof / "skills" / skill.name
    shutil.rmtree(t, ignore_errors=True); shutil.copytree(skill, t)
plugin = prof / "plugins/rg-triage"
shutil.rmtree(plugin, ignore_errors=True)
shutil.copytree(pkg / "plugins/rg-triage", plugin, ignore=shutil.ignore_patterns("__pycache__", "local.json"))
(plugin / "local.json").write_text(json.dumps({"socket": "/run/rgtriage/rgtriage.sock", "home": "/data/rgtriage",
                                               "proposals": "/opt/data/proposals"}))
(prof / "scripts").mkdir(exist_ok=True)
(prof / "scripts/rgtriage-watch.py").write_text(WATCH)
# Knowledge tab (dashboard plugin) and the folders it hands files to the desk through.
tab = Path("/opt/data/plugins/rg-knowledge")
shutil.rmtree(tab, ignore_errors=True)
shutil.copytree(pkg / "dashboard-plugins/rg-knowledge", tab, ignore=shutil.ignore_patterns("__pycache__", "local.json"))
(tab / "local.json").write_text(json.dumps({"socket": "/run/rgtriage/rgtriage.sock", "home": "/data/rgtriage",
                                            "proposals": "/opt/data/proposals", "inbox": "/opt/data/knowledge-inbox",
                                            "files": "/opt/data/knowledge-files", "profile": "remedigenius",
                                            "improve": "/opt/data/rg-improve", "package": "/opt/remedigenius-package"}))
# Dashboard tab: serves the page the desk writes; refresh asks the desk for a scan.
board_tab = Path("/opt/data/plugins/rg-board")
shutil.rmtree(board_tab, ignore_errors=True)
shutil.copytree(pkg / "dashboard-plugins/rg-board", board_tab, ignore=shutil.ignore_patterns("__pycache__", "local.json"))
(board_tab / "local.json").write_text(json.dumps({"socket": "/run/rgtriage/rgtriage.sock",
                                                  "board": "/data/rgtriage/board.html",
                                                  "status": "/data/rgtriage/status.json"}))
for d in ("proposals/knowledge", "knowledge-inbox", "knowledge-files", "rg-improve", "rg-traces"):
    Path("/opt/data", d).mkdir(parents=True, exist_ok=True)
# Skill improvements a person approved survive restarts when they were made for this shipped version.
import sys
sys.path.insert(0, str(tab))
from improve.runner import apply_approved
print(json.dumps(apply_approved(Path("/opt/data/rg-improve"), pkg / "skills", prof / "skills")))
key = os.environ.get("MODEL_API_KEY", "")
env = prof / ".env"
text = env.read_text() if env.exists() else ""
if key and not any(l.startswith("MODEL_API_KEY=") for l in text.splitlines()):
    env.write_text(text.rstrip() + ("\n" if text.strip() else "") + "MODEL_API_KEY=" + key + "\n"); env.chmod(0o600)
'''
WATCH = r'''"""Hermes cron script: print only new P1/P2 security findings (empty output = silent)."""
import json, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(1200); s.connect("/run/rgtriage/rgtriage.sock")
s.sendall(json.dumps({"args": ["watch", "--min-priority", "P2"]}).encode() + b"\n")
data = b""
while True:
    chunk = s.recv(65536)
    if not chunk:
        break
    data += chunk
reply = json.loads(data)
print(reply.get("stdout", "") if reply.get("rc") == 0 else "rgtriage watch failed: " + reply.get("stderr", "")[-600:], end="")
'''


def seed_config(args) -> Path:
    """Profile package with the model block filled in (or removed, so Hermes asks for a model)."""
    package = args.data / "package"
    if package.exists():
        shutil.rmtree(package)
    shutil.copytree(REPO / "profiles/remedigenius", package, ignore=shutil.ignore_patterns("__pycache__", "local.json"))
    config = package / "config.yaml"
    text = config.read_text(encoding="utf-8")
    if os.environ.get("REMEDIGENIUS_MODEL_KEY") and args.model_base_url:
        text = text.replace("__MODEL_NAME__", json.dumps(args.model_name)).replace("__MODEL_BASE_URL__", json.dumps(args.model_base_url))
    else:
        lines, out, skipping = text.splitlines(keepends=True), [], False
        for line in lines:
            if line.startswith("model:"):
                skipping = True
                continue
            if skipping and (line.startswith((" ", "\t")) or not line.strip()):
                continue
            skipping = False
            out.append(line)
        text = "".join(out)
    config.write_text(text, encoding="utf-8")
    return package


def start_hermes(args):
    login = login_file(args.data)
    package = seed_config(args)
    docker("rm", "-f", HERMES, check=False, capture=True)
    env = {"HERMES_DASHBOARD": "1", "HERMES_DASHBOARD_PORT": "9120", "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": login["username"],
           "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD": login["password"], "HERMES_DASHBOARD_BASIC_AUTH_SECRET": login["secret"],
           "AWS_EC2_METADATA_DISABLED": "true", "HERMES_TUI_TOOLSETS": "skills,clarify,file,rg_triage"}
    flags = sum((["-e", f"{k}={v}"] for k, v in env.items()), [])
    if os.environ.get("REMEDIGENIUS_MODEL_KEY"):
        os.environ["MODEL_API_KEY"] = os.environ["REMEDIGENIUS_MODEL_KEY"]
        flags += ["-e", "MODEL_API_KEY"]  # value comes from this process's environment, not the command line
    run = ["run", "-d", "--name", HERMES, "--restart", "unless-stopped", "-p", f"127.0.0.1:{args.port}:9120",
           "-v", f"{VOLUMES['hermes']}:/opt/data", "-v", f"{VOLUMES['socket']}:/run/rgtriage",
           "--mount", f"type=volume,src={VOLUMES['desk']},dst=/data/rgtriage,readonly",
           "-v", f"{host_path(package)}:/opt/remedigenius-package:ro", "--memory", f"{args.memory_mb}m", *flags]
    if args.iac:
        run += ["-v", f"{host_path(Path(args.iac))}:/data/iac:ro"]
    docker(*run, HERMES_IMAGE, "gateway", "run", capture=True)
    for _ in range(120):
        if docker("exec", HERMES, "test", "-f", "/opt/data/config.yaml", check=False, capture=True).returncode == 0:
            break
        time.sleep(2)
    else:
        raise SystemExit(f"Hermes did not initialize: docker logs {HERMES}")
    if docker("exec", HERMES, "test", "-d", f"/opt/data/profiles/{PROFILE}", check=False, capture=True).returncode:
        docker("exec", HERMES, "hermes", "profile", "install", "/opt/remedigenius-package", "--name", PROFILE, "--yes", capture=True)
    docker("exec", "-i", "--user", "10000:10000", HERMES, "python", "-", input=f"WATCH = {WATCH!r}\n{SYNC}")
    # The dashboard serves user plugins only when enabled: in the profile (tab list) and at its launch scope (API).
    docker("exec", "-i", "--user", "10000:10000", HERMES, "python", "-", input=ENABLE_PROFILE_PLUGIN)
    docker("exec", "--user", "10000:10000", HERMES, "hermes", "-p", "default", "plugins", "enable", "rg-knowledge", capture=True)
    for key in ("kanban.dispatch_in_gateway", "kanban.auto_decompose"):  # Kanban cards are for people, never worker agents
        docker("exec", "--user", "10000:10000", HERMES, "hermes", "-p", "default", "config", "set", key, "false", capture=True)
    docker("exec", "--user", "10000:10000", HERMES, "hermes", "profile", "use", PROFILE, capture=True)
    docker("restart", HERMES, capture=True)
    for _ in range(60):
        if docker("exec", HERMES, "test", "-f", "/opt/data/config.yaml", check=False, capture=True).returncode == 0:
            break
        time.sleep(2)
    if args.watch_deliver:
        time.sleep(5)
        jobs = docker("exec", "--user", "10000:10000", HERMES, "hermes", "-p", PROFILE, "cron", "list", check=False, capture=True)
        if "security-watch" not in (jobs.stdout or ""):
            docker("exec", "--user", "10000:10000", HERMES, "hermes", "-p", PROFILE, "cron", "create",
                   f"every {int(args.scan_every_hours)}h", "--name", "security-watch", "--no-agent", "--script",
                   "rgtriage-watch.py", "--deliver", args.watch_deliver, capture=True)


# ---------------------------------------------------------------- commands

DATA_NOTICE = ("RemediGenius-CE runs on Hermes with the model provider you configure. Findings, resource identifiers, IaC excerpts, knowledge and chat are sent to that provider; RemediGenius-CE runs no model of its own and stores nothing elsewhere. One operator, one organization per installation (not multi-tenant). Details: docs/DATA-FLOW.md")


def data_notice(args) -> None:
    """Shown before the first start; the operator's acknowledgement is recorded once (#10)."""
    ack = args.data / "data-notice-accepted"
    if ack.exists():
        return
    print("\n" + DATA_NOTICE + "\n")
    if sys.stdin.isatty() and input("Type yes to continue: ").strip().lower() != "yes":
        sys.exit("Not started.")
    ack.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")


def cmd_start(args):
    args.data.mkdir(parents=True, exist_ok=True)
    data_notice(args)
    (args.data / "durable").mkdir(exist_ok=True)
    print("Building the desk image ...")
    build_desk_image()
    prepare_volumes()
    restore(args.data)
    write_desk_profile(args)
    expires = push_credentials(args)
    start_desk(args)
    start_hermes(args)
    print(f"\nRemediGenius-CE is running: http://127.0.0.1:{args.port}/chat?profile={PROFILE}")
    print(f"Login: python tools/workstation.py login   (stored in {args.data / 'login.json'})")
    print(f"Desk AWS credentials expire: {expires}. `run` keeps them fresh; `refresh` renews once.")
    if not os.environ.get("REMEDIGENIUS_MODEL_KEY"):
        print("No REMEDIGENIUS_MODEL_KEY set: configure the model in the dashboard before chatting.")


def cmd_run(args):
    cmd_start(args)
    print("Keeping credentials fresh; Ctrl+C stops refreshing (containers keep running; `stop` stops them).")
    try:
        while True:
            time.sleep(30 * 60)
            print("Credentials refreshed; expire at " + push_credentials(args), flush=True)
    except KeyboardInterrupt:
        pass


def cmd_refresh(args):
    print("Credentials refreshed; expire at " + push_credentials(args))


def cmd_stop(args):
    # The desk writes a final checkpoint on stop (SIGTERM ends serve; checkpoint first for certainty).
    if exists("container", DESK):
        docker("exec", DESK, "python", "-m", "rgtriage", "durable", "checkpoint", "--url", "/durable", "--home", "hermes=/opt/data",
               "--home", "desk=/data/rgtriage", check=False)
    for name in (HERMES, DESK):
        docker("rm", "-f", name, check=False, capture=True)
    print(f"Stopped. Durable checkpoints remain in {args.data / 'durable'}; volumes are kept.")


def cmd_status(args):
    for name in (DESK, HERMES):
        state = docker("inspect", "-f", "{{.State.Status}}", name, check=False, capture=True)
        print(f"{name}: {(state.stdout or 'not created').strip()}")
    print(docker("exec", DESK, "python", "-m", "rgtriage", "digest", "--limit", "3", check=False, capture=True).stdout or "")


def cmd_login(args):
    print("Private dashboard login; keep it out of chat and screenshots:")
    print(json.dumps({k: v for k, v in login_file(args.data).items() if k != "secret"}))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # boards contain non-ASCII; Windows pipes default to cp1252
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["start", "run", "refresh", "stop", "status", "login"])
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument("--read-role-arn", help="read-only role to assume (recommended; e.g. SecurityAudit)")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--regions", nargs="*", help="regions to read (first start only; default --region)")
    parser.add_argument("--data", type=Path, default=Path.home() / "RemediGenius-CE", help="durable folder on this machine")
    parser.add_argument("--iac", help="folder with IaC repositories to mount read-only")
    parser.add_argument("--port", type=int, default=9125)
    parser.add_argument("--model-name", default="deepseek-v4.1-flash")
    parser.add_argument("--model-base-url", default=os.environ.get("REMEDIGENIUS_MODEL_BASE_URL", ""))
    parser.add_argument("--memory-mb", type=int, default=4096)
    parser.add_argument("--scan-every-hours", type=float, default=6)
    parser.add_argument("--watch-deliver", default="local", help="Hermes delivery target for new P1/P2 alerts; '' disables")
    args = parser.parse_args()
    {"start": cmd_start, "run": cmd_run, "refresh": cmd_refresh, "stop": cmd_stop, "status": cmd_status, "login": cmd_login}[args.command](args)


if __name__ == "__main__":
    main()
