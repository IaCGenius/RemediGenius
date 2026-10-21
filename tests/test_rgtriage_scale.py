"""Volume behaviour: a 40,000-finding Inspector estate plus Security Hub, through the real CLI path.

The fake clients implement the parts of the AWS APIs the collectors use (pagination with MaxItems,
server-side filters, aggregations) so the test measures what rgtriage actually requests and stores.
"""
import json
import random
import time
from collections import Counter, defaultdict

import pytest

from rgtriage import aws, cli, collect, config, store

ACCOUNT = "111122223333"
REGION = "us-east-1"
SEVERITY_MIX = [("CRITICAL", 0.03), ("HIGH", 0.22), ("MEDIUM", 0.55), ("LOW", 0.20)]


def make_inspector_findings(n=40_000, seed=7):
    rng = random.Random(seed)
    amis = [f"ami-{i:08x}" for i in range(40)]
    repos = [f"svc-{i}" for i in range(30)]
    packages = ["openssl", "glibc", "curl", "zlib", "libxml2", "python3", "nodejs", "log4j-core", "busybox", "sudo"]
    findings = []
    for i in range(n):
        roll, severity = rng.random(), "LOW"
        acc = 0.0
        for label, share in SEVERITY_MIX:
            acc += share
            if roll < acc:
                severity = label
                break
        on_ec2 = rng.random() < 0.6
        package = rng.choice(packages)
        cve = f"CVE-2026-{rng.randrange(1, 900):04d}"
        resource = ({"type": "AWS_EC2_INSTANCE", "id": f"i-{i % 3000:06x}", "region": REGION, "tags": {},
                     "details": {"awsEc2Instance": {"imageId": amis[i % 3000 % len(amis)]}}}
                    if on_ec2 else
                    {"type": "AWS_ECR_CONTAINER_IMAGE", "id": f"arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{repos[i % len(repos)]}/sha256:{i:x}",
                     "region": REGION, "details": {"awsEcrContainerImage": {"repositoryName": repos[i % len(repos)]}}})
        findings.append({
            "findingArn": f"arn:aws:inspector2:{REGION}:{ACCOUNT}:finding/{i:08x}", "awsAccountId": ACCOUNT,
            "title": f"{cve} - {package}", "description": "synthetic", "severity": severity, "status": "ACTIVE",
            "type": "PACKAGE_VULNERABILITY", "exploitAvailable": "YES" if rng.random() < 0.05 else "NO",
            "fixAvailable": "YES", "inspectorScore": round(rng.uniform(1, 10), 1), "epss": {"score": rng.random() / 5},
            "firstObservedAt": "2026-09-01T00:00:00Z", "lastObservedAt": "2026-10-20T00:00:00Z",
            "packageVulnerabilityDetails": {"vulnerabilityId": cve, "vulnerablePackages": [
                {"name": package, "version": "1.0", "fixedInVersion": "1.1", "packageManager": "OS"}]},
            "resources": [resource], "remediation": {"recommendation": {"text": "upgrade"}},
        })
    return findings


class Pages:
    """Botocore-style page iterator with MaxItems and resume_token."""

    def __init__(self, items, key, max_items, page_size, calls):
        self.items, self.key, self.max_items, self.page_size, self.calls = items, key, max_items, page_size, calls
        self.resume_token = None

    def __iter__(self):
        served = 0
        for start in range(0, len(self.items), self.page_size):
            room = self.max_items - served
            if room <= 0:
                self.resume_token = "more"
                return
            chunk = self.items[start:start + min(self.page_size, room)]
            self.calls.append(len(chunk))
            served += len(chunk)
            yield {self.key: chunk}
            if served >= self.max_items and start + len(chunk) < len(self.items):
                self.resume_token = "more"
                return


