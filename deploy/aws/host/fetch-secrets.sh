#!/bin/bash
# Render the Hermes container env file into tmpfs from Secrets Manager.
# /run is memory-backed: keys never touch a disk, an AMI or a snapshot.
# Rotation = change the secret, then: systemctl start rg-hermes-secrets
set -euo pipefail
. /etc/rg-hermes.env
OUT_DIR=/run/rg-hermes
get() { aws secretsmanager get-secret-value --region "$REGION" --secret-id "$1" --query SecretString --output text 2>/dev/null || true; }

MODEL_KEY="$(get "$SECRET_MODEL")"
LOGIN="$(get "$SECRET_LOGIN")"
[ -n "$LOGIN" ] || { echo "fetch-secrets: dashboard login secret missing" >&2; exit 1; }
[ -n "$MODEL_KEY" ] || echo "fetch-secrets: WARNING model key not set yet (agents cannot answer until you set it: see the set_model_key output)" >&2

umask 077
mkdir -p "$OUT_DIR"
TMP="$(mktemp "$OUT_DIR/.env.XXXXXX")"
{
  echo "# rendered $(date -u +%FT%TZ) by rg-hermes-fetch-secrets (tmpfs)"
  echo "MODEL_API_KEY=$MODEL_KEY"
  echo "HERMES_DASHBOARD=1"
  echo "HERMES_DASHBOARD_PORT=$DASHBOARD_PORT"
  echo "HERMES_DASHBOARD_BASIC_AUTH_USERNAME=$(echo "$LOGIN" | jq -r .username)"
  echo "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=$(echo "$LOGIN" | jq -r .password)"
  echo "HERMES_DASHBOARD_BASIC_AUTH_SECRET=$(echo "$LOGIN" | jq -r .secret)"
} > "$TMP"
if [ -f "$OUT_DIR/env" ] && cmp -s <(grep -v '^#' "$TMP") <(grep -v '^#' "$OUT_DIR/env"); then
  rm -f "$TMP"; echo "fetch-secrets: unchanged"; exit 0
fi
mv -f "$TMP" "$OUT_DIR/env"
echo "fetch-secrets: rendered"
# Changed keys only reach the container on restart.
if systemctl is-active --quiet rg-hermes; then systemctl restart --no-block rg-hermes; fi
