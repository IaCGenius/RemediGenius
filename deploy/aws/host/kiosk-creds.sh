#!/bin/bash
# Short-lived kiosk credentials for each Hermes profile that ships a kiosk.json ({"kiosk": "...", "agent": "..."}).
# The host (instance role) assumes kiosk-<kiosk>-agent-<agent> for 1 hour and writes the credentials where only
# that profile's `kiosk` command reads them: /data/hermes/kiosk/<agent>/ (container: /opt/data/kiosk/<agent>/).
# The container never gets the instance role. Runs at boot and every 40 minutes (rg-kiosk-creds.timer).
set -uo pipefail
. /etc/rg-hermes.env
ACCOUNT=$(aws sts get-caller-identity --query Account --output text --region "$REGION") || exit 1
rc=0
for f in /opt/rg/profiles/*/kiosk.json; do
  [ -f "$f" ] || continue
  kiosk=$(jq -r .kiosk "$f"); agent=$(jq -r .agent "$f")
  dir="/data/hermes/kiosk/$agent"; mkdir -p "$dir"
  out=$(aws sts assume-role --region "$REGION" --role-arn "arn:aws:iam::$ACCOUNT:role/kiosk-$kiosk-agent-$agent" \
        --role-session-name "kiosk-$agent" --source-identity "kiosk-$agent" --duration-seconds 3600 \
        --query Credentials --output json) || { echo "kiosk-creds: assume failed for $agent"; rc=1; continue; }
  umask 077
  printf '[kiosk]\naws_access_key_id = %s\naws_secret_access_key = %s\naws_session_token = %s\n# expires %s\n' \
    "$(jq -r .AccessKeyId <<<"$out")" "$(jq -r .SecretAccessKey <<<"$out")" "$(jq -r .SessionToken <<<"$out")" \
    "$(jq -r .Expiration <<<"$out")" > "$dir/credentials.tmp"
  printf 'KIOSK_NAME=%s\nKIOSK_AGENT=%s\nAWS_REGION=%s\n' "$kiosk" "$agent" "$REGION" > "$dir/kiosk.env"
  mv "$dir/credentials.tmp" "$dir/credentials"
  chown -R 10000:10000 /data/hermes/kiosk && chmod 700 "$dir" && chmod 600 "$dir/credentials"
  echo "kiosk-creds: $agent refreshed (kiosk $kiosk, expires $(jq -r .Expiration <<<"$out"))"
done
exit $rc
