#!/bin/bash
# Every boot: attach the data volume, install Docker, render secrets to tmpfs, start Hermes,
# install the profiles. Idempotent; safe to re-run by hand: sudo /opt/rg/dist/boot.sh
set -uo pipefail
. /etc/rg-hermes.env
log() { echo "[boot] $(date -u +%T) $*"; }
DIST=/opt/rg/dist

TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)

# ---- 1. data volume: wait until the old (interrupted) instance lets go, then attach --------
for i in $(seq 1 60); do
  read -r STATE OWNER < <(aws ec2 describe-volumes --region "$REGION" --volume-ids "$DATA_VOLUME_ID" \
    --query 'Volumes[0].[State, Attachments[0].InstanceId]' --output text)
  if [ "$OWNER" = "$INSTANCE_ID" ]; then break; fi
  if [ "$STATE" = "available" ]; then
    aws ec2 attach-volume --region "$REGION" --volume-id "$DATA_VOLUME_ID" \
      --instance-id "$INSTANCE_ID" --device /dev/sdf >/dev/null && log "attach requested"
  else
    log "data volume is $STATE (held by $OWNER), waiting"
  fi
  sleep 10
done
DEV="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_$(echo "$DATA_VOLUME_ID" | tr -d -)"
for i in $(seq 1 30); do [ -e "$DEV" ] && break; sleep 2; done
if [ ! -e "$DEV" ]; then log "FATAL: data volume did not appear"; exit 1; fi
if ! blkid "$DEV" >/dev/null 2>&1; then
  log "new data volume: formatting"
  mkfs.ext4 -q -L rg-hermes-data "$DEV"
fi
mkdir -p /data
mountpoint -q /data || mount "$DEV" /data
grep -q " /data " /etc/fstab || echo "$DEV /data ext4 defaults,nofail 0 2" >> /etc/fstab
mkdir -p /data/hermes
# Terminal working dir of the profiles (terminal.cwd: /opt/data/work). Missing, every agent shell
# command fails on cd with exit 126.
mkdir -p /data/hermes/work && chown 10000:10000 /data/hermes/work
log "data volume mounted: $(df -h /data | awk 'NR==2{print $2" total, "$4" free"}')"

# ---- 2. Docker -------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  log "installing docker"
  apt-get update -qq && apt-get install -y -qq docker.io jq >/dev/null
fi
systemctl enable --now docker >/dev/null

# Containers must never reach the instance metadata (credentials). Hop limit 1 already
# blocks a bridged container; this rule is the second lock.
iptables -C DOCKER-USER -d 169.254.169.254 -j DROP 2>/dev/null \
  || iptables -I DOCKER-USER -d 169.254.169.254 -j DROP

# ---- 3. secrets to tmpfs, refreshed every 6 h ---------------------------------------------
install -m 0755 "$DIST/fetch-secrets.sh" /usr/local/sbin/rg-hermes-fetch-secrets
install -m 0644 "$DIST/rg-hermes.service" /etc/systemd/system/rg-hermes.service
install -m 0644 "$DIST/rg-hermes-secrets.service" /etc/systemd/system/rg-hermes-secrets.service
install -m 0644 "$DIST/rg-hermes-secrets.timer" /etc/systemd/system/rg-hermes-secrets.timer
# user-data runs only on an instance's first boot; this unit re-runs boot.sh on reboots.
install -m 0644 "$DIST/rg-hermes-boot.service" /etc/systemd/system/rg-hermes-boot.service
# Collector (no LLM, host only: it needs the instance role). Timer on only when SCHEDULE_ENABLED=true (section 6).
install -m 0644 "$DIST/rg-hermes-collect.service" /etc/systemd/system/rg-hermes-collect.service
install -m 0644 "$DIST/rg-hermes-collect.timer" /etc/systemd/system/rg-hermes-collect.timer
# Kiosk credentials (profiles with kiosk.json get a short-lived role; not a schedule of work, so it is on).
install -m 0755 "$DIST/kiosk-creds.sh" /usr/local/sbin/rg-kiosk-creds
install -m 0644 "$DIST/rg-kiosk-creds.service" /etc/systemd/system/rg-kiosk-creds.service
install -m 0644 "$DIST/rg-kiosk-creds.timer" /etc/systemd/system/rg-kiosk-creds.timer
systemctl daemon-reload
systemctl enable rg-hermes-boot.service >/dev/null
/usr/local/sbin/rg-hermes-fetch-secrets

