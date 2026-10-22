---
type: Guide
title: Beyond the desk's evidence
description: Questions that need more than configuration and 90 days of management events - could versus did, the evidence boundary, and where to hand off.
tags: [remedigenius, evidence, investigation, boundary]
sources:
  - {id: lake, resource: "https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake.html", title: Working with AWS CloudTrail Lake, author: aws-documentation}
  - {id: athena, resource: "https://docs.aws.amazon.com/athena/latest/ug/cloudtrail-logs.html", title: Querying AWS CloudTrail logs with Athena, author: aws-documentation}
  - {id: sir, resource: "https://docs.aws.amazon.com/security-ir/latest/userguide/what-is.html", title: What is AWS Security Incident Response, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

The desk reads configuration and bounded history. **Configuration answers *could*; only logs and detections answer
*did*.** Where the logs end, the answer is "not established", never "no" and never "yes".

```
Could:    what configuration allows (evidence ids)
Did:      what logs show happened (evidence ids), or "no evidence either way"
Boundary: what cannot be seen, and the next step to see it
```

| Question | Could (desk) | Did (desk) | Boundary and next step |
|---|---|---|---|
| Can this identity reach production data? | policy documents, `iam simulate_principal_policy`, AWS exposure findings | `RoleLastUsed`, CloudTrail management events (90 days) | which objects or rows were read needs S3 data events or database audit logs |
| Was data accessed or exfiltrated? | read permissions, public access settings | GuardDuty `Exfiltration:` findings, management events | S3 data events / server access logs via Athena[^athena] or CloudTrail Lake[^lake]; for an active incident, AWS Security Incident Response[^sir] |
| How far could an attacker move from this workload? | instance or task role permissions, roles it can assume (simulator), AWS exposure finding attack path | GuardDuty findings on the resource | actual movement: Detective behavior graph, VPC Flow Logs; the desk's own path is a **hypothesis** |
| What happened before the event history? | not applicable | nothing beyond 90 days | the trail's S3 logs via Athena, or CloudTrail Lake |

Queries for the operator to run (Athena over the trail's S3 logs, table created as in the AWS guide):

```sql
-- Who used a key or role, any age the trail keeps
SELECT eventtime, eventname, sourceipaddress, useragent, errorcode
FROM cloudtrail_logs WHERE useridentity.accesskeyid = '<key id>' OR useridentity.arn LIKE '%<role name>%'
ORDER BY eventtime;
-- Object reads on a bucket (needs S3 data events in the trail)
SELECT eventtime, useridentity.arn, sourceipaddress, json_extract_scalar(requestparameters, '$.key') AS object_key
FROM cloudtrail_logs WHERE eventsource = 's3.amazonaws.com' AND eventname = 'GetObject'
  AND json_extract_scalar(requestparameters, '$.bucketName') = '<bucket>' ORDER BY eventtime;
```

The desk does not run these: they read log contents, which its guard blocks on purpose.

Related: [detection and history](/remedigenius/guides/evidence-detection-and-history.md) ·
[threat response](/remedigenius/playbooks/threat-response.md)

[^lake]: Working with AWS CloudTrail Lake
[^athena]: Querying AWS CloudTrail logs with Athena
[^sir]: What is AWS Security Incident Response
