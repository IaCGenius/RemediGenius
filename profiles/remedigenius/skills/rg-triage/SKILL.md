---
name: rg-triage
description: Brief the user on their AWS security queue (Security Hub, GuardDuty, Inspector, Access Analyzer, Config, CloudWatch alarms, Health), explain priorities, explain and verify findings or any AWS configuration question (IAM trust and permissions, network exposure, data protection) with live read-only evidence, and record decisions. Not for suspicious-activity investigations (rg-investigate) or writing fixes (rg-iac-fix).
license: Apache-2.0
---
# Security queue triage

Use for "what needs attention", "show findings", "what's new", "why is this P1", morning/daily
briefings, recording decisions, and **"is this finding real / what does it mean / who can access X / can X do Y"**,
with or without a finding. Hand off: suspicious activity → `rg-investigate`; "fix it" → `rg-iac-fix`; owners and
accepted risks → `rg-knowledge`; missing accounts or sources → `rg-onboard`.

## 1. Get the board
- `rg_triage action=digest` reads the last scan (no AWS calls). Check the "Scanned ..." time.
- Run `rg_triage action=scan` when: the user asks for fresh data, the scan is older than ~6h, or
  you need to confirm something changed after a fix. Scans read every onboarded account/region.

## 2. Brief (lead with the decision)
Format for a briefing:
```
**N things need you today** (scan 12:47 UTC, account prod 1111…)
1. P1 <plain-language title> — <resource> · <why in ≤12 words> · ref `abc123…`
2. ...
New since last scan: … · Resolved: …
Blind spots: <coverage gaps that matter, e.g. "Config off in us-east-1 → no change history">
Next: "<one concrete suggestion>"
```
- Group related findings the way the board does (one issue = one fix). 14 CIS metric-filter
  controls are ONE change, not 14 problems.
- Translate titles into impact: "root credentials used 1,200 times this month from an unfamiliar network"
  beats "Policy:IAMUser/RootCredentialUsage".
- Keep source severity and our priority distinct: "GuardDuty rates it LOW; we rank it P1 because …".

## 3. Drill down
- `rg_triage action=list priority=P1,P2` or `issues=true` for grouped issues; filter by `source`,
  `category` (threat, vulnerability, exposure, posture, operational, health), `account`.
- `rg_triage action=show ref=<ref>` gives why-this-priority, actor/context, related findings on the
  same resource ("toxic combination"), AWS remediation link and console link.
- Threats/alerts → load `rg-investigate`. Fix questions → load `rg-iac-fix`.

## 3a. Explain or verify (a finding or any configuration question)
1. Scope: the resource, account and region (from the finding, or ask once if the question is ambiguous). Use the
   finding whose resource matches the question; a grouped issue's ref may point at another resource. A resource
   missing from the board may be accepted or resolved: `list all=true`.
2. Read the claim: `show ref=<ref>` gives the stored classification, any decision or accepted risk, and the evidence
   guide on its `Guidance:` line. If the risk is accepted (Risk Exception or decision), say so with its approver and
   expiry (`knowledge view=for ref=<ref>`); live reads then only confirm nothing changed beyond the exception.
   Load that guide (`knowledge view=show path=...`) unless you already know its reads.
3. Verify live with the reads the guide marks as decisive, passing `account` and `region`. Usually 1–3 reads; for
   identity questions the trust policy (`iam get_role`) or the policy documents (`iam get_role_policy`,
   `iam get_policy_version`) decide, and `iam simulate_principal_policy` answers "can X do Y" including SCPs.
   For a question without a finding ("which roles trust outsiders?") list first (`iam list_roles`), then read only
   the matches.
4. Compare: does live configuration support the finding's headline? If not, say exactly which field differs. Do not
   explain *why* or *when* it differs unless a read shows it (no change timeline without CloudTrail or Config).
5. Answer: one-line verdict, then **Observed** (fields quoted, `Evidence` line), **Inferred**, **Gaps**, and the
   residual risk in plain words (e.g. `repo:org/app:*` still admits any branch and pull request workflow). Offer the
   fix as a next step; do not write it unless asked.
6. If the finding no longer matches reality, propose the decision (`false_positive` or `resolved` with the evidence)
   and record it only after the user confirms.

## 4. Prioritization model (explain it when asked)
Score = source severity points (CRITICAL 60, HIGH 45, MEDIUM 25, LOW 10) + signals:
active threat (+10/+20 for compromise/exfiltration/impact types), root credential use (+15..+40 by
volume), public exposure (+15), exploit available (+12), EPSS ≥ 0.1 (+5), detection/audit gap (+8),
fix available (+3), toxic combination on one resource (+10), business criticality of the
account/application/env tag (−10..+15), business-goal match (+5), stale threat >30 days (−10).
P1 ≥ 70, P2 ≥ 50, P3 ≥ 30, else P4. Criticality, applications, accounts, goals and risk exceptions come
from reviewed knowledge concepts (cited by path in the reasons; see `rg-knowledge`), then `triage.yaml`.
A reviewed Risk Exception makes matching findings accepted risk until it expires. Never quietly override
the score; explain disagreements and record them.

<!-- PROTECTED_START -->
## 5. Record decisions (the user's, not yours)
Only record a decision the user stated in this conversation ("yes that was me", "accept it, it's a
test account"). Evidence that points to "expected" is a *proposal*: say "I suggest marking these
false_positive — confirm?" and wait. In scheduled or unattended runs never call decide; list the
proposed decisions instead. Hermes asks the user to approve each decide call.
`rg_triage action=decide ref=<ref> status=<status> reason="<user's words>"` with status:
acknowledged · investigating · fixing · accepted_risk · false_positive · suppressed · resolved.
Add `issue=true` to apply to every finding of a grouped issue. accepted_risk/false_positive/
suppressed/resolved hide the item from the board. Confirm before recording accepted_risk.
Decisions are local triage notes; they do not archive findings in AWS. If the user wants that,
show the operator CLI (e.g. `aws securityhub batch-update-findings ... Workflow={Status=SUPPRESSED}`).
<!-- PROTECTED_END -->

## 6. Share
`rg_triage action=report` writes a self-contained HTML report (filterable by priority/source) and
returns its path for the user to open or share.
