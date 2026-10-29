"""Test a published RemediGenius Community Edition (RemediGenius-CE) release on AWS Spot, end to end, unattended.

    python tools/spot_release_test.py v0.3.2 --settings ~/rgce-spot-test.json

1. Downloads the release assets from GitHub and checks them against SHA256SUMS.
2. Deploys a fresh stack with the release's own Terraform (deploy/aws-single), named rgce-release-test by default
   (use --name for a separate stack) so it never touches a real installation, with delete_data_on_destroy=true and no
   data from earlier runs.
3. Waits for the instance, then checks it over SSM: version, services, skills, plugins, config schema, warnings,
   and that the dashboard serves the release's Knowledge tab code.
4. Opens an SSM tunnel and checks, in headless Chrome, the dashboard Knowledge tab and the GitHub tab (the page renders, shows the
   connect step, makes no failing API call). Needs `pip install playwright`; browser errors and failed API calls fail the run.
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
s=$(systemctl is-active remedigenius-desk remedigenius-hermes remedigenius-validate remedigenius-scan.timer | tr '\n' ' ')
check "services active" $(echo "$s" | grep -qv -e inactive -e failed; echo $?) "$s"
v=$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' /opt/rgtriage/src/rgtriage/__init__.py)
check "rgtriage version" $([ "$v" = "__VERSION__" ]; echo $?) "$v"
p=$( ($H -p remedigenius plugins list; $H -p default plugins list) 2>&1 | grep -oE "rg-[a-z-]+ +│ +enabled +│ +[0-9.]+" | sed -E 's/[^a-z0-9.-]+/ /g' | sort -u | tr '\n' ';')
check "plugins enabled at release version" $([ "$(echo "$p" | grep -o "enabled __VERSION__" | wc -l)" = 3 ]; echo $?) "$p"
k=$($H -p remedigenius skills list 2>&1 | grep -oE "rg-[a-z-]+" | sort -u | tr '\n' ' ')
check "skills load" $([ "$k" = "__SKILLS__ " ]; echo $?) "$k"
c=$(grep -h _config_version /data/hermes/profiles/remedigenius/config.yaml)
check "config schema stamped" $([ -n "$c" ]; echo $?) "$c"
m=$(journalctl -u remedigenius-hermes --no-pager -o cat | grep -ciE "migration skipped|config.*(outdated|too old)")
check "no config migration warnings" $([ "$m" = 0 ]; echo $?) "$m"
j=$(sha256sum __SERVED_JS__ | cut -c1-16)
check "dashboard serves the release Knowledge tab" $([ "$j" = "__JS_SHA__" ]; echo $?) "$j"
D="setpriv --reuid=10000 --regid=10000 --clear-groups env PYTHONPATH=/opt/rgtriage/src RGTRIAGE_HOME=/data/rgtriage RGTRIAGE_DURABLE=1 RGTRIAGE_CONFIG=/data/rgconfig/triage.yaml HOME=/data/rgtriage/.home AWS_DEFAULT_REGION=__REGION__ /opt/rgtriage/venv/bin/python -m rgtriage"
for i in $(seq 1 30); do b=$($D digest --limit 3 2>&1); echo "$b" | grep -qiE "P[1-4]|no open findings" && break; sleep 10; done
echo "$b" | grep -qiE "P[1-4]|no open findings"; check "first scan produced a board" $? "$(echo "$b" | head -1 | cut -c1-120)"
c=$($H -p default config get kanban.dispatch_in_gateway 2>&1 | tail -1)
check "Kanban dispatcher off" $([ "$c" = "false" ]; echo $?) "$c"
if [ -x /usr/local/bin/rgdesk ]; then
  g=$(rgdesk github status 2>&1)
  ghost=$(systemctl list-unit-files 2>/dev/null | grep -c remedigenius-webui; docker ps -a --format '{{.Names}}' | grep -c webui; ss -ltn 2>/dev/null | grep -cE ':(8787|8642)\b')
  check "no WebUI service or container, and nothing on the host listening on its port (8787) or the old API port (8642)" $([ "$(echo $ghost | tr -d ' 0')" = "" ]; echo $?) "unit/container/port counts: $(echo $ghost | tr '\n' ' ')"
  cip=$(docker inspect remedigenius --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
  a1=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://$cip:8642/health); a2=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8642/health)
  bound=$(docker exec --user 10000:10000 remedigenius python -c "
for l in open('/proc/net/tcp').read().splitlines()[1:]:
    f = l.split()
    if f[3] == '0A' and int(f[1].split(':')[1], 16) == 8642: print(f[1].split(':')[0])" 2>&1 | head -1)
  check "the agent's API server is not reachable from outside the agent container (Hermes keeps it on loopback inside; nothing is published for it)" $([ "$a1" = 000 ] && [ "$a2" = 000 ] && { [ -z "$bound" ] || [ "$bound" = 0100007F ]; }; echo $?) "from host via container address: http $a1; host loopback: http $a2; bound to: ${bound:-closed}"
  left=$( [ -e /data/hermes/.remedigenius-api-key ] && echo key; [ -e /data/hermes/rg-wiki ] && echo wiki; grep -l API_SERVER_KEY /data/hermes/profiles/remedigenius/.env 2>/dev/null | head -1; true )
  check "nothing is left from an earlier release's WebUI (shared API key, wiki view, key in the profile .env)" $([ -z "$left" ]; echo $?) "left: [$(echo $left)] (Hermes writes its own key in /data/hermes/.env; the WebUI's own /data/hermes/webui folder is kept on purpose)"
  check "GitHub status is readable (Disconnected on a fresh stack)" $(echo "$g" | head -1 | grep -q "^GitHub: "; echo $?) "$(echo "$g" | head -1)"
  check "validation tools installed (terraform, tflint, cfn-lint)" $(echo "$g" | grep -q "terraform yes, tflint yes, cfn-lint yes"; echo $?) "$(echo "$g" | tail -1)"
  p=$(stat -c "%a %u" /data/rggithub 2>&1); check "GitHub key folder private to the desk user" $([ "$p" = "700 10000" ]; echo $?) "$p"
  m=$(for c in remedigenius; do docker inspect $c --format '{{json .Mounts}}' 2>/dev/null; done | grep -c rggithub)
  check "GitHub key folder is not mounted into any container" $([ "$m" = 0 ]; echo $?) "$m mounts"
  r=$(docker exec --user 10000:10000 remedigenius ls /data/rggithub 2>&1 | head -1); check "agent container cannot see the GitHub key folder" $(echo "$r" | grep -qi "no such file"; echo $?) "$r"
  s=$(docker exec --user 10000:10000 remedigenius python -c "
import json,socket
for args in (['github','connect'],['github','configure','--repo','a/b','--base','dev'],['github','disconnect'],['github','status','--org','x']):
    c=socket.socket(socket.AF_UNIX); c.connect('/run/rgtriage/rgtriage.sock'); c.sendall((json.dumps({'args':args})+'\n').encode())
    print(json.loads(c.makefile().readline())['rc'], end=' ')" 2>&1)
  check "operator-only GitHub operations are refused over the agent socket" $([ "$s" = "2 2 2 2 " ]; echo $?) "$s"
  t=$(docker exec --user 10000:10000 remedigenius python -c "
import importlib.util as u
s=u.spec_from_file_location('p','/opt/data/profiles/remedigenius/plugins/rg-triage/__init__.py');m=u.module_from_spec(s);s.loader.exec_module(m)
print(m.handle({'action':'github','op':'publish','ref':'x','files':['/etc/passwd=main.tf']})[:70])" 2>&1)
  check "agent publish without a connected repository is refused" $(echo "$t" | grep -qE "DENIED|Blocked|not enabled|GitHub is not connected|not a file"; echo $?) "$t"
else check "rgdesk wrapper installed" 1 "missing"; fi
if [ -x /usr/local/bin/rgdesk ]; then
  # --- the GitHub tab (web console): setup goes through the dashboard, which holds a setup token the agent never has
  tk=/data/rggithub/operator.token; tc=/data/hermes/.rg-operator-token
  check "console setup token: both copies private to the desk user and identical" $( [ "$(stat -c '%a %u' $tk)" = "600 10000" ] && [ "$(stat -c '%a %u' $tc)" = "600 10000" ] && cmp -s $tk $tc; echo $?) "$(stat -c '%a' $tk) $(stat -c '%a' $tc)"
  tab=/data/hermes/plugins/rg-github/dashboard; check "GitHub tab plugin installed" $([ -s $tab/dist/index.js ] && [ -s $tab/plugin_api.py ] && [ -s $tab/manifest.json ]; echo $?) "$(ls $tab 2>&1 | tr '\n' ' ')"
  JAR=$(mktemp); python3 -c "import json;d=json.load(open('/data/hermes/remedigenius-login.json'));print(json.dumps({'provider':'basic','username':d['username'],'password':d['password'],'next':''}))" > $JAR.body
  curl -s -c $JAR -H 'Content-Type: application/json' -X POST --data @$JAR.body http://127.0.0.1:9120/auth/password-login > /dev/null; rm -f $JAR.body
  a=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9120/api/plugins/rg-github/status)
  check "GitHub tab API requires the dashboard login" $([ "$a" = 401 ] || [ "$a" = 403 ]; echo $?) "without login: http $a"
  b=$(curl -s -b $JAR http://127.0.0.1:9120/api/plugins/rg-github/status)
  check "GitHub tab API returns the connection status (after login)" $(echo "$b" | grep -q '"state": *"'; echo $?) "$(echo "$b" | cut -c1-90)"
  if [ -e /data/rggithub/app.json ]; then
    check "Connect GitHub starts (skipped here: this instance is already connected, and starting a reconnect could replace a real App)" 0 "skipped on purpose"
  else
    c=$(curl -s -b $JAR -H 'Content-Type: application/json' -X POST -d '{}' http://127.0.0.1:9120/api/plugins/rg-github/begin)
    check "Connect GitHub starts: github.com target, and GitHub is told to return to this console" $( (echo "$c" | grep -q 'https://github.com/settings/apps/new?state=' && echo "$c" | grep -q '127.0.0.1:9120/api/plugins/rg-github/callback' && ! echo "$c" | grep -qi 'BEGIN'); echo $?) "$(echo "$c" | cut -c1-70)"
  fi
  d=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -b $JAR "http://127.0.0.1:9120/api/plugins/rg-github/callback?code=abcdefgh1234&state=forged")
  check "a forged GitHub callback is refused and the page is shown with the reason" $(echo "$d" | grep -q '^303 .*github?error='; echo $?) "$(echo "$d" | cut -c1-110)"
  e=$(curl -s -o /dev/null -w '%{http_code}' -b $JAR -H 'Content-Type: application/json' -X POST -d '{"repo":"a/b; rm","base":"dev","reviewers":["x"]}' http://127.0.0.1:9120/api/plugins/rg-github/configure)
  check "the GitHub tab validates what it is given" $([ "$e" = 400 ]; echo $?) "http $e"
  s2=$(docker exec --user 10000:10000 remedigenius python -c "
import json,socket
t=open('/opt/data/.rg-operator-token').read().strip()
for tok in (t,'x'*43,''):
    c=socket.socket(socket.AF_UNIX); c.connect('/run/rgtriage/rgtriage.sock'); c.sendall((json.dumps({'args':['github','web-install','--json'],'operator':tok})+'\n').encode())
    print(json.loads(c.makefile().readline())['rc'], end=' ')" 2>&1)
  check "setup operations work over the real socket only with the setup token" $([ "$s2" = "0 2 2 " ]; echo $?) "$s2"
  r2=$(docker exec --user 10000:10000 remedigenius python -c "
import importlib.util as u
s=u.spec_from_file_location('p','/opt/data/profiles/remedigenius/plugins/rg-triage/__init__.py');m=u.module_from_spec(s);s.loader.exec_module(m)
print(m.on_pre_tool_call('read_file',{'path':'/opt/data/.rg-operator-token'}).get('action'))" 2>&1)
  check "the agent's file tool is blocked from reading the setup token" $([ "$r2" = block ]; echo $?) "$r2"
  rm -f $JAR
  # --- the untrusted-tools boundary (PR #19 finding 1): validation runs as its own user, away from the key and policy
  vs=$(systemctl is-active remedigenius-validate); vpid=$(systemctl show -p MainPID --value remedigenius-validate); vuid=$(ps -o uid= -p "$vpid" 2>/dev/null | tr -d ' ')
  check "validation service runs as its own user (10002)" $([ "$vs" = active ] && [ "$vuid" = 10002 ]; echo $?) "$vs uid=$vuid"
  printf 'SYNTHETIC-BROKER-KEY' > /data/rggithub/_probe.pem; printf '{"repo":"x/y"}' > /data/rggithub/_probe.json; chown 10000:10000 /data/rggithub/_probe.pem /data/rggithub/_probe.json; chmod 600 /data/rggithub/_probe.pem /data/rggithub/_probe.json
  r=$(sudo -u '#10002' cat /data/rggithub/_probe.pem 2>&1 | head -1); check "validation user cannot read the GitHub key" $(echo "$r" | grep -qi "permission denied"; echo $?) "$r"
  r=$(sudo -u '#10002' sh -c 'echo tamper >> /data/rggithub/_probe.json' 2>&1 | head -1); check "validation user cannot modify the GitHub policy" $(echo "$r" | grep -qi "permission denied"; echo $?) "$r $(cat /data/rggithub/_probe.json | cut -c1-20)"
  r=$(sudo -u '#10002' ls /data/rggithub 2>&1 | head -1); check "validation user cannot even list the key folder" $(echo "$r" | grep -qi "permission denied"; echo $?) "$r"
  c=$(sudo -u '#10002' curl -s -m 5 -o /dev/null -w '%{http_code}' http://169.254.169.254/latest/meta-data/ 2>&1); check "validation user cannot reach the instance metadata service" $([ "$c" = 000 ]; echo $?) "http $c"
  mkdir -p /data/iac/_rgtest; printf 'locals {\n  a = 1\n}\n' > /data/iac/_rgtest/main.tf; chown -R 10000:10000 /data/iac/_rgtest; printf 'locals {\n  b = 2\n}\n' > /opt/data/proposals/_t.tf; chown 10000:10000 /opt/data/proposals/_t.tf
  rm -f /data/rgtriage/stolen.pem /data/rgtriage/stolen.tf
  o1=$(rgdesk validate --module /data/iac/_rgtest --file /data/rggithub/_probe.pem=/data/rgtriage/stolen.pem 2>&1 | tail -1 | cut -c1-90)
  o2=$(rgdesk validate --module /data/iac/_rgtest --file /opt/data/proposals/_t.tf=/data/rgtriage/stolen.tf 2>&1 | tail -1 | cut -c1-90)
  o3=$(rgdesk validate --module /data/rggithub --file /opt/data/proposals/_t.tf=a.tf 2>&1 | tail -1 | cut -c1-90)
  check "the key cannot be copied out through validate (absolute destination, key as source, key folder as module)" $( (echo "$o1" | grep -q DENIED && echo "$o2" | grep -q "safe relative" && echo "$o3" | grep -q DENIED && [ ! -e /data/rgtriage/stolen.pem ] && [ ! -e /data/rgtriage/stolen.tf ]); echo $?) "$o1 | $o2"
  o4=$(rgdesk validate --module /data/iac/_rgtest --file /opt/data/proposals/_t.tf=extra.tf 2>&1 | tail -1 | cut -c1-80)
  check "normal proposal validation works through the validation service" $(echo "$o4" | grep -q "VALID"; echo $?) "$o4"
  printf 'module "steal" {\n  source = "/data/rggithub"\n}\n' > /opt/data/proposals/_h.tf; chown 10000:10000 /opt/data/proposals/_h.tf
  printf 'SYNTHETIC-BROKER-KEY-DO-NOT-LEAK' > /data/rggithub/_probe.pem; chown 10000:10000 /data/rggithub/_probe.pem; chmod 600 /data/rggithub/_probe.pem
  o5=$(rgdesk validate --module /data/iac/_rgtest --file /opt/data/proposals/_h.tf=evil.tf 2>&1 | tr '\n' ' ' | cut -c1-160)
  leak=$(grep -rl "SYNTHETIC-BROKER-KEY" /data/rgtriage /data/hermes /data/iac /var/lib/rgvalidate 2>/dev/null | head -1)
  check "a hostile module pointing at the key folder cannot read it, and the key text appears nowhere the agent can read" $(echo "$o5" | grep -qE "init: FAILED|Unreadable module directory" && [ -z "$leak" ]; echo $?) "$o5 leak=[$leak]"
  rm -rf /data/iac/_rgtest /opt/data/proposals/_t.tf /opt/data/proposals/_h.tf /data/rggithub/_probe.pem /data/rggithub/_probe.json  # only our own probe files
  fw=$(iptables -S OUTPUT | grep -c "uid-owner 10002.*REJECT"); check "firewall blocks the validation user from metadata and private networks" $([ "$fw" -ge 3 ]; echo $?) "$fw rules"
fi
ref=$($D list --limit 1 --json 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['key'])" 2>/dev/null)
if [ -n "$ref" ]; then
  out=$(docker exec --user 10000:10000 remedigenius python -c "import importlib.util as u;s=u.spec_from_file_location('p','/opt/data/profiles/remedigenius/plugins/rg-triage/__init__.py');m=u.module_from_spec(s);s.loader.exec_module(m);print(m.handle({'action':'card','ref':'$ref'}))" 2>&1)
  t=$($H kanban list --json 2>&1 | python3 -c "import json,sys;t=[x for x in json.load(sys.stdin) if x.get('created_by')=='remedigenius'];print(t[0]['status'],t[0]['assignee'],t[0]['id'] if t else '') if t else print('none')" 2>&1)
  echo "$out" | grep -q "Fix in code" && [ "${t%% *}" = "triage" ] && echo "$t" | grep -q " None "; check "Kanban card filed for people (triage, unassigned, fix steps)" $? "$t"
else check "Kanban card filed for people (triage, unassigned, fix steps)" 1 "no finding to file"; fi
"""


