---
type: Guide
title: "Evidence: detection and history"
description: Who did what and when - CloudTrail event history, Config history, GuardDuty detail - and what each cannot see.
tags: [remedigenius, evidence, cloudtrail, config, guardduty]
sources:
  - {id: ct, resource: "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html", title: Viewing CloudTrail event history, author: aws-documentation}
  - {id: cfg, resource: "https://docs.aws.amazon.com/config/latest/developerguide/view-manage-resource-console.html", title: Looking up resource configuration history, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

Question shapes: "who created this?", "when did it change?", "was this key used?", "is logging on?".

## Reads that decide it
1. Who and when: `cloudtrail lookup_events` with one `LookupAttributes` entry (AccessKeyId, Username, ResourceName,
   EventName)[^ct]. Decisive fields inside `CloudTrailEvent`: `userIdentity`, `sourceIPAddress`, `userAgent`,
   `errorCode`, `mfaAuthenticated`. IAM, Organizations and STS events are recorded in us-east-1.
2. What changed: `config get_resource_config_history resourceType=... resourceId=...` where Config records[^cfg].
3. Is logging on: `cloudtrail describe_trails` + `get_trail_status`, `guardduty list_detectors` per region,
   `config describe_configuration_recorder_status`.
4. Threat detail: `guardduty get_findings` with the detector and finding ids from the native id.

## Limits to say out loud
- Event history covers 90 days of management events, one region per call; no S3 object or Lambda data events.
  "No events" beyond 90 days means "not visible", not "did not happen".
- Without Config recording there is no configuration timeline; do not reconstruct one from finding timestamps.

## Stop when
The who/what/when the user asked about is quoted from events, or the window and region you searched are stated.

Related: [logging and detection](/remedigenius/practices/logging-and-detection.md) ·
[threat response](/remedigenius/playbooks/threat-response.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^ct]: Viewing CloudTrail event history
[^cfg]: Looking up resource configuration history
