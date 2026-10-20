---
name: ce-onboarding
description: Onboard an AWS account or organizational knowledge through short Q&A; show saved background status and confirm a reusable workload brief without a full investigation.
license: Apache-2.0
---
# Two onboarding conversations

Use for account onboarding, "show account status", "what do you know about this
account", or knowledge onboarding. Keep one ce-desk profile. Ask one short question
at a time and reuse existing answers.

## Account

1. Read `ce_aws(action="show", path="scheduled/account-status.json", limit=200)`.
   This is saved background evidence. If absent, try `scheduled/latest.json`.
   If neither exists, explain that the baseline is unavailable; do not silently
   start an account-wide investigation.
2. Present account/region, observed time, next expected refresh, tested reads,
   supplied counts and gaps. Compare current time with the next expected refresh.
   Overdue, RUNNING, partial or failed is not ready. Config counts cover recorded
   resources; successful reads do not prove service health or full inventory.
3. Read the selected knowledge index and relevant account/workload notes. Ask:
   "What is this account used for, and what should we protect or improve first?"
   If known, show the current understanding and ask only for corrections.
4. Use ce-knowledge to stage a short `org/context` account brief: exact scope,
   supplied purpose/goals/constraints, dated evidence references, and important
   unknowns. Separate observations from operator assertions. Show the draft and
   returned publish phrase; publication requires the operator's separate message.
5. Explain that background facts refresh independently; confirmed business context
   remains until corrected. Never replace it with assumptions from a scan.
   Offer a Kanban task for an access/configuration gap only on request.

Instance-role access already authorizes configured reads. Confirmation does not
grant access, apply fixes or add accounts. This baseline is not an AI security
assessment. For deeper analysis use the existing workflow and selected brief.
For saved status, answer directly without ce_assessment or redundant critique.

## Knowledge

Load ce-knowledge and its guided-knowledge reference. Start with purpose and goals.
Ask only what changes prioritization: resource scope, sensitivity/criticality,
ownership, change constraints or policy variations. Allow "unknown" and "skip".
Never ask for credentials or fill in invented owners, dates or business facts.

Draft and stage a small readable brief. Show the exact confirmation phrase.
Explicit publication makes it reusable; chat context is usable immediately.
After publication, read the returned document and explain how its actual content
will affect future prioritization. Do not claim a reassessment already ran.
