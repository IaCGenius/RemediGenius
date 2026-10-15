# Daily evidence, saved findings and remediation follow-up

See [acceptance results and known gaps](OPERATING-LOOP-ACCEPTANCE.md).

This increment keeps Hermes as the interactive agent and native Kanban as its
workspace. AWS EventBridge Scheduler invokes a small deterministic Lambda, which
reuses the existing read executor and snapshot comparator. No scheduled model call,
customer-resource write, new findings database or custom web workspace is needed.

## Start with daily checks

In the native deployment's private Terraform inputs:

```hcl
schedule_enabled        = true
schedule_interval_hours = 24
```

Set the interval to 12, 6 or 1 for more frequent collection, then review/apply the
Terraform plan. Disable with schedule_enabled=false. No chat tool changes this
operator setting. Default queries are ACTIVE Security Hub findings (two pages)
and Config recorder configuration (one page), in the deployment region/default
target. This is a useful starting scope, not every security service/account.
Custom scheduled_checks may select up to four requests, each one to three pages,
using the same target/region/operation allowlist. Unknown scope fails rather than
granting access. More frequent reads create AWS storage/request charges.

Every run writes receipts through the existing reader, and a report under
scheduled/runs/ plus scheduled/latest.json in the evidence prefix. A scheduled
timestamp deduplicates delivery; concurrency is one; there is no model retry loop.
A failed/incomplete snapshot is not unchanged or secure. If a process dies, the
latest RUNNING report can remain stale: investigate the scheduled Lambda logs and
last observation time. A later scheduled invocation can make progress; there is
no automatic replay of an abandoned claim. No notification service is configured.

Ask Hermes: "Show the latest scheduled checks, freshness and what changed."
It uses ce_aws show with scheduled/latest.json. The schedule runs independently
of Spot; interactive explanation still requires the Hermes host to be available.
Pause/decommission the schedule separately when stopping compute.

## A finding can outlive its chat

Ask "Track this finding on the board" after investigating an actual issue.
Hermes uses ce_case to save a native Kanban card with exact scope, evidence,
proposal and remaining decisions. Open the native Kanban page, or ask "List my
cases" / "Resume case ID". General board worker dispatch and review dispatch are
disabled; a card never starts an autonomous model worker.

In Kanban, use the ce-cases tenant filter; enable archived items to inspect closed
acceptance/history cards. Both the default dashboard route and ce-desk expose the
same retained board. The authenticated board API was checked; this is not a claim
that every drag/drop interaction has been retested.

Open = triage; Waiting = blocked; Verify = review; Closed = done. Comments retain
proposal revisions and operator decisions. Identical exact identities deduplicate
creation. This does not automatically import every alert or suppress AWS findings.
Cards live in the native retained EBS database, not in S3. Evidence stays in S3.
The existing volume survives same-AZ Spot replacement; scheduled card backup and
cross-AZ board recovery are not implemented by this increment.

Closure is explicit: verified fix, operator false-positive decision, accepted risk,
retired resource, duplicate or cancellation. Accepted risk includes a review date
and remains risk; it does not make the AWS control pass. Verification must cite
fresh observations. The adapter enforces fields, not truth of the model's claim.
Archive only after conclusion; keep history. Expired decisions and due dates are
shown when reviewing the case, not automatically reopened or notified.

## Fix adapters: prepare, retain, apply externally, verify

The existing security skill prepares AWS CLI, Terraform or CloudFormation using
the operator's format preference. Store the chosen draft in a case comment with
scope, prerequisites, impact, validation status, rollback and verification reads.
Supplied source can guide a specific edit. No provider-specific generator is added.

CLI is operator-run; Terraform is a source/import proposal; CloudFormation is an
owning-stack edit/change-set proposal. This increment does not implement automated
apply, Git OAuth/PR creation, arbitrary repository execution, Terraform plan or
CloudFormation validation. The operator can run provider validation in their own
repository and return redacted results. Never label AI critique as provider validation.
After execution is reported, Hermes collects fresh evidence and recommends closure
only if it actually establishes the intended condition.

## Review and profile corrections

Bounded recent same-session tool excerpts persist on the retained volume and are
included in subsequent critiques. Pinned fix/follow-up references are included as
guidance, explicitly separate from AWS observations. They are not full history or fresh re-reads;
re-read older cited evidence when missing. AI_CRITIQUED means a model critique
occurred with excerpts, NOT_GROUNDED means no evidence excerpts were available,
and NOT_REVIEWED means no usable critique. None is a certification or schema check.

The upstream default dashboard route is configured with the same CE provider,
instructions and tool gate, since native navigation can select it. It may still
appear as a second UI label; it is not intended as an unrestricted second agent.
skill_manage may remain visible through upstream's skills toolset but is rejected
by the CE gate. UI button/count behavior belongs to the upstream dashboard and
has not been rewritten here. Treat the dashboard owner as a trusted administrator.