class FakeInspector:
    def __init__(self, findings):
        self.findings = findings
        self.calls = defaultdict(list)

    def batch_get_account_status(self):
        return {"accounts": [{"state": {"status": "ENABLED"}}]}

    def get_paginator(self, op):
        fake = self

        class P:
            def paginate(self, PaginationConfig, **params):
                return Pages(*fake._run(op, params), PaginationConfig["MaxItems"], 100, fake.calls[op])
        return P()

    @staticmethod
    def _counts(items):
        c = Counter(f["severity"] for f in items)
        return {"all": len(items), "critical": c["CRITICAL"], "high": c["HIGH"], "medium": c["MEDIUM"]}

    def _run(self, op, params):
        if op == "list_findings":
            crit = params["filterCriteria"]
            sev = {x["value"] for x in crit.get("severity", [])}
            exploit = {x["value"] for x in crit.get("exploitAvailable", [])}
            rows = [f for f in self.findings if (not sev or f["severity"] in sev)
                    and (not exploit or f["exploitAvailable"] in exploit)]
            rows.sort(key=lambda f: -f["inspectorScore"])
            return rows, "findings"
        kind = params["aggregationType"]
        groups = defaultdict(list)
        for f in self.findings:
            res = f["resources"][0]
            key = {"ACCOUNT": ACCOUNT,
                   "AMI": res.get("details", {}).get("awsEc2Instance", {}).get("imageId"),
                   "REPOSITORY": res.get("details", {}).get("awsEcrContainerImage", {}).get("repositoryName"),
                   "AWS_LAMBDA_FUNCTION": None,
                   "PACKAGE": f["packageVulnerabilityDetails"]["vulnerablePackages"][0]["name"],
                   "TITLE": f["packageVulnerabilityDetails"]["vulnerabilityId"]}[kind]
            if key:
                groups[key].append(f)
        rows = []
        for key, items in groups.items():
            c = self._counts(items)
            body = {"ACCOUNT": {"accountAggregation": {"accountId": ACCOUNT, "severityCounts": c}},
                    "AMI": {"amiAggregation": {"ami": key, "accountId": ACCOUNT, "severityCounts": c,
                                               "affectedInstances": len({i["resources"][0]["id"] for i in items})}},
                    "REPOSITORY": {"repositoryAggregation": {"repository": key, "accountId": ACCOUNT, "severityCounts": c,
                                                             "affectedImages": len(items)}},
                    "PACKAGE": {"packageAggregation": {"packageName": key, "severityCounts": c}},
                    "TITLE": {"titleAggregation": {"vulnerabilityId": key, "title": key, "severityCounts": c}}}[kind]
            rows.append((c["critical"], body))
        rows.sort(key=lambda r: -r[0])
        return [b for _, b in rows], "responses"


class FakeSecurityHub:
    """Security Hub that also holds a copy of every Inspector finding, like a real integration."""

    def __init__(self, inspector_findings, own=3000):
        self.rows = []
        for i in range(own):
            label = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")[i % 5]
            self.rows.append(self._asff(f"sh-{i}", "Security Hub", label, f"S3.{i % 20}"))
        for f in inspector_findings:
            self.rows.append(self._asff(f["findingArn"], "Inspector", f["severity"], ""))
        self.requested = []
        self.calls = []

    @staticmethod
    def _asff(fid, product, label, control):
        return {"Id": fid, "ProductName": product, "AwsAccountId": ACCOUNT, "Region": REGION, "Title": f"{control} {fid}",
                "Severity": {"Label": label}, "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
                "Compliance": {"Status": "FAILED", "SecurityControlId": control},
                "Resources": [{"Type": "AwsS3Bucket", "Id": f"arn:aws:s3:::b{fid}", "Region": REGION}],
                "Workflow": {"Status": "NEW"}, "UpdatedAt": "2026-10-20T00:00:00Z"}

    def describe_hub(self):
        return {}

    def list_finding_aggregators(self):
        return {"FindingAggregators": []}

    def get_paginator(self, op):
        hub = self

        class P:
            def paginate(self, PaginationConfig, Filters, **_):
                hub.requested.append(Filters)
                excluded = {x["Value"] for x in Filters.get("ProductName", []) if x["Comparison"] == "NOT_EQUALS"}
                label = Filters["SeverityLabel"][0]["Value"]
                rows = [r for r in hub.rows if r["ProductName"] not in excluded and r["Severity"]["Label"] == label]
                return Pages(rows, "Findings", PaginationConfig["MaxItems"], 100, hub.calls)
        return P()


class FakeSession:
    def client(self, service, **_):
        class STS:
            def get_caller_identity(self):
                return {"Account": ACCOUNT}
        return STS()


@pytest.fixture(scope="module")
def estate():
    return make_inspector_findings()


@pytest.fixture
def fakes(estate, monkeypatch, tmp_path):
    monkeypatch.setenv("RGTRIAGE_HOME", str(tmp_path))
    inspector, hub = FakeInspector(estate), FakeSecurityHub(estate)
    monkeypatch.setattr(aws, "session_for", lambda account, region=None: FakeSession())
    monkeypatch.setattr(aws, "client", lambda session, service, region: {"inspector2": inspector, "securityhub": hub}[service])
    (tmp_path / "triage.yaml").write_text(
        f"name: scale\naccounts: [{{name: prod, account_id: '{ACCOUNT}'}}]\nsources: [inspector, securityhub]\n")
    return inspector, hub, tmp_path


