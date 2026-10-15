# MVP acceptance — 2026-10-15

Baseline: **AWS us-east-1, Qwen 3.8 Max, native Hermes ce-desk**. This report
records a targeted preview qualification, not an exhaustive service/model matrix.
Earlier acceptance reports retain their failures, retries and limitations.

## Local verification replaces unavailable hosted CI for this preview

The owner explicitly chose local verification while GitHub Actions is unable to
start because of an account billing lock. No GitHub CI success is claimed.

| Check | Result |
|---|---|
| Main Windows checkout | 211 passed, 4 skipped |
| Fresh public-source export, Windows | 201 passed, 4 skipped |
| Fresh public-source export, Linux | 205 passed, none skipped |
| Deterministic rule cases | 38 passed |
| Result checks | 7 passed |
| Lambda kiosk tests | 30 passed |
| Python wheel | Built successfully, version 0.1.0rc10 |
| Archify architecture | 9/9 checks; light/dark browser inspection; no overflow at four sizes |

The ten-test Windows difference is private-identifier parameterizations loaded
from an ignored local file. Private patterns are intentionally absent from the
public export. Linux ran offline in an existing container with a clean source
copy, no AWS credentials and disposable temporary storage. Initial Linux test
setup failures (read-only test directory, missing optional dependencies and a
container-specific environment flag) were corrected before the reported run;
they were not silently counted as successful runs. No new runtime image was built.

## Cloud update and real Qwen evidence

The tested native source archive has SHA-256
`dc17c5cf50eb427844ba13ad94ed2fa0a16f9082180060870611af897f254705`.
Terraform updated five CE resources, with no resource additions or destructions.
The retained profile was backed up/upgraded after Spot replacement. All 59
profile integrity entries passed; Qwen remained selected; automatic Kanban worker
dispatch remained disabled. The SSM tunnel and authenticated native UI recovered.

The new Config recorder-status operation was exercised alongside recorder
definitions against the real default account. Both returned successful empty
lists. Separate operator AWS CLI calls independently returned zero for both.
Qwen distinguished empty successful responses from permission denial and from a
configured-but-stopped recorder, and stated the account/region/time and
customer-managed-recorder scope. It did not infer complete security coverage.

The same run read the selected real operator S3 policy. It explained **Source →
Applies because → Effect → Unknowns**: confirmed logs-only use may qualify for
AES256, business data requires a customer-managed KMS key, and unknown/mixed
purpose does not automatically receive the exception. No real bucket purpose,
policy effective date or expiry was invented. AWS facts were not rewritten.

The review audit confirmed seven evidence excerpts and the exact hashes of both
skill results read by Hermes. One Qwen critique returned AI_CRITIQUED with no
skill omission. This is bounded model critique, not proof of correctness or
provider validation. Private transcripts and account identifiers are not included.

## Operator walkthrough

The current workstation profile upgraded successfully on its retained Docker
volume. Real AWS checks confirmed that the container identity cannot directly
describe EC2, while the bounded collector and scoped S3 receipt retrieval work.
The deterministic schedule completed two checks; dashboard login and the native
Kanban API passed. A real Qwen run collected fresh Config definitions and returned
an AI_CRITIQUED answer. Its report correctly reflected the then-older workstation
backend manifest. The backend was subsequently updated (two resources in place,
no additions/destructions), and the new recorder-status read returned OK. That
last status check was a direct collector check, not a second Qwen generation.

The real login form and ce-desk selector were captured without credentials or
session identifiers. See [the walkthrough](MVP-WALKTHROUGH.md). The updated native
UI submitted a daily-check/case-list request and returned the existing schedule
report and retained cases. Its critic could not verify all details of a large
case-list excerpt; the final response disclosed that disagreement. Complete case
details should be fetched individually before using a stored proposal. Review
context remains bounded, not full transcript replication.

A separate UI session reopened only the retained Config case, fetched fresh
definitions and status, and deterministically compared the definition snapshot
with the older receipt: UNCHANGED. Hermes corrected the case's obsolete claim
that status reads were unavailable, kept missing role/scope/delivery choices
explicit, and did not modify the case or AWS. Its global-IAM recording flag
guidance was checked against the [AWS RecordingGroup reference](https://docs.aws.amazon.com/config/latest/APIReference/API_RecordingGroup.html).
The walkthrough includes an inspected identifier-free crop of these decisions.

One historical S3-case follow-up was not rerun: automatic approval review blocked
reading it into the model because it contains an access-key identifier. This is
an explicit test limitation, not a pass. Earlier correction acceptance remains
in [the operating-loop report](OPERATING-LOOP-ACCEPTANCE.md).

## Preview limits

Proposals are prepared for operator execution. CE does not apply customer fixes,
certify generated IaC, ingest every AWS log format, automatically enroll accounts,
or run autonomous board workers. Selected knowledge publication/activation is an
operator command workflow. Cases/conversations require their retained volume;
S3 evidence alone does not restore them. Daily checks are bounded collection,
not continuous autonomous security assurance.

Use [the capability matrix](AWS-MVP-CAPABILITIES.md) to distinguish implemented
operations from populated-source live testing. Other models and regions are
configurable but not qualified by this preview.
