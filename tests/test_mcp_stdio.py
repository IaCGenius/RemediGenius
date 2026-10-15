"""A subprocess transport check using the public MCP client API."""
import asyncio
import json
import os
import sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from rgce import core
from rgce.store import Store


def test_stdio_mcp_reads_the_selected_workspace(tmp_path):
    d = core.demo(Store(tmp_path))
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "rgce.mcp_server"], env={**os.environ, "RGCE_HOME": str(tmp_path)})
        async with Client(params, read_timeout_seconds=20) as client:
            tools = await client.list_tools()
            assert len(tools.tools) == 10
            result = await client.call_tool("get_record", {"record_id": d["before"]["id"]})
            assert not result.is_error
            body = result.structured_content or json.loads(result.content[0].text)
            assert body["id"] == d["before"]["id"]
    asyncio.run(run())
