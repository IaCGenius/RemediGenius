"""Community edition checks: nothing private leaks in, the read-only role keeps its promises, the seams hold.

    python -m pytest -q tests/test_community.py
"""
import json
import importlib.util
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEXT = {".py", ".md", ".json", ".yaml", ".yml", ".tf", ".sh", ".tftpl", ".txt", ".service", ".timer", ".html", ".js", ".css", ".hcl", ""}
SKIP = {".git", ".terraform", "build", "__pycache__", ".pytest_cache", ".venv", ".rgce", "dist", "playwright-output"}


def repo_files():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            p = Path(folder) / name
            if p.suffix in TEXT :
                yield p


# Check for credential shapes and optional private maintainer identifiers.
# Maintainer-specific identifiers belong in an ignored local file, never the release.
PRIVATE = [r"AKIA[A-Z0-9]{16}", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
           r"ghp_[A-Za-z0-9]{36}"]
private_patterns = ROOT / ".rgce" / "private-patterns.json"
if private_patterns.exists():
    PRIVATE += json.loads(private_patterns.read_text(encoding="utf-8"))


@pytest.mark.parametrize("pattern", PRIVATE, ids=[f"private-check-{i}" for i in range(len(PRIVATE))])
def test_no_private_identifiers(pattern):
    hits = [f"{p.relative_to(ROOT)}" for p in repo_files() if re.search(pattern, p.read_text(encoding="utf-8", errors="ignore"))]
    assert not hits, f"Private material found in {hits}"


def test_profiles_bring_your_own_model():
    for prof in ("desk", "analyst", "builder"):
        cfg = (ROOT / "profiles" / prof / "config.yaml").read_text(encoding="utf-8")
        assert "default: __MODEL_NAME__" in cfg and "base_url: __MODEL_BASE_URL__" in cfg, prof
        assert "key_env: MODEL_API_KEY" in cfg, prof
        dist = (ROOT / "profiles" / prof / "distribution.yaml").read_text(encoding="utf-8")
        assert 'license: "Apache-2.0"' in dist and "MODEL_API_KEY" in dist, prof
    assert "__KIOSK_NAME__" in (ROOT / "profiles/builder/kiosk.json").read_text(encoding="utf-8")


def role_template():
    return (ROOT / "onboarding/aws/readonly-role.yaml").read_text(encoding="utf-8")


def test_role_trust_needs_external_id_and_the_engine_role():
    t = role_template()
    assert "sts:ExternalId: !Ref ExternalId" in t
    assert "aws:PrincipalArn: !Ref TrustedRoleArn" in t
    assert "MaxSessionDuration: 3600" in t


def test_role_only_reads_and_denies_data():
    t = role_template()
    assert t.count("Effect: Allow") == 1, "only the trust statement may allow"
    assert "Effect: Deny" in t
    actions = re.findall(r"^\s+- ([a-z0-9-]+:[A-Za-z*]+)\s*$", t, re.M)
    assert len(actions) >= 160
    for must in ("s3:GetObject*", "s3:ListBucket", "secretsmanager:GetSecretValue", "kms:Decrypt", "dynamodb:Scan",
                 "logs:GetLogEvents", "lambda:GetFunction", "ssm:GetParameter*"):
        assert must in actions, must
    managed = re.findall(r"iam::aws:policy/([A-Za-z/-]+)", t)
    assert sorted(managed) == ["SecurityAudit", "job-function/ViewOnlyAccess"]


def test_host_may_assume_exactly_the_template_role_name():
    tf = (ROOT / "deploy/aws/variables.tf").read_text(encoding="utf-8")
    default = re.search(r'variable "readonly_role_name" \{.*?default\s*=\s*"([^"]+)"', tf, re.S).group(1)
    assert f"Default: {default}" in role_template()
    engine = (ROOT / "deploy/aws/engine.tf").read_text(encoding="utf-8")
    assert 'role/${var.readonly_role_name}"' in engine


def test_skillresult_provider_and_fix_ids():
    spec = importlib.util.spec_from_file_location(
        "skillresult", ROOT / "profiles/analyst/skills/remedigenius/skillresult/scripts/skillresult.py")
    sr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sr)
    rule = {"id": "BKTPUB-002", "severity": "high", "fix": "FIX-S3PUB-01"}
    f = sr.finding(rule, "arn:aws:s3:::b", "global", {"why": "x"})
    ok = sr.envelope("s3-public-access", "A3", "global", [], {}, [f])
    assert ok["provider"] == "aws" and f["fix_id"] == "FIX-S3PUB-01" and sr.validate(ok) == []
    assert sr.validate({**ok, "provider": "oci"}) == ["provider not in aws/azure/gcp"]
    assert any("fix_id" in e for e in sr.validate({**ok, "findings": [{**f, "fix_id": "X"}]}))


def test_agents_never_get_aws_credentials():
    boot = (ROOT / "deploy/aws/host/boot.sh").read_text(encoding="utf-8")
    assert "iptables -I DOCKER-USER -d 169.254.169.254 -j DROP" in boot
    engine = (ROOT / "deploy/aws/engine.tf").read_text(encoding="utf-8")
    assert "http_put_response_hop_limit = 1" in engine and 'http_tokens                 = "required"' in engine
    unit = (ROOT / "deploy/aws/host/rg-hermes.service").read_text(encoding="utf-8")
    assert "--network host" not in unit and "-p 127.0.0.1:" in unit


def test_no_inbound_rules():
    net = (ROOT / "deploy/aws/network.tf").read_text(encoding="utf-8")
    assert "aws_vpc_security_group_ingress_rule" not in net and "ingress" not in net
