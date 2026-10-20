---
name: ce-proactive-security
description: Scheduled AWS security bootstrap, hourly investigation and monthly posture review; reuse saved evidence and confirmed context, report changes and access gaps.
---
# Proactive security desk

Your cloud's native security tools are powerful. We make them usable.

This procedure adapts the operator's AWS Security Agent proposal. Use the existing
RemediGenius tools and receipts, not generated CLI wrappers or unrestricted shell.
The scheduler supplies the mode. A scheduled run cannot wait for an answer: record
questions for the operator and finish. Do not grant access or publish inferred
business knowledge.

## Modes

**bootstrap:** This is an orientation pass, not a comprehensive tooling census.
Read saved account status once with ce_aws show. If returned successfully, pass its
returned path as `evidence_paths` when starting; otherwise the nested investigator
and reviewer cannot see it. Load ce-investigation, then start one investigation
with `max_reads: 3`: confirm Config recorder status, Security Hub availability and
GuardDuty availability in the configured account/us-east-1. Use exactly these three
technical criteria. A future human answer or question is not a completion criterion.
These are completion
criteria; a denied or unavailable source is a reported gap, not another discovery
branch. Use the baseline for inventory and finding counts, with its observation
time. Do not enumerate organization accounts or add Macie/Inspector/Security Lake
reads in this pass. Call next on the same workflow until terminal. The workflow
loads selected knowledge and performs review internally: do not call ce_review or
additional show/read tools while it is active. Preserve the tool budget for next.
After the terminal result, report observed scope and coverage, then ask:
"What is this account used for, and what should we protect first?"
Other organization accounts are discovered, not accessible, until a target and
successful assumed-role read exist. Never infer a standalone account from AccessDenied.

**hourly:** Load ce-investigation, ce-aws-security and ce-security-brief.
Read saved status first; pass its successful returned path as `evidence_paths`.
Use one investigation with `max_reads: 4`, at most four
cloud reads, to refresh active threat findings and recent CloudTrail management events.
Use an explicit UTC window with overlap; prefer the previous successful run's time,
otherwise the last 70 minutes. If earlier runs failed, report the uncovered interval.
Prefer Security Hub's aggregated findings; choose direct GuardDuty/Inspector reads
only for relevant gaps. Preserve source severity. CloudTrail LookupEvents does not
cover object-level data events. A page cap is not complete time-window coverage.
The workflow handles knowledge and review; keep calling next until terminal instead
of interleaving independent reads or a separate ce_review. Compare with previous
output when supplied. Lead with changed risks and the next
useful decision, not API counts. Report unchanged status briefly. Do not restart a
completed workflow to evade its budget. Unfinished checks stay explicit.

**monthly:** Load ce-security-brief and selected organizational knowledge. Review
available evidence, prior scheduled outputs and material coverage gaps. Use at most
one six-read investigation for important missing facts. Present workload and account
risks, practical trade-offs, and up to three next decisions. Ask the operator to
reconfirm purpose, critical workloads and change constraints. Do not fabricate a
monthly trend when prior comparable observations are unavailable.

**ask:** Answer from saved evidence and context first. Start a fresh investigation
only for a material gap or a user request for current observations.

## Evidence and decisions

Use ce_assessment start/next through completion for live reads. Retain the workflow
ID and actual receipt references. The runtime enforces its own smaller limits if
they differ from this procedure. Outputs are stored by native Hermes cron; report
the actual output location only if known. Do not claim a finding database, graph,
notification delivery, full SEC1–11 coverage, or a baseline file was created unless
the relevant operation actually succeeded.

Names and tags can suggest criticality, never establish it. Explain any inferred
priority. The proposal's numeric risk formula is not an AWS severity or deterministic
fact; prefer a short evidence-based ordering and explicit unknowns.
Missing observations are not proof of remediation: require a successful,
appropriately scoped fresh check before calling a condition corrected.
Public endpoints, IAM users or missing SCPs are investigation leads, not universal
policy violations. Apply the operator's confirmed exceptions within their scope.

Use ce-knowledge for staged context and explicit publication in an interactive
conversation. Use ce-remediation-plan for requested fixes and actual validation
tools before claiming validation. Applying changes stays with the operator.
Kanban decisions do not suppress AWS findings.

## Schedule and control

Heartbeat is a separate deterministic native cron script every 15 minutes; it does
not invoke a model or scan AWS. Hourly runs at minute 7; monthly at 03:13 UTC on day
1. Operators pause jobs on the Cron page. No external notification channel, SQS
consumer or Cost Explorer access is enabled by this skill.
