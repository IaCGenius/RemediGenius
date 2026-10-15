# Native Hermes skill retest

Operator-authorized real AWS and Qwen testing after the skills review. No synthetic
findings, organization policies or observation dates are supplied. Private account
records and transcripts remain under `.rgce/native-sketch/` and in native Hermes
sessions; source receipts remain in the configured S3 evidence prefix.

Skill source revision: `6014d4e`. Packaged source SHA-256:
`d4260bd2b3db36e8027b898cb5e779a1f8d8655d230a3c0c1e56959aef488b9c`.
Model: configured Qwen3.8-max through native Hermes. Existing iteration limit is
unchanged. A successful source request is not automatically a successful answer.

The pinned source update was applied to the native Spot deployment. The retained
profile was backed up before its instruction files were updated. All seven live
SOUL/skill hashes matched local source; the gateway, credential-refresh timer and
S3 hydration timer were active. Startup's first one-minute readiness wait expired
while the image downloaded; no profile edit occurred on that attempt. The later
installation succeeded. No product executable code was changed in this review.

An intermediate candidate (`5cf7c29`, native session
`20261014_002202_c88487`) completed its answer but skipped ce-aws-security, queried
fields absent from the normalized projection, and repeated invalid CloudTrail and
Config next steps. It failed acceptance. Revision `6014d4e` makes the routing
explicit in SOUL and ce-aws-read and documents raw versus normalized record shapes.
The final retest uses a new conversation, not that candidate's accumulated context.

## Independent source checks

- Actual sandbox EC2 inventory and CloudTrail trail reads succeeded through the
  member role; their stored record hashes verified.
- Actual default-target Security Hub query returned 24 active findings; raw,
  normalized and receipt hashes verified.
- GuardDuty, Inspector, Access Analyzer, Config and Security Lake source calls
  returned responses whose stored hashes verified. Empty results are not findings
  and do not establish organization-wide absence.
- Macie returned AccessDeniedException, stored as ERROR with a verified receipt.
- IAM simulation retained the separation: agent credentials cannot read EC2
  directly, terminate instances or fetch secrets; executor can describe EC2 and
  cannot terminate instances or fetch secrets.
- The executor rejected a disallowed mutation operation and out-of-scope region
  before customer API execution. No customer mutation was attempted.

## Native Qwen acceptance

Deployment verified; all five scoped UI workflows completed. Run dates cross midnight UTC
on October 14 while the operator's local date remains October 13.

| Task | Required result | Result |
|---|---|---|
| Security Hub triage and selected knowledge | Correct counts/severity, scoped proposals, no invented organization policy or unsupported next-step promises | FAILED interpretation acceptance; collection, routing and knowledge distinction passed |
| Same-conversation reassessment | Fresh matching request, deterministic comparison, no invented fix | FAILED workflow acceptance; final unchanged-finding conclusion independently confirmed |
| Two-account EC2 inventory | Separate observed counts/states/receipts and coverage for both targets | PASS for requested inventory and policy-scope handling; unsolicited next-step advice not accepted as validated |
| Five-day EC2 activity | Current requested window, actual returned coverage, honest pagination and errors | Source facts/partial coverage verified; FAILED no-generated-analysis-script workflow; one scratch-script correction |
| Denied/empty sources and source limits | No denial retry, no false clean result, correct CloudTrail and Config limitations | Core checks passed; PARTIAL answer quality due to extrapolating one denial to other Macie operations |

A completed answer is reviewed against original records. The prior failed run and
the later answer with interpretation defects remain failures in the history; a
successful retest does not relabel them as clean passes.

### Security Hub result

Fresh native session `20261014_003421_3eb789`, Qwen3.8-max. Qwen loaded
ce-aws-security first, alongside ce-aws-read, shared-evidence and ce-knowledge.
It completed with 7 model API calls and 14 tool calls recorded at the end of this
turn, below the unchanged iteration cap. There was no repeated invalid SDK call
or generated collector. The SDK record-shape correction worked.

Run `647034ae21554ef6a1b895c228da8a6d`, observed
`2026-10-14T00:35:16.186246+00:00`, returned 24 ACTIVE findings. Independent
inspection confirmed 2 CRITICAL, 2 HIGH, 4 MEDIUM and 16 LOW; the exact query
completed without more pages. Qwen read the actual CE operating guidance and
correctly stated that it is not customer security policy or an organization
exception. No cloud remediation occurred.

The answer nevertheless fails interpretation acceptance:

- It said the Config gap removes available change history, despite the skill's
  explicit distinction between missing Config and unknown alternative history.
- It proposed LookupEvents to establish whether an S3 deletion succeeded, then
  added a caveat about data events. The caveat does not repair the incompatible
  proposed verification method; S3 object events need another connected source.
- It implied missing management-event alarm controls would have alerted on the
  S3 anomaly cluster, without evidence those controls cover the object activity.

The answer correctly named the missing Config status operation and preserved
source severities, but those improvements do not cancel the defects above.
Loading the right skill is necessary and was observed; compliance with every
instruction is not guaranteed by native skill loading or the execution boundary.

### Reassessment result

New run `06c0c9f54cd241cdbc16c8b842a30d03`, observed
`2026-10-14T00:37:59.689092+00:00`, repeated the exact ACTIVE query and completed
two pages. The helper returned comparable=true, response_changed=true. Independent
inspection confirmed identical finding content; only the pagination token and
request/run metadata differed. The implemented comparison excludes ResponseMetadata
but retains NextToken. It is a response comparison, not yet a stable semantic
finding comparison across paginated reads.

