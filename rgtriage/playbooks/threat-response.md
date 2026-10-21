# Threat findings (GuardDuty, security CloudWatch alarms)

GuardDuty detects behavior, not configuration. High `event_count`, recent last-seen, unknown IPs/ASNs and
sensitive resources raise urgency. `*/AnomalousBehavior*` findings compare against the principal's baseline:
a legitimate user running a new tool, script or Terraform also triggers them.

**Triage questions (answer from evidence first; ask the user only what you cannot see):**
1. Who: principal, access key, user agent, source IP / ASN / country (`context.actor`).
2. What: API calls, target resource, volume; is the resource sensitive (tags, goals)?
3. When: first/last seen; still ongoing?
4. Expected? The user, CI, or a known tool? Ask once and record the answer with `rgtriage decide`.

**Read-only investigation:**
- `rgtriage aws cloudtrail lookup_events --params '{"LookupAttributes":[{"AttributeKey":"AccessKeyId","AttributeValue":"AKIA..."}],"MaxResults":50}' --region <r>`
- `rgtriage aws guardduty get_findings --params '{"DetectorId":"...","FindingIds":["..."]}'` for full detail.
- `lookup_events` returns management events only (90 days). S3 object-level data events are not included; say so.

**Containment options (operator decides and runs; never automatic):**
- IAM key: `aws iam update-access-key --user-name U --access-key-id K --status Inactive`
- EC2: attach an isolation security group with no rules; snapshot volumes for forensics first.
- S3: add a temporary bucket-policy Deny for the suspicious principal.

**Close-out:** expected activity → `rgtriage decide <ref> false_positive --reason "..."`. For recurring benign
patterns, propose a narrowly scoped suppression rule in IaC (`aws_guardduty_filter` with `action = "ARCHIVE"`,
criteria on finding type + principal + resource).
