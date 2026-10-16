#!/usr/bin/env bash
set -euo pipefail
region=us-east-1
name=rgce-native
port=9125
login=false
only_login=false
while (($#)); do
  case "$1" in
    --region) region="${2:?Missing region}"; shift 2 ;;
    --name) name="${2:?Missing stack name}"; shift 2 ;;
    --port) port="${2:?Missing local port}"; shift 2 ;;
    --with-login) login=true; shift ;;
    --show-login) login=true; only_login=true; shift ;;
    *) echo 'Usage: bash tools/open-native-hermes.sh [--region us-east-1] [--name rgce-native] [--port 9125] [--with-login|--show-login]' >&2; exit 2 ;;
  esac
done
[[ "$port" =~ ^[0-9]+$ ]] && ((port >= 1024 && port <= 65535)) || { echo 'Use a local port from 1024 to 65535' >&2; exit 2; }
if "$login"; then
  aws secretsmanager get-secret-value --region "$region" --secret-id "$name/dashboard" --query SecretString --output text |
    python3 -c 'import json,sys; v=json.load(sys.stdin); print("Username: "+v["username"]+"\nPassword: "+v["password"])'
  echo 'Private dashboard credentials, not your model key. Do not paste into chat.'
  if "$only_login"; then exit 0; fi
fi
command -v session-manager-plugin >/dev/null || { echo 'Install the AWS Session Manager plugin for Linux first.' >&2; exit 1; }
instance=$(aws autoscaling describe-auto-scaling-groups --region "$region" --auto-scaling-group-names "$name" --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' --output text)
[[ "$instance" == i-* ]] || { echo 'No InService CE instance. Start the stack and wait for SSM.' >&2; exit 1; }
echo "Open http://127.0.0.1:$port/chat?profile=ce-desk in your browser. Keep this tunnel open."
exec aws ssm start-session --region "$region" --target "$instance" --document-name AWS-StartPortForwardingSession --parameters "portNumber=9120,localPortNumber=$port"
