#!/usr/bin/env bash
# Open the tunnel Hermes Desktop uses: laptop 127.0.0.1:9120 -> host loopback 9120 (SSM, no open ports).
# Looks up the current spot instance, so it keeps working after a spot replacement.
#   ./connect.sh            tunnel for Desktop (leave it running)
#   ./connect.sh shell      shell on the host
set -euo pipefail
export PATH="$PATH:/c/Program Files/Amazon/SessionManagerPlugin/bin"   # Windows Git Bash; needs the Session Manager plugin
REGION="${REGION:-us-east-1}"; ASG="${ASG:-rgce-hermes}"; PORT="${PORT:-9120}"
id=$(aws autoscaling describe-auto-scaling-groups --region "$REGION" --auto-scaling-group-names "$ASG" \
  --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' --output text)
[ -n "$id" ] && [ "$id" != None ] || { echo "no running instance in $ASG (running = false?)"; exit 1; }
if [ "${1:-}" = shell ]; then exec aws ssm start-session --region "$REGION" --target "$id"; fi
echo "tunnel to $id: Desktop remote gateway URL http://127.0.0.1:$PORT (Ctrl+C to close)"
exec aws ssm start-session --region "$REGION" --target "$id" --document-name AWS-StartPortForwardingSession \
  --parameters "{\"portNumber\":[\"$PORT\"],\"localPortNumber\":[\"$PORT\"]}"
