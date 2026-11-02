"""Failure contracts at the managed transport boundary, without live AWS."""
import ast
import json
from types import SimpleNamespace

import boto3
import pytest

from rgtriage import aws, aws_mcp, config


@pytest.fixture
def iam():
    return boto3.client("iam", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")


@pytest.mark.parametrize("operation", ["create_role", "get_credential_report", "get_login_profile", "not_real"])
def test_rejected_before_transport(iam, operation):
    with pytest.raises(aws.WriteBlocked):
        aws_mcp.build_read(iam, operation, {}, "us-east-1")


def test_parameters_are_data_and_sdk_validated(iam):
    value = "x'); print('injected') #"
    name, code = aws_mcp.build_read(iam, "get_role", {"RoleName": value}, "us-east-1")
    tree = ast.parse(code)
    serialized = tree.body[0].value.value.keywords[0].value.args[0].value
    assert json.loads(serialized)["params"]["RoleName"] == value
    assert name == "GetRole"
    from botocore.exceptions import ParamValidationError
    with pytest.raises(ParamValidationError):
        aws_mcp.build_read(iam, "get_role", {"Typo": "x"}, "us-east-1")


def response(payload, error=False):
    return SimpleNamespace(isError=error, structuredContent=payload, content=[])


def successful():
    return {"status": "success", "return_value": {"Role": {"RoleName": "test"}},
            "api_calls": [{"service": "iam", "operation": "GetRole", "status": "success"}]}


def test_requires_positive_matching_api_evidence():
    payload = successful()
    assert aws_mcp.parse_result(response(payload), "iam", "GetRole")["Role"]["RoleName"] == "test"
    for changes in ({"status": "error"}, {"status": "working"}, {"api_calls": []},
                    {"warning": "partial"}, {"return_value": None},
                    {"api_calls": [{"service": "iam", "operation": "CreateRole", "status": "success"}]}):
        with pytest.raises(aws_mcp.ManagedMCPError):
            aws_mcp.parse_result(response({**payload, **changes}), "iam", "GetRole")
    with pytest.raises(aws_mcp.ManagedMCPError):
        aws_mcp.parse_result(response(payload, error=True), "iam", "GetRole")


def test_failed_payload_does_not_echo_private_error():
    with pytest.raises(aws_mcp.ManagedMCPError) as exc:
        aws_mcp.parse_result(response({"status": "error", "error": "PRIVATE"}), "iam", "GetRole")
    assert "PRIVATE" not in str(exc.value)


def test_endpoint_cannot_be_redirected(iam):
    with pytest.raises(ValueError, match="endpoint"):
        aws_mcp.read(None, iam, "get_role", {"RoleName": "test"}, "us-east-1", {"endpoint_region": "attacker.test"})
    with pytest.raises(ValueError, match="transport"):
        config.normalize({"aws_investigation": {"transport": "typo"}})


def test_transport_failure_never_replays_direct(iam, monkeypatch):
    async def fail(*args):
        raise TimeoutError("PRIVATE")
    monkeypatch.setattr(aws_mcp, "_request", fail)
    with pytest.raises(aws_mcp.ManagedMCPError, match="unavailable") as exc:
        aws_mcp.read(None, iam, "get_role", {"RoleName": "test"}, "us-east-1", {})
    assert "PRIVATE" not in str(exc.value)
