# Native Hermes: live AWS investigation

Implemented and exercised against actual AWS accounts on 2026-10-13. This document
records engineering results; the owner decides when and what to release.

## What the operator gets

One Hermes profile, `ce-desk`, can select a configured AWS account and region,
collect current records, inspect the exact S3 result, investigate it with the
model, and prepare a proposal. It reuses a small SDK execution capability for
different questions instead of generating a collector for each question.

Try: “For the default target in us-east-1, investigate EC2 CloudTrail activity
over the last five days. Use at most three pages; tell me how much is missing.”
Or: “Read current ACTIVE Security Hub findings. Preserve AWS severity, explain
your proposed priorities, cite the receipts and suggest verification steps.”
Findings sent to a model are subject to the operator's provider/data-sharing choice.

The workflow is:

1. Hermes reads the capability list and selects the user's account, region and query.
2. A temporary role lets it invoke the CE Lambda and read the CE evidence prefix.
3. Lambda validates the operation, scope and budget. Its separate read role calls
   AWS; a configured member role is assumed for cross-account reads.
4. Original responses, deterministic transformations and receipts are saved to S3.
5. Hermes reads the precise returned paths immediately, selects relevant knowledge,
   and labels its interpretation separately from native findings and tool output.
6. After an operator makes a change, repeat the same read and compare the snapshots.

## Reuse and boundaries

The implementation uses the AWS SDK's operation schemas and pagination, Terraform,
CloudFormation, native Hermes skills and the official pinned Hermes image. The
AWS security reference material comes from the AWS agent toolkit, pinned to
`2cb0fa1c2e668e1bb075028800b6b27efb95779e`; see the skill's PROVENANCE and lockfile.
The earlier v2 review classified that source CAUTION, not blanket approval. CE
imports reviewed reference text, not its executable integrations or unrestricted
administrator tools. No external security SaaS API was added.

`modules/aws-read-executor/operations.json` is the readable operation/IAM manifest:
44 operations across CloudTrail, Security Hub, GuardDuty, Inspector, Config, EC2,
IAM Access Analyzer, Macie, Security Lake and S3 configuration. A listed operation
is a supported call, not a claim that the service is enabled or live-tested.
Security Lake support here is metadata discovery, not querying lake records.

Default pagination is three pages, maximum ten. Execution has a 4 MB response
budget, approximately 55-second collection budget and a 90-second Lambda timeout.
The SDK does not automatically retry. Partial responses, errors and continuation
state remain visible. CloudTrail requires an explicit timezone-aware window of
at most 90 days; a page limit can still return only minutes of that window.

Hermes cannot use these credentials to call EC2 directly, terminate instances or
fetch model secrets. IAM independently constrains execution. Model preferences,
skills and prompts do not grant permissions. This is not a general arbitrary-code
Lambda kiosk and does not perform cloud remediation.

## One account or several

The default target is the deployment account and region. Configure
`aws_read_targets` in private Terraform inputs to add aliases with account ID,
region list and optional role ARN/external ID. For a member account, deploy
`deploy/aws-native/member-read-role.json` with the exact CE executor role
ARN and selected regions, then put its output ARN in that target configuration.
The trust policy requires the configured external ID. Inspect the template before
deployment; it grants metadata/finding reads, not customer object-content reads.

Central Security Hub or Config administrator APIs may already include other
accounts. Preserve each record's account/region; a successful central call does
not establish complete organization coverage or direct access to every member.
Organizations-wide automatic role rollout is not implemented by this addition.

## Durable evidence and selected knowledge

S3 paths under the configured workspace prefix are:

- `raw/RUN/aws-read.json`: original service pages, exact request scope and status.
- `normalized/RUN/`: deterministic CloudTrail timeline or Security Hub projection.
- `receipts/RUN.json`: collection time, scope, collector/SDK version and file hashes.
- `catalog.json`: latest query pointer, not a complete history.
- `knowledge/VIEW/`: an operator-selected knowledge-library export.

Run objects use unique IDs and conditional creation. `show --path ...` reads an
exact evidence object with a size and output-line limit, returning its SHA-256.
`compare --before ... --after ...` checks scope, completeness and ordering, then
compares responses excluding AWS request metadata. It reports changed/unchanged;
it does not certify remediation, causality or security. Ordering and source
timestamps can legitimately produce differences.

