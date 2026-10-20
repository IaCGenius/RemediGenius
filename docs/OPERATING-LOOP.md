# Daily evidence, saved findings and remediation follow-up

## Daily checks use the selected compute

The local collector reuses the same bounded read operations and snapshot comparator
as interactive investigations. It does not call an LLM or apply fixes.

The Spot bootstrap starts daily Security Hub and Config checks. Workstation checks
are opt-in through `checks` and `interval_hours` in the private launcher JSON; see
[workstation setup](LOCAL-COMPUTE-WORKSTATION.md). A report is stored under
`scheduled/runs/` and `scheduled/latest.json` in the evidence prefix.

Ask: "Show the latest scheduled checks, freshness and what changed." A failed or
partial snapshot does not mean unchanged or secure. Read the collector logs and
observation times when a report is stale. Compute must be running for collection.
A restart can perform one overdue check; it does not replay every missed interval.
There is no separate EventBridge schedule or Lambda in this deployment.

## Keep a finding beyond its chat

After an investigation, ask "Track this finding on the board." RemediGenius CE saves a native
Kanban case with scope, evidence, proposal and remaining decisions. Use "List my
cases" or "Resume case ID". Use the dashboard's **Kanban** entry when available
under **Plugins**, or enter `/kanban` in the native **Chat** terminal. Select the
`ce-cases` tenant filter. Dashboard navigation is supplied by Hermes plugins and
can differ by interface. The case prompts work without a sidebar shortcut.
Open means triage; Waiting means blocked; Verify means review; Closed means done.
A card does not start an autonomous worker or suppress an AWS finding.

The board and sessions live in retained storage and are checkpointed to S3 every
two minutes with the rest of Hermes state. Inspect backup status. Activity since
the last successful checkpoint can be lost if retained storage is lost. Recovery
checks hashes before using a checkpoint; existing state is not overwritten.

Closure records a verified fix, operator false-positive decision, accepted risk,
retired resource, duplicate or cancellation. Accepted risk needs a review date;
it does not make an AWS control pass. Verification needs fresh evidence. Expired
review dates are shown on case review, not automatically notified or reopened.

## Prepare, validate, apply externally, reassess

The security skill can prepare AWS CLI, Terraform or CloudFormation in the
operator's chosen format, using supplied source when available. Retain the draft,
impact, prerequisites, validation result and rollback/verification steps in a case.
The Linux validator runs actual tools. Read its result: formatting/schema checks
are not an execution plan, and an AI critique is not tool validation.

The operator applies changes through their own change process. RemediGenius CE does not apply
Terraform, execute remediation CLI commands or create a CloudFormation change set.
Once the operator reports execution, RemediGenius CE rereads the affected state and recommends
closure only when the evidence establishes the intended condition.

## Review means a bounded check

Review uses same-session evidence excerpts and loaded skill context. It is not a
complete history or an automatic refresh of earlier observations. Review labels
state whether critique occurred and whether context was missing or truncated.
They do not certify correctness. The authenticated dashboard owner remains a
trusted administrator; keep its login and loopback tunnels private.
