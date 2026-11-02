"""Optional managed AWS MCP transport for the desk's structured AWS reads.

No model-provided Python, endpoint or credentials cross this boundary. AWS's
official transport signs requests; the existing desk remains the policy gate.
"""
from __future__ import annotations

import asyncio
import json
import re

from botocore.validate import validate_parameters

from . import aws

REGIONS = frozenset({"us-east-1", "us-west-2", "ap-southeast-1", "ap-southeast-2",
                     "ap-northeast-1", "eu-central-1", "eu-west-1", "eu-west-2"})
REFUSED = {"AssumeRole", "AssumeRoleWithSAML", "AssumeRoleWithWebIdentity",
           "GetSessionToken", "GetFederationToken"}


class ManagedMCPError(RuntimeError):
    """No verified account evidence was obtained; never silently switch transports."""


def build_read(client, operation: str, params: dict, region: str) -> tuple[str, str]:
    """Resolve an actual SDK operation and serialize values as data, never code."""
    names = client.meta.method_to_api_mapping
    name = names.get(operation)
    if not name or name in REFUSED or not aws.is_read_operation(name):
        raise aws.WriteBlocked("Managed MCP refused an unknown, mutating or sensitive operation")
    if not isinstance(params, dict):
        raise ValueError("AWS parameters must be an object")
    model = client.meta.service_model.operation_model(name)
    validate_parameters(params, model.input_shape)
    service = client.meta.service_model.service_name
    values = json.dumps(dict(service_name=service, operation_name=name,
                             region_name=region, params=params), allow_nan=False)
    # repr quotes the JSON document, including quotes/newlines supplied in params.
    return name, f"result = await call_boto3(**json.loads({values!r}))\nresult"


def parse_result(response, service: str, operation: str) -> dict:
    if response.isError:
        raise ManagedMCPError("AWS MCP tool failed; no account evidence returned")
    payload = response.structuredContent
    if payload is None:
        try:
            texts = [c.text for c in response.content if c.type == "text"]
            payload = json.loads(texts[0]) if len(texts) == 1 else None
        except (ValueError, AttributeError):
            payload = None
    if not isinstance(payload, dict) or payload.get("status") != "success":
        # Do not echo vendor exceptions: they can contain source code or private payloads.
        detail = str(payload.get("error", "")) if isinstance(payload, dict) else ""
        for markers, advice in (
            (("ExpiredToken", "InvalidClientTokenId", "UnrecognizedClient"), "refresh the source AWS session"),
            (("AccessDenied", "UnauthorizedOperation"), "check the selected audit role and organization restrictions"),
            (("Throttl", "TooManyRequests"), "retry a narrower read after throttling subsides"),
        ):
            if any(marker in detail for marker in markers):
                raise ManagedMCPError(f"AWS MCP returned no verified evidence; {advice}")
        status = payload.get("status", "invalid response") if isinstance(payload, dict) else "invalid response"
        safe_status = status if status in {"error", "working", "pending", "running"} else "invalid response"
        raise ManagedMCPError(f"AWS MCP returned {safe_status}; no verified evidence. Check access/session or retry later")
    calls = payload.get("api_calls")
    if not isinstance(calls, list) or not calls or any(
        c.get("service") != service or c.get("operation") != operation or c.get("status") != "success"
        for c in calls if isinstance(c, dict)
    ) or any(not isinstance(c, dict) for c in calls):
        raise ManagedMCPError("AWS MCP did not confirm the requested API succeeded")
    if payload.get("warning") or payload.get("stderr"):
        raise ManagedMCPError("AWS MCP reported a warning or partial failure; evidence withheld")
    result = payload.get("return_value")
    if not isinstance(result, dict):
        raise ManagedMCPError("AWS MCP returned no structured AWS result")
    return result


async def _request(session, code: str, service: str, operation: str, endpoint_region: str) -> dict:
    try:
        from botocore.credentials import Credentials
        from mcp import ClientSession
        from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
    except ImportError as exc:
        raise ManagedMCPError("Install the optional aws-mcp dependencies in the desk runtime first") from exc
    frozen = session.get_credentials().get_frozen_credentials()
    credentials = Credentials(frozen.access_key, frozen.secret_key, frozen.token)
    endpoint = f"https://aws-mcp.{endpoint_region}.api.aws/mcp"
    async with aws_iam_streamablehttp_client(
        endpoint, aws_service="aws-mcp", aws_region=endpoint_region, credentials=credentials,
        timeout=15, sse_read_timeout=45,
    ) as (reader, writer, _):
        async with ClientSession(reader, writer) as remote:
            await remote.initialize()
            response = await remote.call_tool("aws___run_script", {"code": code})
    # Parse outside transport task groups so semantic errors remain actionable.
    return parse_result(response, service, operation)


def read(session, client, operation: str, params: dict, region: str, settings: dict) -> dict:
    endpoint_region = settings.get("endpoint_region", "us-east-1")
    if endpoint_region not in REGIONS:
        raise ValueError("Unsupported managed AWS MCP endpoint region")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", region):
        raise ValueError("Invalid AWS target region")
    name, code = build_read(client, operation, params, region)

    async def bounded():
        return await asyncio.wait_for(_request(session, code, client.meta.service_model.service_name,
                                               name, endpoint_region), timeout=55)
    try:
        return asyncio.run(bounded())
    except ManagedMCPError:
        raise
    except Exception as exc:
        raise ManagedMCPError("Managed AWS MCP unavailable or unauthorized; no evidence returned. "
                              "Check role, session, endpoint and connectivity; direct collection is unaffected") from exc
