#!/usr/bin/env bash
# Every offline test: rules, results, kiosk CLI, community checks, the kiosk module, Terraform validate.
set -euo pipefail
cd "$(dirname "$0")/.."
CE_PYTHON=python
[ ! -x .venv/bin/python ] || CE_PYTHON="$(pwd)/.venv/bin/python"
"$CE_PYTHON" tests/test_checks.py
"$CE_PYTHON" tests/test_results.py
"$CE_PYTHON" -m pytest -q -p no:warnings tests/test_ce.py tests/test_documents.py tests/test_knowledge.py tests/test_simple_knowledge.py tests/test_adapters.py tests/test_onboarding.py tests/test_workspace.py tests/test_approved_reader.py tests/test_mcp_stdio.py tests/test_kiosk_cli.py tests/test_community.py tests/test_object_storage.py
(cd modules/lambda-kiosk && "$CE_PYTHON" -m pytest -q -p no:warnings tests)
bash -n deploy/aws/host/boot.sh deploy/aws/refresh.sh deploy/aws/connect.sh
if command -v terraform >/dev/null; then
  [ -f modules/lambda-kiosk/build/gate.zip ] || "$CE_PYTHON" modules/lambda-kiosk/build.py
  (cd deploy/aws && terraform fmt -check -recursive . && terraform init -backend=false -input=false >/dev/null && terraform validate)
fi
echo "all tests passed"
