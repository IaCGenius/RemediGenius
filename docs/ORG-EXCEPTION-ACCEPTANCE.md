# Operator-policy acceptance — October 14, 2026 (America/Chicago)

The operator supplied a real S3 encryption baseline and a log-storage exception,
superseding the earlier choice to leave the organization-exception case untested.
The policy is private selected knowledge, **not a default CE policy**.

Follow-up provenance check: the native tool now includes adjacent metadata with
each content read and verifies the imported content hash. Real Qwen assessment
session `20261015_031640_ae1291` received `HASH_MATCHED` and the policy's actual scope.
This closes the separate metadata-retrieval gap for that content path; it does not
rewrite the original test or establish bucket classifications. See
[layered assessment acceptance](LAYERED-ASSESSMENT-ACCEPTANCE.md).

## What was exercised

Used the existing `rgce.knowledge_library` importer and selected-view builder;
preserved the prior view, retained the existing CE guidance, and added a separate
organization/security collection with source, content hash and metadata. The view
was published to its existing S3 location and hydrated into the runtime's read-only
knowledge mount. No collector or policy-specific code was added.

Ran one bounded native Hermes/Qwen 3.8 Max conversation on the existing Spot
runtime. It read the knowledge index and policy, made one real S3 default-encryption
read, inspected its receipt and called the critic once. A separate direct AWS read
confirmed the AES256 default. No resource encryption, finding or case was changed.

| Check | Observed result |
|---|---|
| Baseline and scoped variation | Correctly distinguished business-data baseline from dedicated-log exception. |
| Conditional policy decisions | Correct on log-only/AES256, business/AES256, AWS-managed KMS versus customer-managed KMS, and unknown-purpose cases. These were conditional decisions, not invented live bucket observations. |
| Real bucket | Reported observed AES256 default and unknown purpose; did not classify by name or automatically apply the exception. |
| Object coverage | Distinguished default configuration from encryption of existing objects. No object bodies were read. |
| Native findings | Did not invent, suppress or change a finding. Organization interpretation remained separate. |
| Provenance | Cited the exact policy path and hash; **partial**: the trace shows index/content reads, but no separate metadata.json read despite the request and existing skill guidance. |

Overall: **policy-decision behavior passed; provenance workflow PARTIAL**.
This does not establish end-to-end classification of real log/business buckets,
live KMS key ownership verification, expired-policy handling or conflict resolution.
No bucket classification or policy expiry was invented. The operator can supply
specific bucket purposes for the next live classification test.

Session: `20261015_024852_876413` (UTC identifier). Private source, previous view,
generated library/view, prompt, answer and operation records are retained under
ignored `.rgce/org-policy-test/`. The S3-backed selected view contains the rule for
future conversations; deleting compute does not delete that stored knowledge.
The importer completed successfully; its final local status-print expression
failed on relative versus absolute paths after publication. The stored import
record and live model retrieval verified the actual outcome; it was not re-imported.

AWS's [default-encryption documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/specifying-s3-encryption.html)
supports the distinction between changing a bucket default and encryption of
existing objects. The choice to require a customer-managed key for business data
comes from the operator's policy, not a universal AWS requirement.

The earlier native-dashboard memory incident remains a separate unresolved release
issue. This single oneshot test exited successfully; it does not prove that repeated
browser chat creation is fixed.
