# CE: useful capabilities and small knowledge views

**Historical implementation note.** The gaps described below are dated to this
change, not current release status. See [current offering](CURRENT-CE-OFFERING.md)
and [native acceptance](https://github.com/IaCGenius/RemediGenius/blob/aab2f8a7c74a87fc60684e1afc8ec983fd89fd5b/docs/NATIVE-PREVIEW-ACCEPTANCE.md).

2026-10-13. Implementation notes and next delivery sequence; not a release claim.

## Operator experience

One Hermes profile. Connect existing sources, select organizational context, ask a
question, obtain supported findings and a proposed next action. The operator owns
their knowledge and config; CE does not create a separate approval committee.
The first useful outcomes are AWS activity investigations, prioritization of
existing findings using business context, and repository-aware remediation plans.

The present cloud sketch still lacks agent-triggered collection. A successful
knowledge import or a new skill does not close that gap. The next vertical slice
must answer the CloudTrail/EC2 question and a different event-history question
using the same executable capability, with real receipts and limits.

## Knowledge collections implemented in this change

Use the existing CE Python environment; install its `documents` extra for PDF and
Office conversion. No model is used for extraction. Original files are copied,
not moved. Existing MarkItDown worker and format validation are reused.

```powershell
python -m rgce.knowledge_library --root ./library add --collection org/policies --file ./security-policy.md --scope 'All company accounts'
python -m rgce.knowledge_library --root ./library add --collection apps/payments --file ./payments-exceptions.md --scope 'Payments development accounts only'
python -m rgce.knowledge_library --root ./library view --collection org/policies --collection apps/payments --output ./views/payments-001
```

The sources above are operator-provided files, not shipped sample company facts.
Collections can be arbitrary nested names. Selection is exact: selecting `org`
does not silently include `org/private`. Each import produces original bytes,
`content.md` and `metadata.json` with provenance, scope and hashes. An explicit view
produces `index.md`, a manifest and selected content only. Old views remain intact.

The agent reads the index, then only relevant documents. A worker receives that
view's path, task scope and evidence references; not the entire organization library.
No vector service is required initially. Semantic search can later be a disposable
index over the same files, not a replacement truth store.

The operator can inspect everything with an editor. Direct edits to generated
content are discouraged: edit the source and re-import/rebuild. Metadata is human
readable and editable; CE does not certify its truth. There is no cryptographic
attestation or formal organizational approval claim. Supersession, expiry and
contradictory policies require explicit source guidance; automatic conflict
resolution and automatic revision retirement are not implemented in this slice.

## S3/object storage

Keep separate prefixes for `knowledge/`, `evidence/`, `repositories/` and `runs/`.
Preserve service-native raw records. Common receipt fields can identify source,
scope, time, version, inputs/outputs and errors without one universal data schema.

S3 prefixes group objects; they are not folders or permissions by themselves.
Use IAM prefix/object restrictions and selected runtime mounts when actual access
separation is required. A view limits what is provided to a task; it does not
revoke access from some other broadly credentialed tool.

Reuse standard AWS CLI for initial operator publishing and download:

```sh
aws s3 sync ./views/payments-001 s3://YOUR-BUCKET/ce/knowledge/views/payments-001/ --profile YOUR-PROFILE
aws s3 sync s3://YOUR-BUCKET/ce/knowledge/views/payments-001/ ./runtime-knowledge/ --profile YOUR-PROFILE
```

Use a new prefix per view; do not overwrite a published view. These are manual
commands, not a deployed synchronizer. Mount the downloaded selection read-only
at `/opt/data/shared/knowledge` (or explicitly name its mounted path) for the
`ce-knowledge` skill. Existing cloud evidence hydration does not yet synchronize
these knowledge prefixes; IAM and mount configuration must be connected before
claiming knowledge is live in the cloud chat.

The catalog's S3 plugin is a candidate for reuse, not installed or vetted by this
change. Its list/pull/push/delete behavior and credential model must fit the
selected permissions. No extra storage API service is required for ordinary S3.

## CLI, repositories and extensions

Prefer existing AWS CLI/SDK operations in a scoped execution environment. Hermes
can choose parameters and compose investigations; IAM, request limits and result
receipts belong outside model reasoning. Read-only access does not eliminate
query cost or data disclosure. Novel analysis may run in disposable compute with
provisional outputs; reuse reviewed procedures when available.

Use native Git for repository contents across GitHub/GitLab/Azure DevOps. Record
the commit SHA and selected directories. A repository URL plus existing Git
authentication is sufficient for ordinary reads. Do not invent a Python wrapper
to proxy `git clone`. OAuth setup, PRs, issues and reviews remain provider-specific
plugin capabilities. Do not run downloaded build hooks or repository code merely
to inspect Terraform. Snapshotting and provider OAuth onboarding are not yet
automated in the native CE sketch.

Hermes discovers installed skills and enabled plugin tools; CE's SOUL now directs
it to use that native inventory instead of treating packaged skills as exhaustive.
Installed, enabled, exposed, authenticated and permission-tested are distinct.
Refresh/restart the applicable native session after extension changes.

The native TUI currently uses an explicit toolset filter. It is now configurable
as Terraform `hermes_toolsets`; include the actual plugin/delegation toolset when
enabling one. Changing the profile's plugin toggle alone may not override this
host-level filter. No extensions are installed or automatically enabled here.

## Models and durable operator choices

Use Hermes's Models page/config for the main reasoning model, auxiliary slots
(titles, compression and other supported internal jobs), and `delegation` for
subagent work. Auxiliary `auto` generally uses the main route: it does not mean
"automatically choose a cheaper model". The main agent decides when a specialist
task helps; native routing decides which configured model runs it. Counting and
document conversion need no utility model.

No model IDs are added to this implementation. Keep the configured main model
until the operator supplies a utility route and tests it. Different providers may
have different data-handling terms; a new credential is not permission to send
every knowledge collection there.

Bootstrap now installs a missing profile but preserves an existing profile on
restart/replacement. This preserves model choices, skills, plugins and instructions.
It also means packaged upgrades require an explicit operator update, not an
automatic overwrite. Retained EBS persists this state; S3 session backup is still
not implemented. The code change is not proof of a live Spot replacement test.

## Validation and remaining integration

Validated locally: actual document worker for UTF-8 inputs; selected collection
isolation; direct content-edit detection; path traversal rejection; existing
four evidence-helper checks; Python compilation and Terraform validation.
Tests use synthetic documents, not claimed real organizational knowledge. PDF
and Office extraction are reused but were not retested in this change.

Not deployed by this change: cloud knowledge view, changed bootstrap/toolset
configuration, utility model, new plugins, Git onboarding or on-demand CloudTrail.
Build order: reusable execution/CloudTrail round trip; selected knowledge mount;
repository content; optional utility/delegation and richer plugins. Avoid another
custom agent runtime, admin console, or adapter per individual question.

## References and reuse

- Local OKF ideas: `C:/work/okf-agent-package/addon/README.md`,
  `03-injecting-okf-and-keeping-focus.md`, `12-portable-core-abstractions.md`.
  Concepts only; no organization content or runtime code copied. This collection
  layout is OKF-inspired, not a claim of full OKF schema conformance.
- [S3 prefix organization](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-prefixes.html)
- [Hermes S3 community plugin](https://hermes-agent.nousresearch.com/docs/plugins/s3)
- [Hermes model configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models)
- [Hermes plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)
- [Hermes skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
- [Git clone](https://git-scm.com/docs/git-clone)
