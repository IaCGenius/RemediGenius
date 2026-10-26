"""Set up GitHub for a RemediGenius-CE Spot stack with one command. This is the supported way to start.

    python tools/github_connect_spot.py --stack <your stack name>

It forwards the callback port over SSM and runs the guided `sudo rgdesk github setup` on the instance, which:
  1. checks prerequisites and says what to fix;
  2. prints the address to open (http://localhost:8743/): in YOUR browser click "Create GitHub App" on github.com, then "Install" and
     select only the repository RemediGenius may use (GitHub consent is yours; nothing secret passes through this script);
  3. lets you pick the repository (only the ones you selected), the development branch and the human reviewers;
  4. shows which protections are present or missing, and what to do next.
Run it again any time: it resumes, it never starts over. Afterwards use `sudo rgdesk github status|verify|refresh|disconnect` in an SSM session.

Needs the AWS CLI with the Session Manager plugin and boto3, using your current AWS credentials.
"""
from __future__ import annotations

import argparse
import contextlib
import shutil
import socket
import subprocess
import sys
import time

PORT = 8743


def forward_command(aws: str, region: str, instance: str, port: int = PORT) -> list[str]:
    return [aws, "ssm", "start-session", "--region", region, "--target", instance, "--document-name", "AWS-StartPortForwardingSession",
            "--parameters", f"portNumber={port},localPortNumber={port}"]


def connect_command(aws: str, region: str, instance: str, port: int = PORT, extra: str = "") -> list[str]:
    remote = f"sudo rgdesk github setup --no-browser --port {port} {extra}".strip()
    return [aws, "ssm", "start-session", "--region", region, "--target", instance, "--document-name", "AWS-StartInteractiveCommand",
            "--parameters", f'command=["{remote}"]']


def find_instance(region: str, stack: str) -> str:
    import boto3
    groups = boto3.client("autoscaling", region_name=region).describe_auto_scaling_groups(AutoScalingGroupNames=[stack])["AutoScalingGroups"]
    ids = [i["InstanceId"] for g in groups for i in g["Instances"] if i["LifecycleState"] == "InService"]
    if not ids:
        raise SystemExit(f"no running instance in stack {stack!r}")
    return ids[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack", default="rgce-release-test", help="the stack name (the Auto Scaling group)")
    ap.add_argument("--instance", help="instance id (default: the stack's running instance)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--org", help="create the App under this organization you own")
    ap.add_argument("--reconnect", action="store_true", help="create a new App even if one is already connected (see docs/GITHUB.md)")
    args = ap.parse_args()
    aws = shutil.which("aws")
    if not aws:
        raise SystemExit("the AWS CLI with the Session Manager plugin is required")
    instance = args.instance or find_instance(args.region, args.stack)
    extra = " ".join(filter(None, [f"--org {args.org}" if args.org else "", "--reconnect" if args.reconnect else ""]))
    forwarder = subprocess.Popen(forward_command(aws, args.region, instance), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", PORT), timeout=1):
                break
            time.sleep(1)
        print(f"Port {PORT} forwarded to the instance. When the address appears below, open it in your browser.\n", flush=True)
        sys.exit(subprocess.run(connect_command(aws, args.region, instance, extra=extra)).returncode)
    finally:
        if sys.platform == "win32":  # aws.exe starts session-manager-plugin as a child; stop the whole tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(forwarder.pid)], capture_output=True)
        else:
            forwarder.terminate()


if __name__ == "__main__":
    main()
