# Proactive security trial

RemediGenius Community Edition uses native Hermes cron to investigate without
waiting for a chat question. The operator's AWS Security Agent proposal supplied
the cadence and profile-first approach. The adapted skill is
`profiles/ce/desk/skills/ce-proactive-security/SKILL.md`.

| Job (UTC) | What actually runs |
|---|---|
| Bootstrap, once | Three-read orientation; questions retained for operator confirmation |
| `*/15 * * * *` | Python checks saved baseline freshness; no model or AWS scan |
| `7 * * * *` | Hermes investigates current threat findings and recent management events with a four-read ceiling |
| `13 3 1 * *` | Hermes prepares a posture review from available evidence and confirmed context |

Open the native dashboard **Cron** page in **ce-desk** to inspect or pause jobs.
For agent output, open **Sessions → Automation → History → Resume in Chat**.
This opens the scheduled conversation, including its tool history, for follow-up.
Outputs are local Hermes cron records and are
included in the existing state checkpoint. S3 collection receipts remain separate.
An enabled schedule is not proof that a run succeeded. Inspect the completed output
and coverage before relying on it. A Spot outage skips work while compute is absent;
hourly CloudTrail lookup is not a substitute for complete trail ingestion.

For the interactive trial, resume the bootstrap conversation and ask:

> Review the bootstrap result. What did you observe, what remains unknown, and what
> one question would help you prioritize this account?

Then use ce-onboarding to confirm business purpose and ce-knowledge to publish the
context explicitly. Scheduled runs cannot approve inferred organizational policy.

## Installation

Inside the Hermes container, after backing up state, select the ce-desk home and run
the packaged `deploy/proactive/install.py --bootstrap`. It creates three named jobs
and a one-time bootstrap. Running it again preserves existing jobs and pauses.
Recurring investigations include their previous output through native Hermes
continuity, so they can identify changes. The installer adds this link if missing;
it does not change an existing custom continuity source.
Copy the two Python files together; the installer copies the heartbeat into Hermes's
approved scripts directory. Set `platform_toolsets.cron` to `skills, ce_runtime`.
Provider and key configuration stay in Hermes.

For Spot, set `proactive_enabled = true` in the Terraform inputs. Boot installs
missing jobs; it does not unpause jobs. A persistent registration marker prevents
bootstrap from being queued again on every replacement instance.

These jobs use model tokens hourly and monthly. The heartbeat uses none. Each agent
run is bounded by the existing workflow/action/time limits; there is no aggregate
daily monetary cap. No external notification delivery is configured.

## Accounts and optional integrations

Discovery does not grant access. A member account needs
`deploy/aws-single/member-read-role.yaml`, deployed by its administrator with the
exact instance-role ARN and organization ID. The host must then receive
`sts:AssumeRole` on those exact role ARNs, and the collector needs matching named
targets and allowed regions. Do not grant `arn:aws:iam::*:role/*`.
Verify each target with a small read before claiming coverage.
Organization onboarding and host permission expansion are deferred at the
operator's request. The role template is reference material, not a deployed or
validated multi-account feature.

Cost Explorer and EventBridge/SQS are not enabled in this trial. They are optional
extensions, not prerequisites. SQS requires a bounded consumer and acknowledge-on-
success behavior; merely setting a queue URL does not implement that consumer.
AWS service opt-in and regional availability still apply.

## Deliberate adaptations

The supplied proposal's shell wrapper, per-resource graph, numeric risk scoring,
full SEC1–11 scan, daily/weekly account waves and finding lifecycle database are not
claimed as implemented by installing a skill. Existing deterministic collection
and native findings are used. A missing finding is not automatically marked fixed.
Heuristics about missing SCPs, IAM users, public endpoints or resource names require
context. Application data and secret values remain outside the agent's read path.

## Trial check

On 20 October 2026, the native scheduler and heartbeat were checked on the running
Spot host. The first bootstrap reached the tool-call limit before review; its report
was retained. A focused three-read run completed with receipts and same-evidence
critique in about two minutes. It observed Config recorder status, Security Hub
availability and GuardDuty detector presence; this is not complete posture coverage.

That run did not pass saved baseline evidence into its nested investigation and
treated a business-purpose question as an unfinished criterion. The skill now
explicitly passes the saved path and keeps human questions outside technical
completion criteria. This final wording is for operator interactive review.
Hourly/monthly output quality and organization onboarding are not claimed validated.