Set `knowledge_view` to the published export name. The host syncs only that prefix
to the selected runtime cache. Use `python -m rgce.knowledge_publish` to preview
and verify a new exported view before selecting it; see the
[native knowledge guide](NATIVE-KNOWLEDGE-QUICKSTART.md#preview-and-publish-to-s3).
The host mounts selected knowledge
to `/opt/data/shared/knowledge`, read-only to Hermes. CE operating guidance is
explicitly scoped to tool behavior, never a customer security baseline. The owner
has separately supplied a real S3 policy for acceptance testing; it is not shipped
as a default rule for other organizations. See [the policy test](https://github.com/IaCGenius/RemediGenius/blob/aab2f8a7c74a87fc60684e1afc8ec983fd89fd5b/docs/ORG-EXCEPTION-ACCEPTANCE.md).

Compute can be replaced: source records and selected knowledge remain in S3.
Native Hermes sessions/profile state currently survive on retained encrypted EBS,
not S3. Skills are shipped in the reviewed source archive; existing customized
profiles are preserved and require an explicit backed-up upgrade.

Build a source ZIP with `python tools/package_native_hermes.py --output
.rgce/native-source.zip`, inspect its entries, upload it to the configured bucket,
and use its digest/key as Terraform inputs. Archive timestamps are fixed solely
for reproducible builds; observation timestamps always come from live execution.

## Reproduce the source checks

Run `python tools/verify_aws_read.py --function FUNCTION --bucket BUCKET --prefix
PREFIX --region REGION --target TARGET --output .rgce/live-checks.json` using an
operator identity with Lambda invoke and CE S3 read access. It reads actual EC2,
CloudTrail and Security Hub data and verifies stored hashes; it makes no model
calls. A source ERROR gives a nonzero exit code. A bounded PARTIAL query remains
explicitly partial, not a complete scan.

## Actual acceptance results

Private raw reports are under `.rgce/native-sketch/`; private AWS records are not
checked into Git. Relevant receipts remain in the configured S3 evidence prefix.

| Check | Observed result |
|---|---|
| Native Hermes UI, real model, five-day EC2 CloudTrail request | Run `5a47e4fc40164f77b1d6494c8d92d7ee`; 150 events, three pages, PARTIAL. Model explicitly reported only about 41 minutes represented, retained requested window and cited the new receipt. |
| Selected second AWS account | Actual EC2 describe and CloudTrail describe succeeded through a new member read role. Two accounts tested; no claim of all organization accounts. |
| Security Hub ACTIVE findings | 24 actual findings; original, normalized and receipt object hashes verified. |
| Native helper immediate S3 read | Successfully read receipt `829246aca9c840f6b5339787bceb5fc4` from the running Hermes container using scoped credentials. |
| Reassessment | Two real complete Security Hub reads compared: comparable, unchanged. No cloud fix was made or claimed. |
| GuardDuty / Inspector | One detector returned; five covered resources returned across two Inspector pages. Coverage discovery is not proof of finding triage. |
| Access Analyzer / Config / Security Lake | Successful queries returned zero analyzers, zero configuration recorders and zero lakes in the selected account/region. No broader absence inferred. |
| Macie | AccessDeniedException stored with an ERROR receipt; no false clean result. |
| IAM simulation | Invoker denied direct EC2 read, EC2 termination and secret retrieval; executor allowed EC2 describe and denied termination/secret retrieval. This was policy simulation, not a live destructive attempt. |
| Replacement Spot | Native gateway became active; retained profile survived; credential-refresh and S3-hydration timers active. |
| Executor rejection | A disallowed mutation operation and an unconfigured region were rejected before SDK execution; no customer mutation was attempted. |
| Final reproducible source check | Fresh EC2 OK, CloudTrail PARTIAL (three pages), Security Hub OK; eight returned S3 object hashes verified after the final executor update. |
| Validation | Python compilation, Terraform validation and 44 operation names checked against installed SDK service models. |

The operator authorized the real Qwen test. Its first run exhausted the iteration
limit without an answer; a later run completed but still made unsupported next-step
and coverage claims. It is not counted as a full pass. See
[the skills and execution review](HERMES-SKILLS-AND-EXECUTION-CONTRACT.md) for the
instruction corrections. The subsequent [five-workflow Qwen retest](https://github.com/IaCGenius/RemediGenius/blob/aab2f8a7c74a87fc60684e1afc8ec983fd89fd5b/docs/QWEN-SKILL-RETEST-2026-10-13.md)
verified real reads and source counts but still found interpretation, scratch-script
steering and pagination-sensitive comparison defects; it is not a clean acceptance
pass. Broader central-log querying, automatic onboarding,
actual organization-exception reasoning, and remediation execution are separate
unfinished capabilities, not implied by this read path.
