# Layered assessment and native session acceptance

2026-10-15 UTC (2026-10-14 local). Real AWS account, real Qwen 3.8 Max,
native Hermes UI. No synthetic findings or organization classifications.
Private traces remain in `.rgce/layered-acceptance/`.

## Source candidate

Commit `246a121`; runtime archive
`dbb2343abf987a214338346751e7e702c2d36e5d7f7d0b6c7e3f3474b1f0a7f6`.
Retained-profile upgrade created backups. All 58 integrity entries passed.
Qwen route and manual Kanban settings were preserved.

## What passed

- Native official-image registry behavior: two attached terminals reach capacity;
  a detached terminal is reclaimed by upstream code. No custom cleanup loop.
- Eight UI terminal generations completed with no observed disconnect/OOM.
  Memory: initial 981 MiB, four generations 1.314 GiB, eight 1.282 GiB, limit 3 GiB.
  The saved assessment resumed and its prior answer remained readable.
  This is bounded acceptance, not an indefinite soak or multi-user capacity claim.
- Qwen selected the existing security skill and new layered-assessment reference,
  retrieved the actual operator policy, then selected the knowledge/onboarding skill.
- Knowledge tool returned `HASH_MATCHED` plus the policy's real scope/provenance
  with content. Unknown bucket purpose remained unresolved; no invented expiry.
- Confluence was accurately described as operator export/import, not a connected
  authenticated synchronizer. Chat attachment and pasted URL were not claimed imported.
- One actual Security Hub read returned 24 ACTIVE findings: 2 critical, 2 high,
  4 medium, 16 low. Independent read-only AWS API verification matched exactly.
- Two records for the same Config control were grouped while retaining standard
  references. Missing application criticality was stated as a prioritization limit.
- No customer-cloud changes or case writes were made.
- Updated workstation launcher: existing acceptance backend and retained volume,
  explicit upgrade, 58 integrity entries passed, native login HTTP 200, session
  bound active. Test container then stopped; retained volume and AWS storage remain.
  This smoke test supplements, rather than replaces, prior workstation acceptance.

## Partial result, preserved

Session `20261015_031640_ae1291` / receipt `7935b026fea54f5aa145fe1403fac3b0`:
the final answer overstated missing Config as absence of reliable change history,
and described finding refresh too broadly as verification. Its critic also made
an incorrect objection to the correct LookupEvents data-event limitation.
These are interpretation/review failures; correct counts do not make the run PASS.

The persisted answer correctly carries an AI_CRITIQUED draft heading. During live
streaming the terminal showed answer text before that final transformed heading;
do not treat the streaming text as a verified or approved answer.

The shared critic guidance and assessment reference were clarified to distinguish
Config coverage from all other history, finding status from remediation, recorder
configuration from operation, and management event lookup from S3 data events.
Candidate `4d225f376eb923ea6931a7cc661b47247238fe6a462624694db618f23b524cd9`
was promoted for the targeted retest below. Deployment alone was not acceptance.

### Focused retest

The corrected archive was applied and the retained profile explicitly upgraded
with a backup. Session `20261015_033245_1ebedc`, receipt
`40be11d2ab9c45c69710205eb45469b2`, completed with exit 0 in 3m41s.
It preserved the correct real totals, scoped missing history to Config only,
kept unknown bucket purpose unresolved and described operator-side source intake
accurately. It still described recorder configuration plus finding refresh as a
verification path without explicitly requiring recording-status evidence. Its
low-severity grouping wording was also imprecise. Overall interpretation remains
PARTIAL; this is an AI proposal workflow requiring operator review, not certified
posture or remediation verification. Do not flatten this into a clean PASS.

Final local checks after the focused correction: repository suite 192 passed,
4 Windows skips; separate kiosk suite 30 passed. These constructed regression
tests are distinct from the real AWS/Qwen acceptance above.

## Additional real-model acceptance

### Delayed-fix retest

