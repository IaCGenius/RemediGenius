---
name: rg-investigate
description: Investigate a GuardDuty threat, security alarm or suspicious event with bounded read-only AWS calls (CloudTrail, IAM, EC2, S3) and conclude expected vs suspicious.
license: Apache-2.0
---
# Investigate a threat or alert

Goal: decide **expected activity vs. possible compromise** fast, with evidence, and tell the user
what to do next. Budget: about 3–6 read calls. Stop when the answer is clear.

## Steps
1. `rg_triage action=show ref=<ref>` — read actor (principal, access key, IP, ASN, country, API),
   event count, first/last seen, resource, related findings.
2. Pull the evidence that answers "who/what/when" (pick only what is needed):
   - Recent calls by that key: `rg_triage action=aws service=cloudtrail operation=lookup_events
     parameters={"LookupAttributes":[{"AttributeKey":"AccessKeyId","AttributeValue":"<key>"}],"MaxResults":50}`
   - By user name (root shows as `root`): `AttributeKey: Username`.
   - On a resource: `AttributeKey: ResourceName`, value = bucket/instance id.
   - IAM context: `iam get_user`, `iam list_access_keys`, `iam get_access_key_last_used`.
   - EC2 context: `ec2 describe_instances`, `ec2 describe_security_groups`.
   - Full GuardDuty record: `guardduty get_findings` with DetectorId and FindingIds from the native id
     (`arn:...:detector/<DetectorId>/finding/<FindingId>`).
3. Read CloudTrail fields that decide the case: `userAgent` (Terraform? console browser? aws-cli? SDK
   in a script?), `sourceIPAddress` (matches the user's other activity?), `sessionCredentialFromConsole`,
   `mfaAuthenticated`, error codes, time pattern.
4. Conclude in this shape:
   ```
   Verdict: likely expected | suspicious | compromise indicators | can't tell yet
   Evidence: 3 bullets with times, IPs, user agents, APIs
   Gaps: what you could not see (e.g. S3 data events are not in lookup_events; 90-day limit)
   Do now: containment or "nothing", and the long-term fix (load rg-iac-fix when code is involved)
   ```
<!-- PROTECTED_START -->
5. If only the user can confirm ("was this you running terraform at 14:02 UTC?"), ask once. Propose
   the decision (`false_positive` + reason if expected; `investigating` otherwise) and record it with
   `decide` only after the user confirms. Never record decisions in unattended/scheduled runs.
<!-- PROTECTED_END -->

## Rules
<!-- PROTECTED_START -->
- Read-only. Containment commands are shown for the operator to run, never executed by you.
<!-- PROTECTED_END -->
- `lookup_events` covers management events for 90 days in one region per call; say so.
- AnomalousBehavior findings flag deviations from a baseline: a person's new tool also triggers
  them. Don't call it an attack without corroboration; don't dismiss it without checking the actor.
- Root activity: console sessions with MFA from the user's usual IP are different from access-key
  calls from an unknown ASN. Either way recommend reducing root use (playbook root-account).
