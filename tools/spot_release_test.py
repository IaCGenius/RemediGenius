"""Test a published RemediGenius Community Edition (RemediGenius-CE) release on AWS Spot, end to end, unattended.

    python tools/spot_release_test.py v0.3.2 --settings ~/rgce-spot-test.json

1. Downloads the release assets from GitHub and checks them against SHA256SUMS.
2. Deploys a fresh stack with the release's own Terraform (deploy/aws-single), named rgce-release-test so it never
   touches a real installation, with delete_data_on_destroy=true and no data from earlier runs.
3. Waits for the instance, then checks it over SSM: version, services, skills, plugins, config schema, warnings,
   and that the dashboard serves the release's Knowledge tab code.
4. Opens SSM tunnels and checks the dashboard Knowledge tab and every Hermes WebUI menu in headless Chrome
   (needs `pip install playwright`); browser errors and failed API calls fail the run.
5. Asks the agent "hi" once and saves the answer in the report (model output is recorded, not judged).
6. Always destroys the whole stack, bucket included, unless --keep is given.

The settings file holds your environment and stays outside the repository:
    {"account_id": "...", "subnet_id": "subnet-...", "region": "us-east-1",
     "model_secret_arn": "arn:aws:secretsmanager:...", "model_name": "...", "model_base_url": "https://..."}
It is passed to Terraform as-is, so any variable of deploy/aws-single may be set there.

Needs terraform, the AWS CLI with the Session Manager plugin, and boto3, all using your current AWS credentials.
The report and screenshots go to the work folder (default .rgce/release-test-VERSION); 12-digit account ids are
masked in everything this script prints or writes. The dashboard login is read into memory only.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "rgce-release-test"
ASSETS = ["SHA256SUMS", "RELEASE.json", "remedigenius-ce-{v}-spot.zip", "remedigenius-ce-{v}-source.zip"]
SERVED_JS = "/data/hermes/plugins/rg-knowledge/dashboard/dist/index.js"
JS_IN_ZIP = "profiles/remedigenius/dashboard-plugins/rg-knowledge/dashboard/dist/index.js"

HOST_CHECKS = r"""
check() { if [ "$2" = 0 ]; then echo "CHECK|$1|PASS|$3"; else echo "CHECK|$1|FAIL|$3"; fi; }
H="docker exec --user 10000:10000 remedigenius hermes"
log=/var/log/cloud-init-output.log
n=$(grep -cE "Traceback|^ERROR" $log); check "boot without errors" $([ "$n" = 0 ]; echo $?) "$n error lines"
grep -q "RemediGenius-CE ready" $log; check "boot finished" $? "$(grep -o 'Up [0-9.]* seconds' $log | tail -1)"
s=$(systemctl is-active remedigenius-desk remedigenius-hermes remedigenius-scan.timer remedigenius-webui | tr '\n' ' ')
check "services active" $(echo "$s" | grep -qv -e inactive -e failed; echo $?) "$s"
v=$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' /opt/rgtriage/src/rgtriage/__init__.py)
check "rgtriage version" $([ "$v" = "__VERSION__" ]; echo $?) "$v"
p=$( ($H -p remedigenius plugins list; $H -p default plugins list) 2>&1 | grep -oE "rg-[a-z-]+ +│ +enabled +│ +[0-9.]+" | sed -E 's/[^a-z0-9.-]+/ /g' | sort -u | tr '\n' ';')
check "plugins enabled at release version" $([ "$(echo "$p" | grep -o "enabled __VERSION__" | wc -l)" = 2 ]; echo $?) "$p"
k=$($H -p remedigenius skills list 2>&1 | grep -oE "rg-[a-z-]+" | sort -u | tr '\n' ' ')
check "skills load" $([ "$k" = "__SKILLS__ " ]; echo $?) "$k"
c=$(grep -h _config_version /data/hermes/profiles/remedigenius/config.yaml)
check "config schema stamped" $([ -n "$c" ]; echo $?) "$c"
m=$(journalctl -u remedigenius-hermes --no-pager -o cat | grep -ciE "migration skipped|config.*(outdated|too old)")
check "no config migration warnings" $([ "$m" = 0 ]; echo $?) "$m"
j=$(sha256sum __SERVED_JS__ | cut -c1-16)
check "dashboard serves the release Knowledge tab" $([ "$j" = "__JS_SHA__" ]; echo $?) "$j"
D="setpriv --reuid=10000 --regid=10000 --clear-groups env PYTHONPATH=/opt/rgtriage/src RGTRIAGE_HOME=/data/rgtriage HOME=/data/rgtriage/.home AWS_DEFAULT_REGION=__REGION__ /opt/rgtriage/venv/bin/python -m rgtriage"
for i in $(seq 1 30); do b=$($D digest --limit 3 2>&1); echo "$b" | grep -qiE "P[1-4]|no open findings" && break; sleep 10; done
echo "$b" | grep -qiE "P[1-4]|no open findings"; check "first scan produced a board" $? "$(echo "$b" | head -1 | cut -c1-120)"
"""


def say(*parts):
    print(mask(" ".join(str(p) for p in parts)), flush=True)


def mask(text: str) -> str:
    return re.sub(r"(?<!\d)\d{12}(?!\d)", "<account>", text)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(repo: str, tag: str, dest: Path) -> dict[str, Path]:
    version = tag.lstrip("v")
    dest.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in (a.format(v=version) for a in ASSETS):
        target = dest / name
        if not target.exists():
            urllib.request.urlretrieve(f"https://github.com/{repo}/releases/download/{tag}/{name}", target)
        files[name] = target
    for line in files["SHA256SUMS"].read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if name in files and sha256(files[name]) != digest:
            raise SystemExit(f"checksum mismatch for {name}; delete {dest} and retry")
    say(f"downloaded {tag}: checksums OK")
    return files


def run(cmd, cwd=None, check=True, timeout=1800) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if check and result.returncode:
        raise SystemExit(mask(f"{' '.join(map(str, cmd[:3]))} failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"))
    return result


class Instance:
    def __init__(self, region: str, group: str):
        import boto3
        self.ssm = boto3.client("ssm", region_name=region)
        self.asg = boto3.client("autoscaling", region_name=region)
        self.group, self.id = group, None

    def wait_online(self, timeout=900):
        deadline = time.time() + timeout
        while time.time() < deadline:
            groups = self.asg.describe_auto_scaling_groups(AutoScalingGroupNames=[self.group])["AutoScalingGroups"]
            ids = [i["InstanceId"] for g in groups for i in g["Instances"] if i["LifecycleState"] == "InService"]
            if ids:
                info = self.ssm.describe_instance_information(Filters=[{"Key": "InstanceIds", "Values": ids[:1]}])
                if any(i["PingStatus"] == "Online" for i in info["InstanceInformationList"]):
                    self.id = ids[0]
                    return self.id
            time.sleep(15)
        raise SystemExit("instance did not come online in time")

    def shell(self, script: str, timeout=600) -> str:
        command = self.ssm.send_command(InstanceIds=[self.id], DocumentName="AWS-RunShellScript", TimeoutSeconds=60,
                                        Parameters={"commands": [script], "executionTimeout": [str(timeout)]})
        command_id = command["Command"]["CommandId"]
        deadline = time.time() + timeout + 90
        while time.time() < deadline:
            time.sleep(5)
            try:
                out = self.ssm.get_command_invocation(CommandId=command_id, InstanceId=self.id)
            except self.ssm.exceptions.InvocationDoesNotExist:
                continue
            if out["Status"] not in ("Pending", "InProgress", "Delayed"):
                return out["StandardOutputContent"] + out["StandardErrorContent"][-1500:]
        raise SystemExit("SSM command timed out")


@contextlib.contextmanager
def tunnel(aws: str, region: str, instance: str, remote: int, local: int):
    proc = subprocess.Popen([aws, "ssm", "start-session", "--region", region, "--target", instance,
                             "--document-name", "AWS-StartPortForwardingSession",
                             "--parameters", f"portNumber={remote},localPortNumber={local}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", local), timeout=1):
                break
            time.sleep(1)
        yield f"http://127.0.0.1:{local}"
    finally:
        if os.name == "nt":  # aws.exe starts session-manager-plugin as a child; stop the whole tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.terminate()


def browser_checks(dashboard: str, webui: str, login: dict, out: Path) -> list[tuple[str, bool, str]]:
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, failures = [], []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.on("console", lambda m: errors.append(m.text[:200]) if m.type == "error" else None)
        page.on("response", lambda r: failures.append(f"{r.status} {r.url.split('/', 3)[-1][:100]}")
                if "/api/" in r.url and r.status >= 400 else None)
        page.goto(f"{dashboard}/chat?profile=remedigenius", wait_until="networkidle")
        page.fill("input[name=username]", login["username"])
        page.fill("input[name=password]", login["password"])
        page.click("button:has-text('SIGN IN')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        for _ in range(3):  # the chat page may still be navigating; a superseded navigation aborts
            with contextlib.suppress(Exception):
                page.goto(f"{dashboard}/knowledge?profile=remedigenius", wait_until="domcontentloaded")
                break
            page.wait_for_timeout(3000)
        try:
            page.wait_for_selector(".rgk-page", timeout=60000)
            page.locator("button.rgk-tab", has_text="Graph").first.click()
            page.wait_for_selector("svg.rgk-graph g.rgk-node", timeout=30000)
            nodes = page.locator("svg.rgk-graph g.rgk-node").count()
            results.append(("dashboard Knowledge tab renders the graph", nodes > 0, f"{nodes} concepts"))
        except Exception as exc:
            results.append(("dashboard Knowledge tab renders the graph", False, str(exc).splitlines()[0]))
        page.screenshot(path=str(out / "dashboard-knowledge.png"))
        results.append(("dashboard without browser errors", not errors, "; ".join(errors[:3]) or "none"))

        errors.clear()
        failures.clear()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.on("response", lambda r: failures.append(f"{r.status} {r.url.split('/', 3)[-1][:100]}")
                if "/api/" in r.url and r.status >= 400 else None)
        page.goto(webui, wait_until="domcontentloaded")
        if page.locator("input[type=password]").count():
            page.fill("input[type=password]", login["password"])
            page.keyboard.press("Enter")
        page.wait_for_timeout(6000)
        if page.locator("button:visible", has_text="Skip setup").count():
            page.locator("button:visible", has_text="Skip setup").first.click()
            page.wait_for_timeout(1500)
        items = page.evaluate("""() => [...document.querySelectorAll('button, a, [role=tab], [data-panel], [data-view]')]
            .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.left < 90 && r.top > 40 && r.top < 900; })
            .map(e => ({label: (e.getAttribute('aria-label') || e.title || e.dataset.panel || e.innerText || '').trim(),
                        x: Math.round(e.getBoundingClientRect().left + 5), y: Math.round(e.getBoundingClientRect().top + 5)}))""")
        labels = []
        for item in items:
            if item["label"] and item["label"] not in labels:
                labels.append(item["label"])
                page.mouse.click(item["x"], item["y"])
                page.wait_for_timeout(2500)
        page.screenshot(path=str(out / "webui-last-menu.png"))
        results.append(("WebUI menus open", len(labels) >= 5, f"{len(labels)} menus"))
        results.append(("WebUI without browser errors or failed API calls", not errors and not failures,
                        "; ".join((errors + failures)[:3]) or "none"))
        browser.close()
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag", help="release tag, e.g. v0.3.2")
    ap.add_argument("--settings", required=True, type=Path, help="JSON file with your Terraform variables (kept out of the repo)")
    ap.add_argument("--repo", default="IaCGenius/RemediGenius")
    ap.add_argument("--workdir", type=Path, help="default: .rgce/release-test-TAG")
    ap.add_argument("--keep", action="store_true", help="leave the stack running for manual testing (destroy it yourself)")
    ap.add_argument("--skip-browser", action="store_true", help="skip the dashboard/WebUI browser checks")
    ap.add_argument("--skip-chat", action="store_true", help="do not ask the agent anything (no model tokens)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    version = args.tag.lstrip("v")
    work = (args.workdir or ROOT / ".rgce" / f"release-test-{args.tag}").resolve()
    terraform, aws = shutil.which("terraform"), shutil.which("aws")
    if not terraform or not aws:
        raise SystemExit("terraform and the AWS CLI must be on PATH")
    settings = json.loads(args.settings.expanduser().read_text(encoding="utf-8"))
    region = settings.get("region", "us-east-1")

    files = download(args.repo, args.tag, work / "release")
    spot_zip = files[f"remedigenius-ce-{version}-spot.zip"]
    with zipfile.ZipFile(spot_zip) as z:
        js_sha = hashlib.sha256(z.read(JS_IN_ZIP)).hexdigest()[:16]
        skills = sorted({n.split("/")[3] for n in z.namelist() if n.startswith("profiles/remedigenius/skills/rg-")})
    source = work / "source"
    if source.exists():
        shutil.rmtree(source)
    with zipfile.ZipFile(files[f"remedigenius-ce-{version}-source.zip"]) as z:
        z.extractall(source)
    stack = source / f"remedigenius-ce-{version}" / "deploy" / "aws-single"
    tfvars = {**settings, "name": NAME, "source_zip": spot_zip.as_posix(), "delete_data_on_destroy": True, "region": region}
    (stack / "release-test.auto.tfvars.json").write_text(json.dumps(tfvars, indent=1), encoding="utf-8")
    state = work / "terraform.tfstate"  # outside the extracted source, so a re-run can still destroy
    tf = [terraform, f"-chdir={stack}"]
    started = time.time()
    results: list[tuple[str, bool, str]] = []
    briefing = ""
    try:
        say("terraform apply (release Terraform, stack", NAME + ") ...")
        run(tf + ["init", "-input=false", "-no-color"])
        run(tf + ["apply", "-input=false", "-no-color", "-auto-approve", f"-state={state}"])
        instance = Instance(region, NAME)
        say("instance", instance.wait_online(), "online; waiting for boot")
        say(instance.shell("cloud-init status --wait >/dev/null 2>&1; cloud-init status", timeout=1200).strip())
        script = (HOST_CHECKS.replace("__VERSION__", version).replace("__SKILLS__", " ".join(skills))
                  .replace("__SERVED_JS__", SERVED_JS).replace("__JS_SHA__", js_sha).replace("__REGION__", region))
        for line in instance.shell(script, timeout=600).splitlines():
            if line.startswith("CHECK|"):
                _, name, status, detail = (line.split("|", 3) + [""])[:4]
                results.append((name, status == "PASS", detail.strip()))
        if not args.skip_browser:
            login = json.loads(re.search(r"\{.*\}", instance.shell("cat /data/hermes/remedigenius-login.json"), re.S).group(0))
            with tunnel(aws, region, instance.id, 9120, 9125) as dashboard, tunnel(aws, region, instance.id, 8787, 9126) as webui:
                results += browser_checks(dashboard, webui, login, work)
        if not args.skip_chat:
            say("asking the agent 'hi' (model output is recorded, not judged) ...")
            briefing = instance.shell("timeout 600 docker exec --user 10000:10000 remedigenius "
                                      "hermes -p remedigenius chat -q 'hi' 2>&1 | tail -c 6000", timeout=700)
    except BaseException as exc:
        results.append(("run completed", False, str(exc).splitlines()[0] if str(exc) else type(exc).__name__))
    finally:
        if args.keep:
            say(f"--keep: stack left running. Destroy it with: terraform -chdir={stack} destroy -state={state}")
        else:
            say("terraform destroy (everything, bucket included) ...")
            destroyed = run(tf + ["destroy", "-input=false", "-no-color", "-auto-approve", f"-state={state}"], check=False)
            results.append(("stack destroyed", destroyed.returncode == 0, destroyed.stdout.strip().splitlines()[-1:][0]
                            if destroyed.stdout.strip() else destroyed.stderr[-300:]))

    passed = all(ok for _, ok, _ in results)
    lines = [f"# RemediGenius-CE {args.tag} on Spot: {'PASS' if passed else 'FAIL'}", "",
             f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}, {round((time.time() - started) / 60)} min, region {region}", "",
             "| Check | Result | Detail |", "| --- | --- | --- |"]
    lines += [f"| {name} | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |" for name, ok, detail in results]
    if briefing:
        lines += ["", "## Agent answer to \"hi\" (recorded, not judged)", "", "```", briefing.strip(), "```"]
    report = mask("\n".join(lines) + "\n")
    (work / "report.md").write_text(report, encoding="utf-8")
    print(report.split("\n## ")[0])
    say(f"report: {work / 'report.md'}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
