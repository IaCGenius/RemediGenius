# Simple remediation follow-up and resource ownership context

Research and installed-runtime inspection: 2026-10-14. Recommendation, not a claim
that RemediGenius CE already exposes task management or these additional AWS reads. No board,
dispatcher, cloud permission or customer resource was changed during this review.

## Recommended experience

After investigating a finding, offer: **"Track this on the Hermes board so we can
return to it?"** If the operator already has a change ticket, link that instead of
creating a competing change process. A declined offer does not create a card.
Do not automatically create one ticket for every imported finding.

One card holds the actionable issue, its exact resources and linked source finding
IDs. Reuse it for repeated observations of the same issue. Different resources or
conditions do not inherit a prior disposition just because descriptions resemble
one another. Several source controls may support one issue; retain their IDs.

Keep only a few user-facing stages: **Open → Waiting → Verify → Closed**. These are
RemediGenius CE meanings, not new Hermes database states: initially use native triage, blocked,
review and done, with the reason in the card. Archive concluded cards out of the
active view without deleting their history. Test exact transitions before enabling
agent writes; native worker completion rules may differ from manual board actions.

Minimum readable card content:

- What is affected: account, region, resource and finding/control identifiers.
- Latest evidence and observation time; links to S3 receipts, not pasted raw logs.
- Current proposed fix/version and expected verification condition.
- Human owner, external change reference and next review/change date if supplied.
- Current reason for waiting, next action, and closure reason when concluded.

Append material activity as dated comments: proposal revised, operator decision,
change scheduled, execution reported, reassessment result and closure. Link the
session/receipts for detail. Do not log hidden reasoning or claim every cloud
activity has been captured by a board comment. Keep prior proposals inspectable.

On return: read the card, summarize the last decision, refresh relevant evidence,
check whether configuration/source/knowledge changed, and offer continue, revise,
defer or conclude. A scheduled date is not proof a change happened.

## Closure without losing unresolved risk

| Outcome | Requirement and presentation |
|---|---|
| Fixed and verified | Fresh evidence establishes the intended condition in the stated scope; cite it. |
| False positive / not applicable | Operator decision with supporting reason and precise applicability; distinguish it from an independently proven fact. |
| Accepted risk | Operator-owned decision, scope and expiry/review date; close the remediation work with an explicit unresolved-risk disposition, never mark the control passed. |
| Resource retired | Evidence of removal and adequate visibility; a missing/denied lookup alone is not enough. |
| Duplicate / superseded | Link the surviving card or change; do not silently drop the issue. |
| Cancelled / not pursuing | Explicit operator decision and reason; say whether the risk remains. Not a verified fix. |

Inactivity never means resolved. An overdue card gets attention at the next requested
review; the operator chooses a new date, a reasoned disposition or further work.
No automatic reminders or polling are promised until explicitly configured.
Reassessment after a relevant change or expired decision can reopen or create a
linked successor; automatic reopening is not implemented today. Archiving removes
clutter, not the underlying risk or evidence. Use operator-defined retention.

