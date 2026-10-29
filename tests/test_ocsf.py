"""OCSF 1.9.0 mapping and lossless exposure passthrough (roadmap CE-24)."""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from rgtriage import collect, contracts, ocsf

NOW = "2026-06-15T10:00:00Z"
SCOPE = contracts.Scope(account="111122223333", region="us-east-1", source="inspector")


def contract_event(scope: contracts.Scope = SCOPE, observed_at: str = NOW, sequence: int = 1) -> contracts.Event:
    payload_hash = contracts.payload_hash({"event": "test"})
    return contracts.Event(
        event_id=contracts.observation_event_id("installation-1", scope, observed_at, payload_hash),
        kind="observation", installation_id="installation-1", epoch="epoch-1", sequence=sequence, scope=scope,
        observed_at=observed_at, ingested_at=observed_at, payload_hash=payload_hash)


def raw_ref(scope: contracts.Scope = SCOPE) -> contracts.RawRef:
    body = b'{"Findings":[]}'
    sha = contracts.bytes_sha256(body)
    return contracts.RawRef(sha256=sha, key=contracts.raw_key(scope, NOW, sha), size=len(body), scope=scope,
                            operation="ListFindings", observed_at=NOW)


def base(source: str, **fields) -> dict:
    finding = {
        "key": "abc123def456", "source": source, "native_id": "native-1", "product": source,
        "account": "111122223333", "region": "us-east-1", "title": "Finding title",
        "description": "Finding description", "severity": "HIGH", "category": "posture", "type": "",
        "control_id": "", "resource": {"type": "AwsS3Bucket", "id": "arn:aws:s3:::bucket",
                                       "name": "bucket", "tags": {"env": "prod"}},
        "first_seen": "2026-06-15T09:00:00Z", "last_seen": "2026-06-15T09:30:00Z", "workflow": "NEW",
        "remediation": {"text": "", "url": ""}, "console_url": "", "signals": {}, "context": {},
    }
    finding.update(fields)
    return finding


def inspector() -> dict:
    return base("inspector", category="vulnerability", type="PACKAGE_VULNERABILITY", control_id="CVE-2024-1234",
                signals={"exploit_available": True, "epss": 0.72, "fix_available": True},
                context={"packages": [{"name": "openssl", "installed": "1.0.1", "manager": "OS"}]})


def exposure() -> dict:
    original = {
        "class_uid": 2004, "category_uid": 2, "class_name": "Detection Finding", "activity_id": 1,
        "type_uid": 200401, "time": 1781600000000, "severity_id": 4, "status_id": 1,
        "metadata": {"version": "1.9.0", "product": {"name": "Security Hub exposure", "vendor_name": "Amazon Web Services"}},
        "finding_info": {"uid": "aws-exposure-1", "title": "Public bucket with credentials"},
        "cloud": {"provider": "AWS", "region": "us-east-1", "account_uid": "111122223333"},
        "resources": [{"uid": "arn:aws:s3:::bucket", "type": "AwsS3Bucket", "name": "bucket"}],
        "attack_path": {"hop": ["internet", "bucket"]},
        "aws_traits": ["data_exposure"],
    }
    return base("securityhub-exposure", native_id="aws-exposure-1", product="Security Hub exposure",
                category="exposure", type="Exposure", signals={"aws_exposure": True}, ocsf=original)


def test_reviewed_mapping_table():
    assert ocsf.class_for(base("inspector")) == ocsf.CLASS_VULNERABILITY_FINDING
    assert ocsf.class_for(base("guardduty", category="threat")) == ocsf.CLASS_DETECTION_FINDING
    assert ocsf.class_for(base("accessanalyzer", category="exposure")) == ocsf.CLASS_DETECTION_FINDING
    assert ocsf.class_for(base("config")) == ocsf.CLASS_COMPLIANCE_FINDING
    assert ocsf.class_for(base("securityhub", category="posture")) == ocsf.CLASS_COMPLIANCE_FINDING
    assert ocsf.class_for(base("securityhub", category="threat")) == ocsf.CLASS_DETECTION_FINDING
    assert ocsf.class_for(base("securityhub", category="vulnerability")) == ocsf.CLASS_VULNERABILITY_FINDING
    assert ocsf.class_for(base("something-new")) == ocsf.CLASS_FINDING


