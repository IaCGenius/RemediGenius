#!/usr/bin/env bash
# Rebuildable isolated vendor runtime; never install its SDK into Hermes or the desk.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run on the CE host as root.' >&2; exit 1; }
RUNTIME=/opt/rgtriage/athena-venv
if [ ! -x "$RUNTIME/bin/python" ]; then
  python3.11 -m venv "$RUNTIME"
fi
timeout 150 "$RUNTIME/bin/python" -m pip install --disable-pip-version-check \
  -c "$(dirname "$0")/athena-mcp-constraints.txt" 'awslabs.aws-dataprocessing-mcp-server==0.2.2'
"$RUNTIME/bin/python" -m pip check
"$RUNTIME/bin/python" -c 'from mcp import ClientSession; import boto3; from importlib.metadata import version; assert version("awslabs.aws-dataprocessing-mcp-server") == "0.2.2"'
echo 'Athena MCP runtime ready'
