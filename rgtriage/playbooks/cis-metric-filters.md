# CIS log metric filters and alarms (CloudWatch.1–CloudWatch.14, CIS 3.x "Ensure a log metric filter and alarm exist for ...")

**Means:** CloudTrail events are not turned into alarms for sensitive changes. Each control expects a
metric filter on the CloudTrail log group plus an alarm whose SNS topic has a subscriber. Individually LOW;
fix them together as ONE change.

**Prerequisite:** a multi-region trail delivering to CloudWatch Logs (CloudTrail.5).

**Terraform (one map, all controls):**
```hcl
locals {
  cis_filters = {
    root_usage      = "{ $.userIdentity.type = \"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != \"AwsServiceEvent\" }"
    unauthorized    = "{ ($.errorCode = \"*UnauthorizedOperation\") || ($.errorCode = \"AccessDenied*\") }"
    console_no_mfa  = "{ ($.eventName = \"ConsoleLogin\") && ($.additionalEventData.MFAUsed != \"Yes\") && ($.userIdentity.type = \"IAMUser\") && ($.responseElements.ConsoleLogin = \"Success\") }"
    iam_changes     = "{ ($.eventName = DeleteGroupPolicy) || ($.eventName = DeleteRolePolicy) || ($.eventName = DeleteUserPolicy) || ($.eventName = PutGroupPolicy) || ($.eventName = PutRolePolicy) || ($.eventName = PutUserPolicy) || ($.eventName = CreatePolicy) || ($.eventName = DeletePolicy) || ($.eventName = CreatePolicyVersion) || ($.eventName = DeletePolicyVersion) || ($.eventName = AttachRolePolicy) || ($.eventName = DetachRolePolicy) || ($.eventName = AttachUserPolicy) || ($.eventName = DetachUserPolicy) || ($.eventName = AttachGroupPolicy) || ($.eventName = DetachGroupPolicy) }"
    trail_changes   = "{ ($.eventName = CreateTrail) || ($.eventName = UpdateTrail) || ($.eventName = DeleteTrail) || ($.eventName = StartLogging) || ($.eventName = StopLogging) }"
    console_failure = "{ ($.eventName = ConsoleLogin) && ($.errorMessage = \"Failed authentication\") }"
    cmk_disable     = "{ ($.eventSource = kms.amazonaws.com) && (($.eventName = DisableKey) || ($.eventName = ScheduleKeyDeletion)) }"
    s3_policy       = "{ ($.eventSource = s3.amazonaws.com) && (($.eventName = PutBucketAcl) || ($.eventName = PutBucketPolicy) || ($.eventName = PutBucketCors) || ($.eventName = PutBucketLifecycle) || ($.eventName = PutBucketReplication) || ($.eventName = DeleteBucketPolicy) || ($.eventName = DeleteBucketCors) || ($.eventName = DeleteBucketLifecycle) || ($.eventName = DeleteBucketReplication)) }"
    config_changes  = "{ ($.eventSource = config.amazonaws.com) && (($.eventName = StopConfigurationRecorder) || ($.eventName = DeleteDeliveryChannel) || ($.eventName = PutDeliveryChannel) || ($.eventName = PutConfigurationRecorder)) }"
    sg_changes      = "{ ($.eventName = AuthorizeSecurityGroupIngress) || ($.eventName = AuthorizeSecurityGroupEgress) || ($.eventName = RevokeSecurityGroupIngress) || ($.eventName = RevokeSecurityGroupEgress) || ($.eventName = CreateSecurityGroup) || ($.eventName = DeleteSecurityGroup) }"
    nacl_changes    = "{ ($.eventName = CreateNetworkAcl) || ($.eventName = CreateNetworkAclEntry) || ($.eventName = DeleteNetworkAcl) || ($.eventName = DeleteNetworkAclEntry) || ($.eventName = ReplaceNetworkAclEntry) || ($.eventName = ReplaceNetworkAclAssociation) }"
    gateway_changes = "{ ($.eventName = CreateCustomerGateway) || ($.eventName = DeleteCustomerGateway) || ($.eventName = AttachInternetGateway) || ($.eventName = CreateInternetGateway) || ($.eventName = DeleteInternetGateway) || ($.eventName = DetachInternetGateway) }"
    route_changes   = "{ ($.eventSource = ec2.amazonaws.com) && (($.eventName = CreateRoute) || ($.eventName = CreateRouteTable) || ($.eventName = ReplaceRoute) || ($.eventName = ReplaceRouteTableAssociation) || ($.eventName = DeleteRouteTable) || ($.eventName = DeleteRoute) || ($.eventName = DisassociateRouteTable)) }"
    vpc_changes     = "{ ($.eventName = CreateVpc) || ($.eventName = DeleteVpc) || ($.eventName = ModifyVpcAttribute) || ($.eventName = AcceptVpcPeeringConnection) || ($.eventName = CreateVpcPeeringConnection) || ($.eventName = DeleteVpcPeeringConnection) || ($.eventName = RejectVpcPeeringConnection) }"
  }
}

resource "aws_cloudwatch_log_metric_filter" "cis" {
  for_each       = local.cis_filters
  name           = "cis-${each.key}"
  log_group_name = aws_cloudwatch_log_group.trail.name
  pattern        = each.value
  metric_transformation {
    name      = "cis-${each.key}"
    namespace = "CISBenchmark"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "cis" {
  for_each            = local.cis_filters
  alarm_name          = "cis-${each.key}"
  namespace           = "CISBenchmark"
  metric_name         = "cis-${each.key}"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
}
```
Take exact patterns from each control's remediation URL if the CIS version in the finding differs.

**Trade-offs:** `unauthorized` is noisy; route it to a lower-urgency channel. Alternative: rely on GuardDuty +
EventBridge and disable these CIS controls in Security Hub with a documented reason.
