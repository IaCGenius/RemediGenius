---
name: rg-onboard
description: Onboard AWS accounts for triage - which organization accounts are read fully, findings-only or not covered, and the one-time read-role StackSet for the rest; check source coverage, set business context (criticality, applications, goals, IaC repos) and scheduled alerts.
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
- `iam simulate_principal_policy` or Access Analyzer `check_*` denied → the read role predates the policy
  evaluation permissions; redeploy the role template (Spot: `terraform apply`; members: update the StackSet).
- An AWS read refused with "Several accounts are readable" → pass `account`; a read in the wrong account is not
  evidence about this one.
- Health `SubscriptionRequired` → Health API needs Business support; Health events still arrive via Security Hub.

## 2. Other AWS accounts (onboarding is automatic after one setup step)
`rg_triage action=onboarding` → organization, whether this account is the Security Hub / GuardDuty / Inspector
delegated administrator, and every known account as **read fully**, **findings only** (seen through the
administrator view, no read role) or **not covered**, plus filled-in next steps.

Explain it in plain terms, for example: "I can see findings for 7 accounts through the delegated administrator, and
read 4 of them fully. For the other 3 I can't investigate (CloudTrail, IAM, Config) until they have the read role."

When accounts are missing, give the user the exact command from `next_steps`. Do not invent values; the desk fills in
the desk identity ARN and organization id. Tell them:
- Run it once, with management-account (or StackSets delegated administrator) credentials, from the release folder.
- It deploys `RemediGeniusReadOnly` (SecurityAudit + ViewOnlyAccess + IAM policy simulation and Access Analyzer policy
  checks, denies secret/object/KMS reads) to every account,
  including accounts added later (auto-deployment).
- Nothing else is needed: no restart, no Terraform or triage.yaml change. The next scan reads every account where the
  role works, and the board says "Newly onboarded". Offer to run `scan` once they say it is deployed, then run
  `onboarding` again to confirm.
- StackSets skip the management account; deploy the template there as a normal stack if it should be covered.

If the desk is not the delegated administrator, mention that running it in the delegated administrator account gives the
org-wide findings view immediately. If the account is not in an organization, follow the standalone step in
`next_steps` (one stack per account, then list it under `accounts:` with its `role_arn`).
<!-- PROTECTED_START -->
You never deploy roles or run the command yourself; you are read-only.
The tool blocks every non-read AWS call even if the credentials could write.
<!-- PROTECTED_END -->

## 2a. Confirm the scope once
The board's "Inspected:" line and `footprint` say which regions are enabled and which hold resources outside the scan.
Show the user: accounts read fully, findings-only, not covered; regions scanned; regions with resources not scanned.
Ask once: "Are these all your accounts and regions that matter?" Record the answer as a Note concept
(`knowledge/notes/scope.md`: what is in scope, what is deliberately out, who confirmed, the date) and call
`rg_triage action=remember path=<draft>`. If they want more regions, show the `regions:` change for `triage.yaml`.

## 2b. Connect a code repository (so fixes can become pull requests)
If the user wants fixes opened as pull requests, or asks to connect their repo or GitHub: call `rg_triage action=github op=status`, then send
them to the **GitHub tab** in this console (left menu) and say what they will do there: click **Connect GitHub** (two clicks on github.com:
create the app, then install it on only the repository they choose), then pick the repository, the development branch and the human
reviewers. The page shows which protections are in place and what is still missing, and has Reconnect and Disconnect buttons.
- You cannot connect GitHub for them, and never ask for tokens, keys or passwords in chat; the connection is made on that page.
- Pull requests need branch protection on GitHub (a required review, no force push). On a repository that cannot have it (for example a
  private repository on GitHub's free plan) the page says so and the desk stays read-and-propose only.
- Once connected, `op=refresh` re-reads their development branch after they change the repository.

## 3. Business context in ten minutes (changes priorities)
When the board says "Business context: N of 5 basics set", offer this. Prefill from read-only evidence, then ask the
user to confirm in a few short answers; each confirmed fact becomes a draft plus `remember` (one click each):
1. Accounts: `organizations list_accounts` (management or delegated account) or the configured accounts. Ask which
   are production / mission critical → Account concepts.
2. Critical applications: `resourcegroupstaggingapi get_tag_keys`, then `get_tag_values` for keys like `app`,
   `Application`, `Project`, `service`. Suggest the values behind the most findings; ask for the top 1–3 →
   Application concepts with `match_tags`.
3. Owners: `owner`/`team` tag values and CODEOWNERS in the configured IaC repositories (`read_file`); ask for a
   contact per application → Team concepts.
4. IaC locations: `rg_triage action=doctor` lists them; if none, show the `iac_paths` change for `triage.yaml`.
5. One policy: offer "no SSH from the internet" or "production buckets never public" → Policy concept.
Keep it to these five; more can come later. Do not ask about anything the evidence already answers.

## 3b. Business context, the long form
Business context lives in the knowledge base (load `rg-knowledge`). Start from `rg_triage action=knowledge view=gaps`
and ask briefly, one question at a time, only what changes ranking:
- Which accounts are production / mission critical? → an Account concept draft.
- Which applications matter most, how are their resources tagged, who owns them? → Application and Team drafts.
- Top 1–3 goals in plain words (e.g. "protect customer PII in S3") → a Security Goal draft.
Write drafts under the proposals folder's `knowledge/` and tell the user to approve them in the dashboard
**Knowledge** tab (or to use its Add form directly); approved concepts apply at the next `scan`.
`triage.yaml` keeps the technical settings: regions, `iac_paths` (local clones of Terraform/CloudFormation/CDK repos),
`environment_tag_keys`, sources and limits. Show any YAML change for the user to save.

## 4. Bring findings to the user without being asked
- Every new session opens with the attention board (plugin), refreshed in the background when stale.
- Scheduled alert with no model cost (Hermes cron runs the script; empty output = silent):
  `hermes -p <profile> cron create "every 2h" --name security-watch --no-agent --script rgtriage-watch.py --deliver <telegram|local|...>`
  (`rgtriage watch` prints only NEW P1/P2 findings.) The installer creates the script.
- Daily briefing with the agent (uses the model):
  `hermes -p <profile> cron create "0 8 * * 1-5" "Brief me on the security attention board" --skill rg-triage --deliver <target>`
Creating schedules changes the user's system: show the command and let the user run it or confirm.
