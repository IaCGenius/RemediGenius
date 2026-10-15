#!/usr/bin/env bash
# Re-run the host's boot over SSM after a `terraform apply` that changed profiles or host scripts:
# sync the boot scripts from S3, then boot.sh (idempotent: reconciles profiles, keeps agent memory).
# Changes to user-data values (schedule_enabled, collect_on_calendar, hermes_image, ...) replace the instance
# on apply instead; no refresh needed for those.
#   REGION=us-east-1 ASG=rgce-hermes ./refresh.sh
set -euo pipefail
REGION="${REGION:-us-east-1}"; ASG="${ASG:-rgce-hermes}"
id=$(aws autoscaling describe-auto-scaling-groups --region "$REGION" --auto-scaling-group-names "$ASG" \
  --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' --output text)
[ -n "$id" ] && [ "$id" != None ] || { echo "no running instance in $ASG (running = false?)"; exit 1; }
cmd='. /etc/rg-hermes.env && aws s3 sync "s3://$BUCKET/engine-code/dist/" /opt/rg/dist/ --delete --region "$REGION" --only-show-errors && chmod +x /opt/rg/dist/*.sh && /opt/rg/dist/boot.sh 2>&1 | grep "\[boot\]"'
cid=$(aws ssm send-command --region "$REGION" --instance-ids "$id" --document-name AWS-RunShellScript \
  --parameters "$(jq -cn --arg c "$cmd" '{commands: [$c], executionTimeout: ["900"]}')" --query Command.CommandId --output text)
echo "refreshing $id (command $cid) ..."
while :; do
  sleep 5
  s=$(aws ssm get-command-invocation --region "$REGION" --command-id "$cid" --instance-id "$id" --query Status --output text 2>/dev/null || true)
  case "$s" in Pending|InProgress|Delayed|"") ;; *) break ;; esac
done
aws ssm get-command-invocation --region "$REGION" --command-id "$cid" --instance-id "$id" --query StandardOutputContent --output text
echo "status: $s"; [ "$s" = Success ]
