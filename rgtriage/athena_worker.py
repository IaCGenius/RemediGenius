"""Isolated vendor-MCP worker. Only the desk invokes this with compiled report SQL."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path


def unpack(response):
    envelope = response.model_dump(by_alias=True)
    if envelope.get("isError", envelope.get("is_error", False)):
        raise RuntimeError("Vendor MCP rejected the request")
    for item in reversed(envelope.get("content", [])):
        if item.get("type") == "text":
            try:
                value = json.loads(item["text"])
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
    raise RuntimeError("Vendor MCP returned no structured result")


async def execute(request):
    import boto3
    from botocore.config import Config
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    cfg = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 1})
    region = request["region"]
    creds = boto3.client("sts", region_name=region, config=cfg).assume_role(
        RoleArn=request["role_arn"], RoleSessionName="remedigenius-analytics", DurationSeconds=900)["Credentials"]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/nonexistent",
           "AWS_REGION": region, "AWS_DEFAULT_REGION": region, "AWS_EC2_METADATA_DISABLED": "true",
           "AWS_ACCESS_KEY_ID": creds["AccessKeyId"], "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
           "AWS_SESSION_TOKEN": creds["SessionToken"], "FASTMCP_LOG_LEVEL": "ERROR"}
    cancel = boto3.client("athena", region_name=region, config=cfg,
                          aws_access_key_id=creds["AccessKeyId"], aws_secret_access_key=creds["SecretAccessKey"],
                          aws_session_token=creds["SessionToken"])
    executable = str(Path(sys.executable).with_name("awslabs.aws-dataprocessing-mcp-server"))
    params = StdioServerParameters(command=executable, args=["--allow-sensitive-data-access"], env=env)
    query_id = None
    terminal = False
    try:
        async with asyncio.timeout(75):
            with open(os.devnull, "w") as error_log:
                async with stdio_client(params, errlog=error_log) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()

                        async def call(**arguments):
                            return unpack(await session.call_tool("manage_aws_athena_query_executions", arguments))

                        start = await call(operation="start-query-execution", query_string=request["sql"],
                                           query_execution_context={"Database": request["database"], "Catalog": "AwsDataCatalog"},
                                           work_group=request["workgroup"], client_request_token=str(uuid.uuid4()))
                        query_id = start["query_execution_id"]
                        while True:
                            status = await call(operation="get-query-execution", query_execution_id=query_id)
                            execution = status["query_execution"]
                            state = execution["Status"]["State"]
                            if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                                terminal = True
                                break
                            await asyncio.sleep(1)
                        if state != "SUCCEEDED":
                            raise RuntimeError("Athena query did not succeed")
                        rows, columns, token = [], [], None
                        first = True
                        while True:
                            arguments = dict(operation="get-query-results", query_execution_id=query_id, max_results=100)
                            if token:
                                arguments["next_token"] = token
                            page = await call(**arguments)
                            result = page["result_set"]
                            columns = [c["Name"] for c in result["ResultSetMetadata"]["ColumnInfo"]]
                            batch = result["Rows"][1:] if first else result["Rows"]
                            rows.extend([[cell.get("VarCharValue") for cell in row["Data"]] for row in batch])
                            first = False
                            token = page.get("next_token")
                            if not token or len(rows) >= 100:
                                break
                        stats = execution.get("Statistics", {})
                        return {"status": state, "query_id": query_id, "columns": columns, "rows": rows[:100],
                                "truncated": bool(token) or len(rows) > 100,
                                "bytes_scanned": stats.get("DataScannedInBytes"),
                                "engine_ms": stats.get("EngineExecutionTimeInMillis")}
    finally:
        if query_id and not terminal:
            # Upstream read mode blocks its stop operation. Cleanup uses this role's scoped cancel grant.
            cancel.stop_query_execution(QueryExecutionId=query_id)


def main():
    try:
        request = json.loads(sys.stdin.read(65536))
        result = asyncio.run(execute(request))
        print(json.dumps(result))
    except Exception:
        print(json.dumps({"status": "ERROR", "message": "Analytics unavailable; no successful report"}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