# ---- 4. Hermes container -------------------------------------------------------------------
docker pull -q "$HERMES_IMAGE" >/dev/null && log "image ready: $HERMES_IMAGE"
mkdir -p /opt/rg/profiles
aws s3 sync "s3://$BUCKET/engine-code/profiles/" /opt/rg/profiles/ --region "$REGION" --delete --exact-timestamps
systemctl enable rg-hermes.service rg-hermes-secrets.timer >/dev/null
systemctl restart rg-hermes.service
systemctl start rg-hermes-secrets.timer

# ---- 5. profiles (desk, analyst, builder if the kiosk is on) from the copy in S3 -------------------------
for i in $(seq 1 60); do docker exec hermes true 2>/dev/null && break; sleep 2; done
for p in /opt/rg/profiles/*/; do
  [ -f "$p/distribution.yaml" ] || continue
  name=$(basename "$p")
  if docker exec hermes test -d "/opt/data/profiles/$name"; then
    # Git is the source of truth: re-apply SOUL, config, skills and cron from the repo copy.
    # Memories, sessions and skills the agent made itself are kept.
    if docker exec hermes hermes profile update "$name" --force-config --yes >/dev/null; then
      log "profile $name reconciled to $(grep -m1 '^version:' "$p/distribution.yaml")"
    else
      log "WARNING: profile $name update failed"
    fi
  else
    docker exec hermes hermes profile install "/opt/rg-profiles/$name" --name "$name" --yes \
      && log "profile $name installed" || log "WARNING: profile $name install failed"
  fi
done
# A chat session keeps the SOUL and skill list it started with. Restart once so no open
# session runs on the pre-update profile.
systemctl restart rg-hermes.service && log "hermes restarted on reconciled profiles"
mkdir -p /data/hermes/kiosk && chown 10000:10000 /data/hermes/kiosk
systemctl enable --now rg-kiosk-creds.timer >/dev/null
if ls /opt/rg/profiles/*/kiosk.json >/dev/null 2>&1; then
  systemctl start rg-kiosk-creds.service && log "kiosk credentials refreshed" || log "WARNING: kiosk credentials failed"
fi

# ---- 6. schedule: collector timer + the agents' cron jobs, on only when the owner turned it on ----
# Note: subscription plans that allow interactive use only (e.g. Alibaba Token Plan) forbid scheduled
# jobs; use a pay-as-you-go key before switching this on (docs/MODELS.md).
mkdir -p /etc/systemd/system/rg-hermes-collect.timer.d
printf '[Timer]\nOnCalendar=\nOnCalendar=%s\n' "$COLLECT_ON_CALENDAR" > /etc/systemd/system/rg-hermes-collect.timer.d/schedule.conf
systemctl daemon-reload
if [ "${SCHEDULE_ENABLED:-false}" = "true" ]; then
  systemctl enable --now rg-hermes-collect.timer >/dev/null; action=resume
else
  systemctl disable --now rg-hermes-collect.timer >/dev/null 2>&1; action=pause
fi
for jobs in /opt/rg/profiles/*/cron/jobs.json; do
  [ -f "$jobs" ] || continue
  prof=$(basename "$(dirname "$(dirname "$jobs")")")
  for id in $(jq -r '.jobs[].id' "$jobs"); do
    docker exec -u hermes hermes hermes -p "$prof" cron "$action" "$id" >/dev/null 2>&1 \
      && log "cron $prof/$id: $action" || log "WARNING: cron $prof/$id $action failed"
  done
done
log "boot complete (schedule ${SCHEDULE_ENABLED:-false})"
