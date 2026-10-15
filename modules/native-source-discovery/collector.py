"""Fixed-scope AWS availability inventory. No model, telemetry query or cloud changes."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

CONFIG = Config(retries={"total_max_attempts": 1}, connect_timeout=3, read_timeout=6)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def classify(service, response):
    if service == "securitylake":
        return "available" if response.get("dataLakes") else "not_enabled"
    if service == "guardduty":
        return "available" if response.get("DetectorIds") else "not_enabled"
    if service == "cloudtrail":
        return "available" if response.get("trailList") else "unknown"
    if service == "config":
        return "available" if response.get("ConfigurationRecorders") else "not_enabled"
    if service == "inspector2":
        accounts = response.get("accounts", [])
        states = [x.get("state", {}).get("status") for x in accounts]
        return "available" if "ENABLED" in states else "not_enabled" if states and all(s == "DISABLED" for s in states) else "unknown"
    return "available"


def handler(event, context):
    if event not in ({}, {"action": "discover"}, {"action": "collect_securityhub"}):
        raise ValueError("Only fixed-scope discovery is supported")
    region, account = os.environ["REGION"], os.environ["ACCOUNT_ID"]
    bucket, prefix = os.environ["BUCKET"], os.environ["PREFIX"].strip("/")
    run = uuid.uuid4().hex
    observed = datetime.now(timezone.utc).isoformat()
    s3 = boto3.client("s3", region_name=region, config=CONFIG)
    files, sources = [], []

    def save(path, value, layer):
        body = encode(value)
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{path}", Body=body,
                      ContentType="application/json", IfNoneMatch="*")
        files.append({"path": path, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "layer": layer})

    calls = [
        ("securitylake", "list_data_lakes", {"regions": [region]}),
        ("securityhub", "describe_hub", {}),
        ("guardduty", "list_detectors", {"MaxResults": 50}),
        ("inspector2", "batch_get_account_status", {"accountIds": [account]}),
        ("config", "describe_configuration_recorders", {}),
        ("cloudtrail", "describe_trails", {"includeShadowTrails": False}),
    ]
    if event.get("action") == "collect_securityhub":
        calls.append(("securityhub", "get_findings", {
            "Filters": {"AwsAccountId": [{"Value": account, "Comparison": "EQUALS"}],
                        "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}]},
            "SortCriteria": [{"Field": "UpdatedAt", "SortOrder": "desc"}], "MaxResults": 20}))
    for service, method, args in calls:
        source_id = "securityhub_findings" if method == "get_findings" else service
        raw = {"source": service, "api": method, "arguments": args, "observed_at": observed, "account_id": account, "region": region}
        try:
            response = getattr(boto3.client(service, region_name=region, config=CONFIG), method)(**args)
            raw["response"] = response
            status = classify(service, response)
            reason = "Service metadata only; availability does not establish coverage or access to records."
            if response.get("NextToken") or response.get("nextToken"):
                status, reason = "unknown", "Partial first page; continuation was not queried."
        except ClientError as exc:
            raw["error"] = exc.response
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            status = "access_denied" if "AccessDenied" in code or "Unauthorized" in code else "unknown"
            reason = code
        except Exception as exc:
            status, reason = "unknown", type(exc).__name__
            raw["error"] = {"type": reason}
        path = f"raw/{run}/{source_id}.json"
        save(path, raw, "raw")
        sources.append({"id": source_id, "status": status, "reason": reason, "raw_path": path})
        if method == "get_findings" and "response" in raw:
            findings = raw["response"].get("Findings", [])
            counts = {}
            normalized = []
            for finding in findings:
                severity = finding.get("Severity", {}).get("Label", "UNKNOWN")
                counts[severity] = counts.get(severity, 0) + 1
                normalized.append({"id": finding.get("Id"), "title": finding.get("Title"), "severity": severity,
                    "updated_at": finding.get("UpdatedAt"), "workflow": finding.get("Workflow", {}).get("Status"),
                    "compliance": finding.get("Compliance", {}).get("Status"),
                    "resources": [{"id": r.get("Id"), "type": r.get("Type"), "region": r.get("Region")} for r in finding.get("Resources", [])],
                    "raw_path": path})
            save(f"normalized/{run}/securityhub-findings.json", {"schema_version": "rgce-securityhub-sample/1",
                "scope": "At most 20 latest-updated ACTIVE findings in this account and region; not a complete assessment",
                "returned_count": len(findings), "severity_counts": counts,
                "has_more": bool(raw["response"].get("NextToken")), "findings": normalized}, "normalized")
    save(f"normalized/{run}/sources.json", {"schema_version": "rgce-source-availability/1", "sources": sources}, "normalized")
    receipt = f"receipts/{run}.json"
    save(receipt, {"run_id": run, "observed_at": observed, "producer": "deterministic-python", "python_runtime": "3.12", "boto3_version": boto3.__version__, "collector_sha256": hashlib.sha256(open(__file__, "rb").read()).hexdigest(), "files": list(files)}, "receipts")
    sampled = event.get("action") == "collect_securityhub"
    catalog = {"schema_version": "rgce-source-catalog/1", "run_id": run, "observed_at": observed, "account_id": account, "region": region, "scope": "service availability and bounded Security Hub sample" if sampled else "service availability only", "sources": sources, "files": files, "receipt_path": receipt, "limitations": ["Single account and region; at most 20 ACTIVE Security Hub findings, no event bodies." if sampled else "Single account and region; no finding or event contents collected.", "Availability is not coverage, protection, successful recording, or permission to query.", "Unknown and access denied never mean secure or absent.", "No organization knowledge has been supplied."]}
    s3.put_object(Bucket=bucket, Key=f"{prefix}/catalog.json", Body=encode(catalog), ContentType="application/json")
    return {"run_id": run, "catalog_key": f"{prefix}/catalog.json", "sources": sources}