def say(*parts):
    print(mask(" ".join(str(p) for p in parts)), flush=True)


def mask(text: str) -> str:
    return re.sub(r"(?<!\d)\d{12}(?!\d)", "<account>", text)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(repo: str, tag: str, dest: Path, local: Path | None = None) -> dict[str, Path]:
    version = tag.lstrip("v")
    dest.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in (a.format(v=version) for a in ASSETS):
        target = dest / name
        if local:  # a build from tools/package_release.py, tested before it is published
            shutil.copy2(local / name, target)
        elif not target.exists():
            urllib.request.urlretrieve(f"https://github.com/{repo}/releases/download/{tag}/{name}", target)
        files[name] = target
    for line in files["SHA256SUMS"].read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        if name in files and sha256(files[name]) != digest:
            raise SystemExit(f"checksum mismatch for {name}; delete {dest} and retry")
    say(f"{'local build' if local else 'downloaded'} {tag}: checksums OK")
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


def browser_checks(dashboard: str, login: dict, out: Path) -> list[tuple[str, bool, str]]:
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
        try:  # the GitHub tab: it renders, offers Connect GitHub on a fresh install, and its API calls succeed
            for _ in range(3):
                with contextlib.suppress(Exception):
                    page.goto(f"{dashboard}/github?profile=remedigenius", wait_until="domcontentloaded")
                    break
                page.wait_for_timeout(3000)
            page.wait_for_selector(".rgg-page", timeout=60000)
            page.wait_for_selector("button:has-text('Connect GitHub')", timeout=30000)
            heading = page.locator(".rgg-header h1").inner_text()
            results.append(("dashboard GitHub tab renders and offers Connect GitHub", heading == "GitHub", f"heading {heading!r}"))
        except Exception as exc:
            results.append(("dashboard GitHub tab renders and offers Connect GitHub", False, str(exc).splitlines()[0]))
        page.screenshot(path=str(out / "dashboard-github.png"))
        results.append(("GitHub tab without browser errors or failed API calls", not errors and not failures,
                        "; ".join((errors + failures)[:3]) or "none"))
        browser.close()
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag", help="release tag, e.g. v0.3.2")
    ap.add_argument("--settings", required=True, type=Path, help="JSON file with your Terraform variables (kept out of the repo)")
    ap.add_argument("--repo", default="IaCGenius/RemediGenius")
    ap.add_argument("--name", default=NAME, help=f"stack name (default {NAME}); use a separate name for a throwaway run")
    ap.add_argument("--workdir", type=Path, help="default: .rgce/release-test-TAG")
    ap.add_argument("--local", type=Path, help="test a local build (tools/package_release.py --release) instead of downloading")
    ap.add_argument("--keep", action="store_true", help="leave the stack running for manual testing (destroy it yourself)")
    ap.add_argument("--skip-browser", action="store_true", help="skip the dashboard browser checks (they need Chrome and memory)")
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

    files = download(args.repo, args.tag, work / "release", args.local)
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
    name = args.name
    tfvars = {**settings, "name": name, "source_zip": spot_zip.as_posix(), "delete_data_on_destroy": True, "region": region}
    (stack / "release-test.auto.tfvars.json").write_text(json.dumps(tfvars, indent=1), encoding="utf-8")
    state = work / "terraform.tfstate"  # outside the extracted source, so a re-run can still destroy
    tf = [terraform, f"-chdir={stack}"]
    started = time.time()
    results: list[tuple[str, bool, str]] = []
    briefing = ""
    try:
        say("terraform apply (release Terraform, stack", name + ") ...")
        run(tf + ["init", "-input=false", "-no-color"])
        run(tf + ["apply", "-input=false", "-no-color", "-auto-approve", f"-state={state}"])
        instance = Instance(region, name)
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
            with tunnel(aws, region, instance.id, 9120, 9125) as dashboard:
                results += browser_checks(dashboard, login, work)
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
