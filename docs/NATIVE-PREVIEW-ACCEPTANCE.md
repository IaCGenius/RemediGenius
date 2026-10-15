# Native CE preview acceptance — 2026-10-14

Follow-up: the [longer UI rerun](UI-RERUN-2026-10-15.md) found additional proposal
errors. Read that record alongside this targeted acceptance; earlier successful
answers do not certify every future generated fix.

This record covers the workstation and AWS Spot candidate, using real Qwen calls
and scoped reads of the owner's AWS account. It does not claim a complete rerun
of the independent 18-case UI pack or a production certification.

## What was exercised

| Path | Result and evidence |
|---|---|
| Workstation installation | Official pinned Hermes container, separate Lambda/S3 backend, loopback dashboard and scoped temporary reader credentials. See [workstation acceptance](WORKSTATION-ACCEPTANCE.md). |
| Persistence | Conversation survived container replacement and offline volume restore. Cloud cases use retained encrypted EBS; evidence uses S3. These are separate recovery responsibilities. |
| Live browser investigation | Security Hub returned 24 ACTIVE findings. No MFA Delete finding was present; the model did not invent one. An initial response-key query mistake recovered after inspecting the real response. |
| Review grounding | Real browser reviews received eight bounded evidence excerpts. The critic caught an unsupported claim about enabled standards; the final answer removed it. AI_CRITIQUED means model critique, not provider validation. |
| Terraform fix | The real browser answer used `mfa_delete = "Enabled"` and resource-level `mfa`. The exact proposed HCL passed an independent `terraform validate` with AWS provider 5.100.0. That validation was performed by the acceptance operator, not by Hermes. |
| CloudFormation fix | Initial browser answer FAILED: invented `VersioningConfiguration.MfaDelete`. Corrected the existing fix skill and retested with real source context. Native CloudFormation has no MFA Delete property; a template enabling versioning alone is not this fix. |
| Source-specific proposal | Supplied the actual evidence-bucket resource from `deploy/aws-workstation/main.tf`. Qwen read the real bucket and retained the resource address, bucket reference and existing versioning setting. It did not claim to inspect an unseen repository/state. |
| Shared knowledge | Imported actual historical/current CE release documents into a selected knowledge view. Qwen read both plus metadata, identified supersession and conflict, distinguished import date from effective date, and explained which knowledge informed its answer. It did not treat CE guidance as an organization policy. |
| Saved case | Browser-created waiting case persisted on native Kanban, separate from a GuardDuty finding. No customer-cloud fix was executed. |
| Automated checks | Main suite: 190 passed, four skipped. Lambda kiosk: 30 passed. Existing check/result scripts passed; wheel built. Test doubles cover failure handling but are not evidence of cloud acceptance. |

## Final cloud and workstation retest

Cloud archive `091fc4db0acd7251f3167cee438164438ba9abfcb3576e262a7a1eeecdab87a9`
was deployed to Spot. The explicit retained-profile upgrade backed up its previous
instructions; all 56 manifest entries passed. Both saved cases survived. Browser
Kanban displayed **Orchestration: Manual**. Profiles still navigates to the native
default route, but both routes displayed Qwen; no alternate Anthropic provider or
ce-analyst profile was present.

Final workstation session `20261014_235844_2647f9` passed the real-source retest,
including the new variable declaration, honest unperformed validation and
plan/state caveat. Final cloud session `20261015_000105_dbfbe6` independently
identified the invalid saved CloudFormation property, appended a visible correction,
and reread the bucket (receipt `6973a45fdea0466088ccabfa29820577`). The condition
was unchanged and the case remained blocked. Its first case-note call omitted
required bounded fields; one retry succeeded: **RECOVERED**, not first-pass PASS.

A second saved-proposal review caught invalid CLI flags in the original case:
`--mfa-serial`/`--mfa-code` were corrected to one `--mfa "SERIAL TOKEN"` argument,
and the replacement was appended without deleting history. An independent local
CLI argument-parser check passed using `--generate-cli-skeleton input`, making no
AWS call. The follow-up skill now explicitly rechecks saved syntax before reuse.
This illustrates why a retained AI draft is not validated executable automation.

That same live test exposed an incomplete explanation of `skill_manage`: the
model saw the native banner but did not state the CE gate blocked it. The final
runtime uses one admitted-tool constant for enforcement, preflight and reviewer
context, with explicit skill guidance distinguishing discovery from permission.
The tool remains blocked; no skill mutation was attempted to discover that fact.

Final deployed browser retest `20261015_001315_1a685b` **PASS**: Qwen explicitly
said `skill_manage` is not permitted, enumerated the seven admitted tools from
preflight, and did not invoke a mutation. It read `scheduled/latest.json`, reported
the real report's time, 24-hour interval, Security Hub and Config scope, and
distinguished that snapshot from a new live collection. One critique ran. The
critic still lacked some native skill-invocation context; this bounded critique
is not a complete tool-history audit or an infallible review gate.

The committed preview archive was privacy-scanned across all 448 members, extracted
into a fresh directory, and used to rebuild the native package. Both extracted
workstation and Spot Terraform modules initialized from the installed provider
cache and passed `terraform validate`. All 70 deployed source files matched the
archive after normalizing checkout line endings. Package digests differ with line
endings: deploy the digest printed for the archive you actually upload.

The completed local acceptance container is stopped and its isolated daily
schedule paused. The main cloud daily schedule remains enabled. Recovery data and
the local named volume were retained. No remediation was applied to the observed
bucket or any customer resource.

## Corrections made during acceptance

- Create the nested knowledge-view mountpoint before starting Docker.
- Set native Kanban auto-decomposition and auto-promotion off as well as worker
  dispatch; the board must describe manual tracking accurately.
- Keep the existing fix skill authoritative about format support, root/MFA
  prerequisites, missing variable declarations and Terraform plan/state exposure.
- Preserve one runtime review heading and distinguish a critiqued draft requiring
  operator review from provider validation that was not performed.
- Add a single regression check for the contradictory draft wording observed in
  the real answer. The substantial acceptance evidence remains live AWS/Qwen runs.

The AWS [CloudFormation schema](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-s3-bucket-versioningconfiguration.html)
and [S3 MFA Delete guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/MultiFactorAuthenticationDelete.html)
support the format limitation. Provider schema inspection also found that the
Terraform `mfa` argument is not marked sensitive in the tested provider. A
sensitive variable is not a guarantee that plans/state omit its value.

## Boundaries

No actual organization exception was supplied, so conflict handling was tested
with real CE guidance rather than a fabricated customer policy. The browser used
an existing authenticated session; the fresh login form was not retested in this
cloud run. Workstation authentication was tested separately.

Daily checks collect bounded deterministic snapshots without model calls. They
do not automatically investigate, remediate, notify or close/reopen cases. The
operator returns to a case, requests fresh evidence and decides its disposition.
CloudFormation/Terraform/CLI output remains a proposal requiring appropriate
validation and the operator's change process. No autonomous fix adapter is claimed.

Private transcripts, plans, schema output, Terraform validation and original
responses are retained under the ignored `.rgce/final-release/` directory. Do not
share that directory. Share committed source with [START-HERE](../START-HERE.md).
