# Preview and publish selected knowledge

2026-10-15. Operator usability improvement; no new agent role or write tool.

## What is implemented

`python -m rgce.knowledge_publish --view PATH --config CONFIG` makes an offline
preview of an existing exported view. It lists documents/scopes, exact files and
SHA-256 values, destination, size and a token binding that content and destination.
Repeating with `--publish TOKEN` uses the operator's existing AWS credentials.

The publisher accepts only the manifest/index and listed content/metadata, checks
scope membership and hashes, rejects symlinks/path escapes and extra files, and
bounds the view to 1000 documents/32 MB. Originals are deliberately not uploaded.
The library stays local; this command publishes the selected read-only view.

It uses the maintained AWS SDK and
[S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).
The small CE wrapper adds manifest validation, preview binding and verified view
semantics that ordinary directory synchronization does not provide. No storage
framework, external SaaS connector, vector database or new credential service.
Bucket default encryption is retained rather than forced to SSE-S3.

The destination view name derives from the selected files' hashes. Existing matching
objects are read/verified and reused; conflicting objects cause failure before
further writes. Partial uploads can be retried. The command never deletes objects,
changes IAM, selects the active view or claims organizational approval. This is
application-level non-overwrite behavior, not S3 Object Lock or permanent immutability
against an authorized administrator. Readback verifies bytes at publication time.

## Real AWS acceptance

Used the two real documents already selected in the CE workspace: CE operating
guidance and the operator-supplied S3 encryption rule. No invented organization
policy or findings. A new view was published in the existing private CE bucket;
six objects were read back and verified. Result:
`PUBLISHED_VERIFIED_NOT_ACTIVATED`.

Repeated the same CLI command against S3. All six object VersionIds were unchanged
before/after, confirming this repeat did not write replacement versions. No active
view, policy, case, IAM permission or customer resource was changed by this test.
Private previews/results remain under `.rgce/knowledge-publication-*.json`.

## Local verification

Full repository suite: **202 passed, 4 skipped**. Seven publication tests also
passed after the final credential-error handling refinement. Local transport
simulations cover interrupted upload/resume, no-overwrite conflicts, unlisted
files, modified metadata/content, path escape, offline preview, wrong-token
rejection before SDK access and modified prepared bytes. These simulations are
regression tests, separate from the real S3 test above.

## Runtime guidance

The existing knowledge skill explains preview/publish versus activation and now
explicitly requests complete copyable document paths. Runtime source archive:
`948e93e5cd86ddc26b2fb4c435c88dda0fe77e7b61c407284e1af581d53ffd05`.
The CE-only source-pin plan applied with zero resources added/destroyed and three
updated. The retained profile was backed up and explicitly activated; all 59
integrity entries passed with Qwen 3.8 Max and manual Kanban retained. The publisher
itself is operator-side code, not a Hermes tool.

Real Qwen session `20261015_103251_a02db5` exited 0. It read the selected policy,
provided the complete copyable path, gave the correct operator preview command
using the actual local view/config paths, refused to invent the token, distinguished
publication from activation and identified missing per-bucket purpose classification.
Targeted guidance/citation checks: PASS. No writes were requested or made by this
model run. The prior shortened-citation result remains recorded in its own report.

The critic incorrectly called the workflow unsupported because it lacked the
retrieved skill reference. The main answer retained the source-supported workflow,
but exposed this review disagreement in its user-facing answer. This was the
review-context/usability limitation in that run; the follow-up is recorded in
[CRITIC-CONTEXT-ACCEPTANCE.md](CRITIC-CONTEXT-ACCEPTANCE.md).
AI_CRITIQUED is not independent certification.
Do not convert the targeted pass into a claim that the reviewer is fully grounded.

The replacement tunnel's login endpoint returned 200. Browser automation still
failed to initialize, so no fresh browser UI pass is claimed; the model test used
Hermes's native oneshot interface.

## Scope remaining

AWS activation still uses the reviewed deployment configuration; workstation
activation uses its existing `knowledge_dir` mount. A successful upload does not
prove the agent read it. After activation, ask for the selected index and source.
Assessment-linked knowledge-use history, authenticated Confluence synchronization
and automatic chat attachment ingestion remain separate future work.
