"""Render connection instructions; never install, launch or reconfigure the user's agent."""
import shutil
import os
import sys
from .store import default_home

TOOLS = ["list_capabilities", "list_assessments", "list_evidence", "get_record", "investigate", "prepare_proposal", "reassess", "search_knowledge_sources", "list_knowledge_concepts", "prepare_knowledge_review"]


def connection(home=None):
    server = {"command": sys.executable, "args": ["-m", "rgce.mcp_server"], "env": {"RGCE_HOME": str(home or default_home())}}
    return {"runtime": "Hermes or any local stdio MCP client", "hermes_installed": shutil.which("hermes") is not None,
        "local_stdio_supported": os.environ.get('RGCE_CONTAINER') != '1' and not os.environ.get('RGCE_STORAGE_BUCKET'),
        "connection_notice": "For Docker or S3 workspaces, download selected investigation files for your agent. The displayed server paths belong to this runtime, not your workstation; local stdio MCP is supported for a native local-data installation with the mcp extra.",
        "ai_enabled_in_console": bool(os.environ.get('RGCE_HERMES_JOBS')), "data_disclosure": "Your selected agent can send retrieved evidence to its model. Review the disclosure snapshot, provider and tool permissions before starting.",
        "model_configuration": "Use Hermes native model/setup configuration in a dedicated profile. CE does not store API keys or replace provider authentication.",
        "hermes_config": {"mcp_servers": {"remedigenius": {**server, "tools": {"include": TOOLS}}}},
        "generic_config": {"mcpServers": {"remedigenius": server}},
        "isolation": "A profile is configuration separation, not an OS security boundary. Use a separate user/container without cloud credentials for untrusted investigations."}
