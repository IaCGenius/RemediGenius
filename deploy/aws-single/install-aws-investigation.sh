#!/usr/bin/env bash
# Optional managed AWS investigation transport. Run on the standard CE host as root.
# No IAM changes, no credentials in Hermes, no general-purpose script tool exposed.
set -euo pipefail
MODE="${1:-enable}"
case "$MODE" in enable|disable) ;; *) echo 'Usage: install-aws-investigation.sh [enable|disable]' >&2; exit 2;; esac
PY=/opt/rgtriage/venv/bin/python
PROFILE=/data/rgconfig/triage.yaml
test "$(id -u)" = 0 || { echo 'Run on the CE host as root.' >&2; exit 1; }
test -x "$PY" && test -f "$PROFILE"
if [ "$MODE" = enable ]; then
  "$PY" - "$PROFILE" <<'PY'
import sys, yaml
p=yaml.safe_load(open(sys.argv[1]))
assert p.get('accounts') and all(a.get('role_arn') for a in p['accounts']), 'Configure explicit audit roles first'
PY
  # Preserve all installed desk pins; a conflict fails before changing the profile.
  CONSTRAINTS=$(mktemp)
  trap 'rm -f "$CONSTRAINTS"' EXIT
  "$PY" -m pip freeze > "$CONSTRAINTS"
  timeout 150 "$PY" -m pip install --disable-pip-version-check -c "$CONSTRAINTS" \
    -c "$(dirname "$0")/aws-mcp-constraints.txt" 'mcp-proxy-for-aws==1.7.0'
fi
"$PY" - "$PROFILE" "$MODE" <<'PY'
import os, pathlib, shutil, sys, yaml
p=pathlib.Path(sys.argv[1]); data=yaml.safe_load(p.read_text())
backup=p.with_suffix('.before-aws-mcp.yaml')
if not backup.exists(): shutil.copy2(p, backup)
settings=data.setdefault('aws_investigation', {})
settings['transport']='managed_mcp' if sys.argv[2]=='enable' else 'direct'
settings.setdefault('endpoint_region', 'us-east-1')
temporary=p.with_suffix('.aws-mcp.tmp')
try:
    shutil.copy2(p, temporary)
    st=p.stat(); os.chown(temporary, st.st_uid, st.st_gid)
    temporary.write_text(yaml.safe_dump(data, sort_keys=False))
    os.replace(temporary,p)
finally:
    temporary.unlink(missing_ok=True)
print('Investigation transport:', settings['transport'])
print('Configuration saved. Verify with a scoped AWS read; collection remains direct SDK.')
PY
