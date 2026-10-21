---
name: rg-onboard
description: Onboard AWS accounts and regions for triage, check read access and source coverage, set business context (criticality, applications, goals, IaC repos) and set up scheduled alerts.
license: Apache-2.0
---
# Onboarding and access

The triage profile is `triage.yaml` in the rgtriage home folder (path shown by `rg_triage action=doctor`).
It is the operator's file; you explain and propose edits, the operator saves them (or you write a
proposed copy under the proposals folder for them to move).

## 1. Check what works
`rg_triage action=doctor` → identity per account, and per source/region: `ok`, `not_enabled`,
`denied`, `error`, plus recommendations. Explain blind spots in plain terms:
- Security Hub off → no posture checks (CIS/FSBP). GuardDuty off → no threat detection.
- Inspector off → no CVE findings. Config off → no change history (and Config.1 fails).
- `denied` → the reading identity lacks permissions: attach AWS managed policy `SecurityAudit`.
- Health `SubscriptionRequired` → Health API needs Business support; Health events still arrive via Security Hub.

## 2. Add accounts (read-only)
Best practice (borrowed from the AWS Well-Architected Agent model): one read-only **access role** per
workload account, assumed from the account where the desk runs.
```hcl
# in each workload account
resource "aws_iam_role" "remedigenius_readonly" {
  name = "RemediGeniusReadOnly"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::<DESK_ACCOUNT_ID>:root" }   # or the desk's role ARN
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "sts:ExternalId" = "<random-string>" } }
    }]
  })
}
resource "aws_iam_role_policy_attachment" "security_audit" {
  role       = aws_iam_role.remedigenius_readonly.name
  policy_arn = "arn:aws:iam::aws:policy/SecurityAudit"
}
```
Then add to `triage.yaml`:
```yaml
accounts:
  - name: prod
    account_id: "111122223333"
    role_arn: arn:aws:iam::111122223333:role/RemediGeniusReadOnly
    external_id: <random-string>
    regions: [us-east-1, eu-west-1]
    criticality: mission_critical
```
A local CLI profile works too (`aws_profile: prod-readonly`). If Security Hub has a cross-region
aggregator or a delegated administrator, reading that one account/region already covers the others;
add member accounts only for GuardDuty/Inspector detail or when there is no delegated admin.
The tool blocks every non-read AWS call even if the credentials could write.

## 3. Business context (changes priorities)
Ask briefly, one question at a time, only what changes ranking:
- Which accounts are production / mission critical? → `criticality` per account.
- Which applications matter most and how are they tagged? → `applications: [{name, tags, criticality}]`.
- Which tag marks environments? → `environment_tag_keys`.
- Top 1–3 goals in plain words (e.g. "protect customer PII in S3") → `goals` with `boost`
  (`resource_types`, `categories`, or `signals` such as `public_exposure`, `identity_risk`).
- Where is the IaC? → `iac_paths` (local clones of Terraform/CloudFormation/CDK repos).
Show the YAML change, then re-run `scan` so the new context applies.

## 4. Bring findings to the user without being asked
- Every new session opens with the attention board (plugin), refreshed in the background when stale.
- Scheduled alert with no model cost (Hermes cron runs the script; empty output = silent):
  `hermes -p <profile> cron create "every 2h" --name security-watch --no-agent --script rgtriage-watch.py --deliver <telegram|local|...>`
  (`rgtriage watch` prints only NEW P1/P2 findings.) The installer creates the script.
- Daily briefing with the agent (uses the model):
  `hermes -p <profile> cron create "0 8 * * 1-5" "Brief me on the security attention board" --skill rg-triage --deliver <target>`
Creating schedules changes the user's system: show the command and let the user run it or confirm.
