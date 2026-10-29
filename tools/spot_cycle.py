"""Start, park or inspect the private RemediGenius-CE stack (deploy/aws-private).

  python tools/spot_cycle.py up          # compute on: ASG desired 1 (2-3 minutes, no re-provisioning)
  python tools/spot_cycle.py down        # compute off: ASG desired 0; bucket, Glue database and IAM stay
  python tools/spot_cycle.py status      # ASG state and instance ids

The durable stack (deploy/aws-static) and the image (deploy/ami) are provisioned once and not touched here. Use the
full from-nothing apply of deploy/aws-single when you are validating a release rather than iterating.

Settings live outside the repository, like the Spot test settings:

  {"account_id": "...", "subnet_id": "subnet-...", "region": "us-east-1",
   "state_bucket": "...", "ami_id": "ami-...", "source_zip": "dist/v0.5.0/remedigenius-ce-0.5.0-spot.zip",
   "model_secret_arn": "arn:aws:secretsmanager:...", "model_name": "...", "model_base_url": "https://..."}

Every key in that file is passed to Terraform as-is, so any variable of deploy/aws-private may be set there.
Requires terraform on PATH and AWS credentials for the account in the settings file; nothing is read from the repo.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "deploy" / "aws-private"


def mask(text: str) -> str:
    """Never print a 12-digit account id, even in an error from Terraform."""
    import re
    return re.sub(r"(?<!\d)\d{12}(?!\d)", "****************", text)


def terraform(*args: str, capture: bool = False) -> str:
    proc = subprocess.run(["terraform", f"-chdir={STACK}", *args], capture_output=capture, text=True)
    if proc.returncode:
        raise SystemExit(mask((proc.stderr or proc.stdout or "terraform failed").strip()[-1500:]))
    return (proc.stdout or "").strip()


def init(settings: dict) -> None:
    terraform("init", "-input=false", "-reconfigure",
              f"-backend-config=bucket={settings['state_bucket']}",
              f"-backend-config=region={settings.get('region', 'us-east-1')}",
              "-backend-config=use_lockfile=true")


def apply(settings: dict, running: bool) -> None:
    path = Path(settings.pop("_vars_file"))
    terraform("apply", "-auto-approve", "-input=false", f"-var-file={path}", f"-var=running={'true' if running else 'false'}")


def status(settings: dict) -> int:
    group = terraform("output", "-raw", "autoscaling_group", capture=True)
    out = subprocess.run(["aws", "autoscaling", "describe-auto-scaling-groups", "--auto-scaling-group-names", group,
                          "--region", settings.get("region", "us-east-1"),
                          "--query", "AutoScalingGroups[0].[DesiredCapacity,Instances[].InstanceId]", "--output", "text"],
                         capture_output=True, text=True)
    if out.returncode:
        print(mask(out.stderr.strip()[-600:]))
        return 1
    print(f"{group}: {mask(out.stdout.strip()) or '0'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["up", "down", "status"])
    parser.add_argument("--settings", default=str(ROOT / ".rgce" / "private-stack.json"),
                        help="JSON variables for deploy/aws-private (default .rgce/private-stack.json)")
    parser.add_argument("--init", action="store_true", help="run terraform init with the state bucket first")
    args = parser.parse_args()

    settings = json.loads(Path(args.settings).read_text(encoding="utf-8"))
    settings["_vars_file"] = args.settings
    if args.init:
        init(settings)
    if args.action == "status":
        return status(settings)
    apply(settings, running=args.action == "up")
    return status(settings)


if __name__ == "__main__":
    sys.exit(main())