Qwen diagnosed the token difference and ultimately reported unchanged findings,
but generated scratch Python to do so despite the skill's instruction not to
write an analysis script. It also paraphrased "I have not told you any fix was
performed" as a user statement that no fix occurred, and retained the previous
unsupported CloudTrail recommendation. This is not a clean pass. No comparator
code was changed under the current skills-only instruction.

### Two-account inventory result

Independent S3 hash and record checks matched Qwen's inventory:

| Target | Run | Observed UTC | Returned states |
|---|---|---|---|
| default | `acd2bc3a0ebf4dc1bd095178f057bac1` | 2026-10-14 00:41:58 | 5 instances: 2 running, 1 stopped, 2 terminated |
| sandbox | `b914ce68d34c4be5bdba463d14130a29` | 2026-10-14 00:42:02 | 0 instances |

Both queries returned OK, one page and has_more=false for us-east-1. Qwen retained
separate scopes and receipts, did not equate the empty account result with security,
and did not invent organization exceptions. Its extra proposed security-group read
was loosely phrased as using instance IDs; an actual request must first resolve
group IDs or supported filters through the SDK schema. That unsolicited proposal
was not executed or validated. This pass concerns the requested inventory only.

### CloudTrail result

Run `47710ba58e0a49e4b3520404a94a2844`, observed
`2026-10-14T00:43:58.866442+00:00`, requested exactly five UTC days:
October 9 00:43:46 to October 14 00:43:46. The two-page cap returned 100 events,
PARTIAL and has_more=true. Source times span October 14 00:05:41–00:43:23 only.
Independent raw-record/hash checks matched the answer's event counts and two
RunInstances Client.DryRunOperation errors. Qwen correctly said these two calls
did not launch instances and that the complete five-day window was not retrieved.

The workflow nevertheless generated Python to parse event bodies and retried one
scratch-script failure caused by an absent Username key. That contradicts the
security skill's no-analysis-script procedure, although SOUL still permits bounded
scratch analysis: the instructions are not yet consistent enough. The final answer
also suggested that up to ten pages or daily slices would obtain full coverage;
neither guarantees exhaustion for a busy account. The supported page maximum is
a limit, not a completeness guarantee. This is not an unqualified pass.

The UI driver's final coverage prompt remained in the input field. Its stale
ready indicator was not accepted as a test pass. Coverage is rerun in a fresh
session with observed-busy-then-ready completion required; that rerun completed.

### Denied/empty-source result

Fresh session `20261014_004731_46c629` loaded both ce-aws-read and ce-aws-security.
The recorded trace contains exactly one source request per service, no denial
retry and no scratch script:

- Macie `get_macie_session`: ERROR/AccessDeniedException, zero pages, run
  `fbf0d7c14246446391746cd53f958aa5`, observed 2026-10-14 00:48:24 UTC.
- Security Lake `list_data_lakes`: OK, one empty page, run
  `ec8e8d39740a40e487bab79ad3ff631a`, observed 2026-10-14 00:48:26 UTC.

Both raw hashes were independently verified. Qwen correctly distinguished denied
from disabled, empty regional results from organization-wide absence, LookupEvents
from S3 object/old-event queries, and Config recorder configuration from recording
status. However, its missing-capabilities list broadened the one denied Macie
operation to "any Macie read." That extrapolation is unsupported. Permission must
be described at the tested operation/scope, with other operations unverified.

## Completion and remaining work

All five test prompts now have actual Qwen responses, original AWS receipts and
an independent review. The four-turn session recorded 24 model API calls and 31
tool calls; the separate coverage session recorded 5 model API calls and 7 tool
calls. These are native counters, not a measured dollar cost. No iteration limit
was raised. No customer-resource mutation or additional service was enabled.

This is not a clean acceptance pass. The next corrections are narrowly identified:

1. Resolve SOUL's scratch-analysis permission against the reusable-tool workflow.
   If an existing helper cannot answer a question, name the missing capability
   rather than silently implementing a replacement inside the investigation.
2. Keep proposed verification tied to the specific observable: management-event
   lookup cannot verify object deletion; absent Config does not erase all history;
   one denied operation does not establish all service permissions. A caveat at
   the end must not contradict a confident claim at the beginning.
3. Treat the current comparator as response-level only. Paginated finding-level
   reassessment needs a defined stable comparison excluding transport tokens,
   with source identifiers, status, scope and completeness preserved. This is an
   identified executable gap, not something a stronger prompt can repair.
4. Document the CloudTrail shapes as precisely as the Security Hub shapes. The
   normalized timeline retains EventId, EventTime, EventName, EventSource, Username,
   Resources and ReadOnly; error details remain in raw CloudTrailEvent bodies.
   Explain bounded raw inspection using the existing helper, rather than letting
   an investigation silently turn into a new parser implementation.

Only instruction/source deployment and test documentation changed in this review;
the gaps above were not hidden by changing product code under a no-code request.
The CE release decision remains with the operator.

This run does not validate every one of the 44 allowed SDK methods, organization-
wide onboarding, archived/lake query execution, arbitrary new plugins, real
customer policy exceptions, or remediation writes. Those are not implied by the
five completed workflows or the independent source checks.