This is ordinary finding/change lifecycle management adapted to a small RemediGenius CE. NIST's
patch-management guidance includes prioritization and verification; it is relevant
practice, not a certification of this design. AWS Security Hub similarly separates
workflow disposition from findings and warns that resolved/suppressed status does
not prevent later findings. Sources: [NIST SP 800-40r4](https://csrc.nist.gov/pubs/sp/800/40/r4/final),
[AWS finding workflow](https://docs.aws.amazon.com/securityhub/latest/userguide/findings-workflow-status.html).
RemediGenius CE-local card updates should not silently change Security Hub workflow status.

## Reuse Hermes Kanban, without an autonomous work queue

Hermes already supplies board tools, comments, attachments and durable task data.
Its dispatcher can start workers; board visibility alone does not grant chat tools.
Use manual tracking first and explicitly disable automatic work/review dispatch
before exposing card creation. Do not treat a human change-review card as an agent
execution request. [Hermes Kanban documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban).

Installed Hermes 0.21.7 was inspected read-only:

- Kanban source exists under `/opt/hermes/tools/kanban_tools.py` and
  `/opt/hermes/hermes_cli/kanban_db.py`.
- `/data/hermes/kanban.db` exists on the retained host volume; tables include tasks,
  comments, events, runs and attachments. The container sees `/opt/data/kanban.db`.
- Launch config has `kanban.review_dispatch: true`. Tracking-only behavior has
  not been configured or tested. The installed create tool requires an assignee.
- `ce-desk` exposes skills, clarification and RemediGenius CE tools only. RemediGenius CE's execution gate
  also rejects other tools, so enabling the toolset alone is insufficient.

Reuse the existing tools after narrowly admitting board read/create/comment and
appropriate human-controlled lifecycle actions. Do not admit worker spawning,
arbitrary attachment fetching, worktree execution or broad terminal access as a
side effect. Prefer a configuration-only route if the installed gateway can enforce
the tracking-only boundary; otherwise a small admission change is necessary. A skill
cannot override the current gate, and no separate ticket database is needed.

Keep the board on retained EBS initially; keep AWS evidence in S3. This is an honest
exception to an all-object-storage design. For recoverable S3 checkpoints use a
consistent SQLite backup/export plus attachments, not a live database-file copy
that omits WAL changes. S3 is not a live SQLite filesystem. Board-specific backup
and Spot-replacement recovery need verification; EBS existence alone is not that test.

## Understand how the resource is managed before proposing its fix

Start with allowed live resource metadata and tags. Then use the minimum relevant
source below. Present ownership as confirmed, inferred or unknown, with evidence.

| Source | What it contributes | Limit |
|---|---|---|
| CloudFormation stack | Physical-to-logical resource mapping, stack identity, template, parameters and stack events | Stack deployment is not proof of the Git repository/commit or absence of manual drift. Nested stacks may require following the owning child stack. |
| Selected Terraform repository | Resource/module definitions, desired settings and versioned source | Source alone does not prove deployment or the state/workspace that owns the live resource. |
| Selected Terraform state | Resource address/module to physical ID mapping, provider association and state revision | State can lag live AWS and does not generally prove the repository URL/commit that produced it. |
| AWS Config | Recorded configurations, relationships and changes over available history | Requires recording/coverage; does not recover unrecorded history or generally identify a Terraform module. |
| CloudTrail | Recorded API calls and caller/session/service context | Coverage/retention limits apply; userAgent or a role name alone is only an ownership clue. |

CloudFormation's DescribeStackResources can look up stack resources by physical
resource ID; GetTemplate retrieves a stack template. Read the owning stack before
offering a stack edit. Config and CloudTrail complement each other: configuration
history versus API activity; correlate them without assuming every change maps
uniquely to one event. Sources: [DescribeStackResources](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackResources.html),
[GetTemplate](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_GetTemplate.html),
[AWS Config FAQ](https://aws.amazon.com/config/faqs/),
[Config/CloudTrail correlation](https://aws.amazon.com/blogs/mt/how-to-use-aws-config-and-cloudtrail-to-find-who-made-changes-to-a-resource/).

Current RemediGenius CE supports some Config inventory/aggregator operations, but not resource
history, CloudFormation inspection or arbitrary Terraform-state object retrieval.
These are capabilities to admit and verify using existing SDK/tools, not invented
read access and not a new adapter for each question.

## Context access should be optional and scoped

Offer once when helpful: "Is this managed by CloudFormation or Terraform? I can
use the selected stack or repository to make the proposal specific." Reuse an
existing authorization within its scope; do not repeatedly ask for the same access.
Ask separately before adding a state object or expanding the account/source scope.

Prefer stack resource metadata and selected source files first. CloudFormation
templates/parameters/outputs can also contain sensitive values; do not resolve
secret references just to prepare a fix.

For Terraform, offer two paths:

1. An operator-produced minimal mapping: resource address, type, physical ID,
   provider association and state version, plus relevant non-secret configuration.
2. Explicitly authorized read of a selected S3 object/version with narrowly scoped
   S3/KMS access, processed inside the controlled execution boundary. Give the model
   only an allowlisted mapping, not the entire raw state.

State can contain secrets even when Terraform marks values sensitive. Console
masking is not redaction of the stored state. Do not upload raw state to a chat,
knowledge collection or model provider by default, or assume `terraform show -json`
is a sanitized export. Source: [HashiCorp sensitive data guidance](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).
Record the selected version/lineage/serial where available and refresh the mapping
before execution; a state mapping is not fresh live evidence.

## Small implementation order and acceptance

1. Configure and test native Kanban for manual tracking; keep auto-dispatch off.
2. Add the skill's optional tracking offer and resume/close procedure; admit only
   necessary board tools through the existing gate. Do not claim success before
   the tool confirms the saved card/comment.
3. Add targeted CloudFormation and Config history reads to the existing manifest,
   IAM and capability checks, without writing service-specific agent generators.
4. Add selected repository access; offer minimal Terraform mapping intake before
   considering direct state-object access. Validate deterministic extraction before
   giving it sensitive state. Preserve an honest unknown when access is declined.

Acceptance: save/retrieve across a new chat; no worker/model call on card creation;
waiting through a change window; duplicate grouping; revised proposal after drift;
not-applied versus applied-but-unverified; all closure reasons; expired acceptance;
archive and retrieval; Spot replacement and backup restore; stack ownership lookup;
state mapping with secret-bearing fields excluded before any model call. Tests
must distinguish real evidence from explicit draft inputs and avoid fabricated
findings. No automatic closure on age and no automatic cloud suppression.