def test_mapped_record_passes_the_pinned_subset():
    record = ocsf.map_finding(inspector())
    assert record["metadata"]["version"] == ocsf.OCSF_VERSION == "1.9.0"
    assert record["category_uid"] == 2
    assert record["class_uid"] == 2002
    assert record["class_name"] == "Vulnerability Finding"
    assert record["type_uid"] == 200200
    assert record["severity_id"] == 4
    assert record["status_id"] == 1
    assert record["finding_info"]["uid"] == "native-1"
    assert record["resources"][0]["tags"] == {"env": "prod"}
    assert ocsf.validate_mapped(record) == []
    schema = json.loads((contracts.schema_path("") / "ocsf-1.9.0-findings.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(record)


def test_vulnerability_compliance_and_residual_fields():
    vuln = ocsf.map_finding(inspector())
    assert vuln["vulnerabilities"][0]["cve_uid"] == "CVE-2024-1234"
    assert vuln["vulnerabilities"][0]["package_name"] == "openssl"
    assert vuln["vulnerabilities"][0]["is_exploit_available"] is True
    assert vuln["compliance"] is None
    compliance = ocsf.map_finding(base("config", control_id="config-1", context={"standards": ["cis"]}))
    assert compliance["compliance"]["status_id"] == ocsf.COMPLIANCE_FAIL
    assert compliance["compliance"]["control"] == "config-1"
    assert compliance["compliance"]["standards"] == ["cis"]
    unknown = ocsf.map_finding(base("inspector", surprise={"new_field": "kept"}))
    assert unknown["unmapped"]["fields"]["surprise"] == {"new_field": "kept"}
    assert "surprise" in unknown["unmapped"]["source_keys"]


def test_resource_details_are_json_text_not_a_nested_dict():
    record = ocsf.map_finding(base("inspector", resource={"type": "AwsS3Bucket", "id": "arn:aws:s3:::bucket",
                                                          "name": "bucket", "details": {"policy": {"public": True}}}))
    assert isinstance(record["resources"][0]["data"], str)
    assert '"public":true' in record["resources"][0]["data"]


def test_unknown_source_falls_back_instead_of_guessing():
    record = ocsf.map_finding(base("brand-new-source"))
    assert record["class_uid"] == ocsf.CLASS_FINDING
    assert record["unmapped"]["ce"]["mapping"] == "fallback"
    assert "no reviewed OCSF class" in record["unmapped"]["ce"]["mapping_error"]
    assert ocsf.validate_mapped(record) == []


def test_exposure_is_passthrough_with_every_aws_field():
    record = ocsf.map_finding(exposure())
    assert record["attack_path"] == {"hop": ["internet", "bucket"]}
    assert record["aws_traits"] == ["data_exposure"]
    assert record["metadata"]["product"]["name"] == "Security Hub exposure"
    assert record["unmapped"]["ce"]["mapping"] == "passthrough"
    assert ocsf.validate_mapped(record) == []
    without = exposure()
    without.pop("ocsf")
    with pytest.raises(ocsf.MappingError):
        ocsf.map_finding(without)


def test_normalize_exposure_keeps_the_original_ocsf_record():
    original = exposure()["ocsf"]
    raw = {"finding_info": original["finding_info"], "cloud": original["cloud"],
           "resources": original["resources"], "severity_id": 4, "class_uid": 2004, "status": "ACTIVE",
           "attack_path": original["attack_path"]}
    finding = collect.normalize_exposure(raw, "us-east-1")
    assert finding["ocsf"]["attack_path"] == {"hop": ["internet", "bucket"]}
    assert finding["signals"]["aws_exposure"] is True


def test_finding_row_links_raw_evidence_and_matches_the_iceberg_shape():
    finding = inspector()
    event = contract_event()
    ref = raw_ref()
    row = ocsf.finding_row(finding, event, ref)
    assert row["event_id"] == event.event_id
    assert row["raw_sha256"] == ref.sha256 and row["raw_key"] == ref.key
    assert row["account_id"] == "111122223333" and row["region"] == "us-east-1"
    assert row["class_uid"] == 2002
    assert str(row["event_day"]) == "2026-06-15"
    assert row["ce"]["mapping"] == "native"
    assert isinstance(row["ocsf"]["unmapped"], str)
    restored = dict(row["ocsf"], unmapped=json.loads(row["ocsf"]["unmapped"]))
    schema = json.loads((contracts.schema_path("") / "ocsf-1.9.0-findings.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(restored)


def test_signals_do_not_enter_the_findings_table():
    signal = base("cloudwatch", type="CloudWatchAlarm", category="posture")
    event = contract_event(contracts.Scope(account="111122223333", region="us-east-1", source="cloudwatch"))
    table, row = ocsf.row_for(signal, event, raw_ref())
    assert table == "signals"
    assert row["source"] == "cloudwatch" and row["signal_type"] == "CloudWatchAlarm"
    assert "class_uid" not in row
    table, row = ocsf.row_for(inspector(), contract_event(), raw_ref())
    assert table == "findings"


def test_validation_reports_every_problem():
    record = ocsf.map_finding(inspector())
    record["metadata"]["version"] = "1.8.0"
    record["category_uid"] = 1
    record["severity_id"] = 42
    record["finding_info"]["uid"] = ""
    problems = ocsf.validate_mapped(record)
    assert any("version" in p for p in problems)
    assert any("category_uid" in p for p in problems)
    assert any("severity" in p for p in problems)
    assert any("finding_info" in p for p in problems)