Session `20261015_033811_ac5d8e` reread the retained case and its corrections,
collected fresh versioning evidence (`3ec31ed297c44025b75d028a5daeff32`), and
correctly used Terraform `mfa_delete = "Enabled"` plus the resource `mfa` input.
It correctly rejected a native CloudFormation MFA Delete property, distinguished
ordinary object operations from protected version operations, and marked IaC
validation NOT_RUN. No cloud or case changes were made.

An independent operator-side check then extracted that exact resource into an
isolated, backend-disabled configuration using the existing AWS provider 5.100.0.
`terraform validate` passed. No plan/apply or credentials were used. This later
check is not something Hermes itself performed or may retrospectively claim.

The answer's final format summary nevertheless called CLI the only capable route
after describing supported Terraform, and speculated about CloudFormation reverting
an unsupported property. Record PARTIAL, with the original schema defect corrected.
The skill and shared critic now require consistent format labels and prohibit that
unsupported drift inference. Source candidate
`95c2bb2d330d5608053dc546e0dbc01a0232abc58a4275390f398be7c4917b26`
is deployed and explicitly activated, with 58 integrity entries verified and
the Qwen route retained. Its focused retest is recorded below when complete.

Do not replace original partial results with later passes. No GitHub remote exists.

### CloudTrail denominator and limits retest

Session `20261015_034203_602b37`, receipt `b72261d4160949eaaee1d3dd08544f31`:
Qwen used one cloud read capped at ten pages and correctly reported PARTIAL
coverage for the requested five-day window. It corrected an unsupported projection
and a ReadOnly string/boolean mismatch before presenting reconciled totals.
Independent AWS calls using the same window/filter/page bound matched exactly:
500 events; 493 successes (451 read, 42 write), 7 errors (1 read, 6 write),
has_more=true; observed bounds 2026-10-14T20:10:06Z to 2026-10-15T03:40:30Z.
DryRunOperation events were not counted as executed changes. The final event-name
counts also matched. No expanded cloud-read retry or generated code was used.

Outcome: RECOVERED for collection/projection/counts/coverage, with a remaining
narrative attribution caveat. The answer called a historical acceptance-role
denial this session's own denied read; it belonged to the earlier acceptance
activity, not the current read. Its current-turn read count of one was correct.
The critic disputed a correct timestamp and the observed projection failure;
the main agent retained the tool-supported facts. Critique is fallible advice.

### Final proposal correction — targeted PASS

Source `95c2bb2d330d5608053dc546e0dbc01a0232abc58a4275390f398be7c4917b26`:
session `20261015_035411_4d7b5e`, fresh versioning receipt
`5cb726f1c84247ab81d0bca2630359e9`, observed 2026-10-15T03:54:37Z.
The bounded real Qwen run exited 0. It preserved the case and its corrections,
read current configuration, and consistently supported Terraform and CLI/API
while rejecting native CloudFormation representation of MFA Delete. It explicitly
withdrew the unsupported stack-reversion inference. Terraform used string enum
values and the resource-level MFA input, with root/MFA prerequisites and plan/state
handling cautions. It did not claim to have run provider or template validation.
Reassessment required the actual versioning/MFA Delete configuration, not finding
refresh. No case or customer-cloud changes were made. PASS applies to these
targeted checks, not all possible remediation formats/resources or all earlier runs.

The final cloud profile passed all 58 integrity entries with Qwen retained. The
dashboard reconnected through the replacement tunnel and showed the retained
conversation list. Final packaging records the commit, archive checksum and private
data scan in `dist/native-preview/RELEASE.json` (local delivery metadata).

## Preview decision and remaining work

This is an operator-reviewed, single-operator AWS friend-preview candidate. The
collection, provenance, persistence and bounded-runtime checks support that scope.
Broad assessment interpretation remains PARTIAL and the CloudTrail run RECOVERED
with a narrative caveat. AI critique can itself be wrong. Those are recorded
quality limitations, not evidence that automatic assurance/remediation is ready.
Source severity, deterministic receipts and operator verification remain authoritative.
Authenticated document sync, complete framework assessment, automatic case reopening
and autonomous remediation are not shipped. Repository publication needs the owner's
destination; no GitHub remote is configured.