def test_inspector_40k_is_counted_fully_but_read_selectively(fakes, estate):
    inspector, _, _ = fakes
    profile = config.load()
    findings, meta = collect.collect_inspector(None, profile["accounts"][0] | {"account_id": ACCOUNT}, REGION,
                                               {"detail_limits": profile["detail_limits"], "rollup_limit": 25})
    expected = Counter(f["severity"] for f in estate)
    assert meta["total"] == 40_000
    assert meta["counts"]["CRITICAL"] == expected["CRITICAL"] and meta["counts"]["HIGH"] == expected["HIGH"]
    detailed = [f for f in findings if not f["signals"].get("rollup")]
    exploitable_medium = sum(1 for f in estate if f["severity"] == "MEDIUM" and f["exploitAvailable"] == "YES")
    assert len(detailed) == meta["detailed"] <= 1000 + 1000 + min(300, exploitable_medium)
    assert meta["truncated"]  # HIGH (~8,800) exceeds the 1,000 cap and says so
    assert sum(inspector.calls["list_findings"]) == len(detailed)  # no finding fetched and thrown away
    rollups = [f for f in findings if f["signals"].get("rollup")]
    assert {f["type"] for f in rollups} == {"InspectorRollup/AMI", "InspectorRollup/REPOSITORY"}
    assert len([f for f in rollups if f["type"] == "InspectorRollup/AMI"]) == 25  # top fix units by critical count
    truth = Counter(f["resources"][0]["details"]["awsEc2Instance"]["imageId"] for f in estate
                    if f["resources"][0]["type"] == "AWS_EC2_INSTANCE")
    top = max((f for f in rollups if f["type"] == "InspectorRollup/AMI"), key=lambda f: f["signals"]["critical_count"])
    assert top["signals"]["fleet_findings"] == truth[top["resource"]["id"]]
    assert meta["top_packages"][0]["package"]


def test_full_scan_excludes_inspector_from_security_hub_and_bounds_storage(fakes):
    inspector, hub, home = fakes
    started = time.perf_counter()
    cli.main(["scan", "--quiet"])
    elapsed = time.perf_counter() - started
    scan = store.load_latest()
    hub_reads = sum(hub.calls)
    assert all(any(x["Value"] == "Inspector" for x in f.get("ProductName", [])) for f in hub.requested)
    assert hub_reads <= 600 + 600 + 600 + 100  # Security Hub's own 3,000, tiered; no Inspector copies
    assert not any(f["product"] == "Inspector" and f["source"] == "securityhub" for f in scan["findings"])
    latest_mb = (home / "latest.json").stat().st_size / 1e6
    history = list((home / "history").glob("*.json"))
    assert latest_mb < 15 and history[0].stat().st_size < 400_000
    assert (home / "board.md").stat().st_size < 8_000  # what the agent sees at session start stays small
    board = (home / "digest.md").read_text(encoding="utf-8")
    assert "40,000 open findings" in board and "summarized by AMI" in board
    assert elapsed < 30, f"scan took {elapsed:.1f}s"
    print(f"\nscale: {elapsed:.1f}s, stored {len(scan['findings'])} findings, latest.json {latest_mb:.1f} MB, "
          f"inspector detail calls {len(inspector.calls['list_findings'])}, hub pages {len(hub.calls)}")


def test_enabling_inspector_is_a_baseline_not_40k_new_alerts(fakes, monkeypatch, capsys):
    _, _, home = fakes
    (home / "triage.yaml").write_text(
        f"name: scale\naccounts: [{{name: prod, account_id: '{ACCOUNT}'}}]\nsources: [securityhub]\n")
    cli.main(["scan", "--quiet"])  # before Inspector is onboarded
    (home / "triage.yaml").write_text(
        f"name: scale\naccounts: [{{name: prod, account_id: '{ACCOUNT}'}}]\nsources: [inspector, securityhub]\n")
    cli.main(["watch"])
    out = capsys.readouterr().out
    scan = store.load_latest()
    assert scan["changes"]["new"] == 0
    assert scan["changes"]["new_sources"][0]["source"] == "inspector"
    assert out == ""  # no alert storm
    assert "Newly readable: inspector" in (home / "digest.md").read_text(encoding="utf-8")


def test_capped_source_does_not_report_false_resolutions(fakes):
    _, hub, _ = fakes
    cli.main(["scan", "--quiet"])
    hub.rows.reverse()  # a different subset falls inside the caps next time
    cli.main(["scan", "--quiet"])
    changes = store.load_latest()["changes"]
    assert changes["no_longer_active_count"] == 0 and changes["new"] == 0


def test_agent_facing_outputs_stay_bounded(fakes, capsys):
    cli.main(["scan", "--quiet"])
    cli.main(["list", "--priority", "P1,P2"])
    listed = capsys.readouterr().out
    assert len(listed.splitlines()) <= 31
    cli.main(["list", "--issues", "--json", "--limit", "20"])
    issues = json.loads(capsys.readouterr().out)
    assert len(issues) == 20 and all(len(i["finding_keys"]) <= 50 for i in issues)
    ami = next(i for i in store.load_latest()["issues"] if i["type"] == "InspectorRollup/AMI")
    assert "open vulnerabilities" in ami["title"] and any("one fix clears" in r for r in ami["reasons"])
