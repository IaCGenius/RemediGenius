# What steers Hermes, and what enforces the boundaries

Reviewed 2026-10-13 after the live Qwen test. This update changes instructions and
documentation only. It does not add an agent framework, adapter or executable.

The system needs three distinct parts: the model chooses and explains; skills
give repeatable procedures; the execution harness validates and runs requests.
Skills are readable operating instructions, not executable security boundaries.
A different model should receive the same procedures and face the same controls.

## Existing harness, independent of model judgment

Here “local harness” means the machinery outside the LLM. Some of it runs in the
Hermes container and some in the separate AWS execution boundary.

| Part | What is implemented | What it does not guarantee |
|---|---|---|
| Native Hermes runtime | Tools, skill discovery, session history, model routing and configured iteration/retry limits | A correctly chosen investigation or accurate final interpretation |
| CE SDK executor | Configured accounts/regions/operations, SDK input validation, pagination/size/time limits, source responses and receipts | That an allowed query is the right query for the user's question |
| IAM and container access | Separate executor identity; agent can invoke it and read scoped CE evidence; shared cache read-only | That malicious source text cannot influence a model's prose |
| Deterministic evidence tools | Hashes, defined normalization, bounded JSON selection and snapshot comparison | Source authenticity, completeness beyond the recorded scope, or proof of remediation |
| Persistent storage | S3 evidence/knowledge; retained EBS for native sessions/profile state | S3 backup of all native session state |

The current native limit is 12 tool-calling iterations, not 12 total tool calls.
The 240-second run budget is a wrap-up hint, not a hard wall-clock or cost cutoff.
One corrected retry is currently a skill instruction; the SDK independently uses
one attempt per request, but that does not prevent the model issuing another
request. There is no implemented model-independent semantic answer validator or
global per-investigation AWS-call budget. Those gaps cannot be fixed merely by
claiming stronger wording in a skill.

## How the agent knows its environment

The agent should not guess it from training or prior chat. Its working context is
built from existing runtime sources:

1. Native tool catalog: which tools are actually exposed in this session.
2. Native profile/model context: which profile and configured model it is using.
3. CE capabilities response: exact configured account aliases, regions and reads.
4. Actual read receipts: whether each selected source worked, when, and with what
   filters, limits and failures.
5. Selected knowledge index and metadata: which business documents apply here.

The execution contract is now in `ce-aws-read/SKILL.md`. It is a readable map of
these authorities, not a generated inventory or an assertion that everything is
connected. There is currently no single automatically refreshed, complete
environment manifest injected into every model request. The skill must consult
the relevant existing sources, and the receipts remain the authority.

## Responsibilities of the existing skills

| Skill | Job | Finish condition |
|---|---|---|
| ce-aws-read | Establish scope, use supported SDK operations, retrieve exact records | Receipt plus requested bounded data, or a specific failure |
| ce-aws-security | Select the AWS investigation workflow and interpret source evidence | Concise evidence-backed answer/proposals with limits |
| shared-evidence | Read previously collected evidence when no fresh run was requested | Relevant receipt and files; no redundant discovery on a fresh run |
| ce-knowledge | Apply selected business context and scoped exceptions | Applicable guidance cited, or the specific ambiguity identified |
| ce-source-tools | Discover genuinely usable integrations | One configured route or a precise missing integration; no improvised adapter |
| ce-explain-review | Explain actions, failures, limits and review evidence | Traceable outcome and bounded improvement proposal |

One single CE profile uses these skills. No additional agent personas or approval
committee are required. Business knowledge answers “what matters here”; skills
answer “how to investigate”; tools answer “what happened when this request ran.”

## Defects found and corrected in the instructions

- Repeated skill/catalog exploration wasted steps even when the fresh run already
  returned exact evidence paths. Fresh and historical evidence routes are now distinct.
- A broad suggestion to prefer local CLI conflicted with the actual Lambda-only
  customer-read boundary. The configured CE AWS route now takes precedence.
- The first Qwen run guessed a Security Hub filter shape and exhausted its 12
  iterations without a summary. SDK-schema use, exact filter preservation,
  deterministic projections and a clear stopping point are now explicit.
- The second answer completed but suggested Event History for S3 object activity,
  used recorder configuration as a recording-status check, and overclaimed missing
  alternative alerting/history. The AWS workflow now explicitly forbids these
  inferences and names the missing source or operation.
- Business exceptions now require baseline, variation and applicability, without
  inventing formal approval or treating the import date as the effective date.

AWS confirms that [LookupEvents](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html)
is limited to recent regional management/Insights events. Recorder status is a
[separate check](https://docs.aws.amazon.com/config/latest/developerguide/configuration-recorder-view.html)
from recorder configuration. These distinctions are now part of the procedure.

## Acceptance before calling the skills reliable

Use the existing real Qwen transcript as a failed/partial baseline. A later rerun
must use the same task and data scope, then independently check the final answer:
counts against the response; observation versus event dates; no fabricated policy;
no unsupported source promises; no current-state claim from an old finding; and
a useful answer within the unchanged iteration limit. Reassessment, two-account
scope, denied-source handling and applicable policy exceptions need their own
observed results. A wording review is not an end-to-end pass.

After the operator requested resumption, revision `6014d4e` was deployed to the
native Spot runtime. All seven SOUL/skill hashes matched source after a backed-up
profile upgrade. Real Qwen UI retesting found that correct skill loading did not
eliminate interpretation errors or improvised scratch analysis. The deterministic
comparison also treats a rotated pagination token as a changed response.

See [the live retest record](QWEN-SKILL-RETEST-2026-10-13.md) for exact scope,
receipts, successes and failures. Product executable code was not changed during
this review/retest. Existing scratch-analysis permission in SOUL conflicts with
the security skill's stronger workflow restriction; skill loading alone does not
resolve that conflict. The test result is not a claim of full reliability.
