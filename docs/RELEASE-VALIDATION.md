# Validation records

## v0.2.0 single-compute validation — 2026-10-19

Fresh deployment from commit `8a0695a`, source ZIP SHA-256
`89cdd0aceac8afb74d64f51f93414b30974f4c16022a9acf1b07fd4e831031ae`.
Local Pi/DeepSeek executed the tests; the maintainer reviewed its recorded results.

| Check | Actual result |
|---|---|
| Regression and collector/profile checks | 184 + 6 passed. |
| Docker onboarding | Keyless model omission and keyed startup probe passed; anonymous optional UI redirects to login. Test containers stopped, volumes retained. |
| Fresh AWS setup | New Terraform state, 16 resources created, Spot instance-role collection, no Lambda. Native login showed no inherited conversations. |
| One-read Config request | Exactly one read, zero recorders returned, truthful budget-limited conclusion; receipt/raw hashes checked against S3. |
| Security Hub | 24 real active findings across two pages; explanation reconciled with raw/normalized S3 data. |
| Knowledge | Real operator policy staged, explicitly published, retrieved by hash and used in labelled policy-applicability examples. |
| Case and proposal | Real Config finding saved in native Kanban. CloudFormation lint failed once, then passed on attempt two of three. No apply. |
| Optional UI | Visible ce-desk selection, same five native sessions, reopened conversation and grounded follow-up. |
| Storage and schedule | Instance role verified; S3 receipts and deterministic 24-hour schedule inspected. Schedule correctly reported partial coverage. Private checkpoint contained five sessions, 111 messages, the case and policy. |
| New-host replacement | Passed on a new Spot host with the same retained EBS: five sessions, 111 messages, policy hash, case, dashboard credentials and model configuration preserved. Both UIs reopened the state; a real DeepSeek follow-up cited the saved policy. |

These checks exercise actual model calls and UI behavior, not just unit tests.
They do not guarantee every possible AWS query or identical model wording.
The fresh Spot used an existing model secret. Keyless Spot UI onboarding was not
repeated; the corresponding seed behavior was checked offline and in Docker.
See [actual walkthrough screenshots](WALKTHROUGH.md#fresh-single-host-examples).
Replacement used package `4cd8e320d69bc357fbcbb924750da692c30329f88e668435fa1ba68f9a2b8f13`
from commit `c885e6c`. This tested retained-EBS recovery, not an empty-volume
restore. A stale local SSM tunnel caused connection timeouts; replacing those
local tunnel processes restored access without changing CE. Shell syntax,
140 local documentation links and source-archive privacy checks passed.

The final boot package is
`01c421580a292429a6da94def5fc9ecb8882ebb70a060747edfa8da30f0aad7b`
from source commit `a8bd4b0`. The final change updated three skill Markdown files
and documentation, with no Python execution-code change. Installed skills matched
the package; the integrity manifest checked 95 files with zero missing files or
hash mismatches. Policy, sessions and case remained intact after explicit upgrade.

A targeted UI question loaded both the AWS-read and knowledge skills plus the
knowledge onboarding reference. The answer correctly described reviewed chat
notes on Spot, local `knowledge_dir` views on Docker, no Spot `knowledge_view`
input, and the deterministic local collector. The first model call did not finish
within 300 seconds; the single allowed retry completed in 241 seconds. This is a
recovered pass, not a first-attempt latency guarantee. No AWS read or publication
was requested in that question. Full regression tests were not repeated for those
Markdown-only changes.

Private raw reports are excluded from the release. GitHub Actions remains paused;
no successful hosted CI run is claimed.


## Main after v0.1.3 — 2026-10-16

The [answer contract and writing changes](ANSWER-CONTRACT.md) passed 168 local
regression tests. Four real DeepSeek v4.1 Flash checks ran in isolated local Hermes:

| Check | Result |
|---|---|
| Repeated EC2 inventory | Two completed investigations agreed on counts; returned references were valid. |
| Config configuration/status | Completed with separate fresh reads and scoped conclusions. |
| Frozen review context | All three investigations used the same packet hash within interpretation, review and finish; zero planning repairs. |
| Unavailable CloudWatch source | Capability/schema checks and direct review stopped without reading logs or substituting CloudTrail; this was not a structured-investigation run. |
| Writing quality | Partial: some metadata repeats, and the capability-gap answer contains unsolicited setup advice. |

No new native UI end-to-end or Spot deployment pass is claimed for these updates.
The live checks did not apply customer-cloud remediation. Private traces were kept
outside tracked source. The existing release tag, version and downloads are unchanged.
Source setup and packaging checks are described in the [change log](../CHANGELOG.md).

## v0.1.3 qualification

Scope: AWS us-east-1, DeepSeek v4.1 Flash, one native ce-desk profile. Both deployment
paths use official Hermes 0.21.7 pinned by digest; CE supplies skills and the runtime
boundary, not a different model runtime. Earlier releases remain immutable.

| Check | Observed result |
|---|---|
| Existing regression suite | 145 passed, including native profile, collectors, validator boundaries, knowledge and packaging checks. |
| Repeated real-model investigations | Two identical inventory requests and two identical Config configuration/status requests, each in a fresh session: 4/4 completed, same substantive scoped conclusions, no planning repairs. |
| Shared review context | All four repeats recorded the same frozen packet hash for interpretation, review and final answer; actual model recorded as DeepSeek. |
| Local native UI | WSL Bash launch, Windows-browser login, connected knowledge reading and remediation guidance exercised. |
| Actual validator repair | Native UI Terraform and CloudFormation: original FAIL, corrected PASS on attempt 2 for each. Displayed artifact bytes matched validator results. These were labelled syntax fixtures, not invented findings. |
| Spot replacement | t3.large replacement, 6144 MiB Hermes limit, completed startup tool-call probe and preserved sessions/knowledge/credentials. |
| Spot security triage | Active Security Hub page prioritized with receipt and partial-page disclosure; one bounded planning repair, then completion with the same interpretation/review/final packet. This was recovered success, not a clean first attempt. |
| Retained profile upgrade | Snapshot and profile backups first; 25 retained session/knowledge/credential files unchanged across explicit upgrade; package integrity checked afterward. |
| Provisioning/removal | Both isolated stacks created using a scoped provisioning role. Default non-empty evidence bucket survived destroy; explicit deletion opt-in removed it. Native destroy left a completed final EBS snapshot. |

The repeated cases test factual consistency and process boundaries, not identical
wording. Observation times and receipt IDs legitimately differ. This small sample
is not a statistical correctness guarantee across AWS questions. Earlier development
runs had scope-selection and unsupported-query errors; those failures were retained
privately and informed generic guidance, not erased from the test history.

Offline Terraform validation does not run plan/apply. CloudFormation lint does not
create a change set. CLI validation checks arguments, not permission or business
impact. Model commentary can still contain irrelevant qualifications or errors;
actual validator status and recorded cloud observations remain distinct.

Daily collection and Kanban are separate: collection does not automatically create
cases or trigger LLM analysis; case closure does not suppress AWS findings. Source
availability is not successful collection. Knowledge publication requires explicit
operator activation. Sessions/cases require the retained volume, independently of S3.

No customer-cloud remediation was executed. Local/live checks substitute for the
unavailable GitHub Actions run; a successful hosted CI run is not claimed. The
operator-policy module is a reviewed starting point tested for sandbox provisioning,
not a claim that CloudTrail generated a complete least-privilege policy for every
installation. Review it for your exact options and test your daily-use identity.

See [release scope](V0.1-RELEASE-PLAN.md), [limits](LIMITS.md),
[validation tools](REMEDIATION-VALIDATION.md) and [upgrading](UPGRADING.md).
Historical qualification is preserved with the earlier GitHub releases and tags.

Vendored skill references were checked against their provenance lock. The final
source preserves those bytes across Git checkout. Runtime text line endings were
canonicalized; payload comparisons excluded no executable or prompt content.

### Optional Hermes UI packaging validation (2026-10-18)

- Pinned-source Docker build passed, including TypeScript and Vite production build.
- Packaged nginx runtime served HTTP 200, passed `nginx -t`, ran as 101:101 with
  read-only root and no volume mounts. Disposable smoke-test container removed.
- Three focused tests passed: sidecar isolation, refusal to remove an unrelated
  container, and inclusion of required UI files/license in the CE ZIP.
- `terraform fmt -check` and `terraform validate` passed for aws-native.
- Earlier live DeepSeek tests of this pinned frontend plus the same profile patch
  verified CE skills, knowledge, review, sessions and refresh; see HERMES-UI.md.
- New automatic Spot bootstrap and workstation opt-in wiring have not had a full
  fresh deployment/replacement acceptance run. Existing Spot was not replaced.
- A broader existing execution-contract suite was not completed in this packaging
  pass (default temporary-directory setup errors, then a stalled rerun); it is
  not counted as passing. No CE execution-plugin code changed in this addition.
- Upstream CSS/font/optional SkillsView build warnings remain. Bots panel remains
  a known issue. Release tag unchanged.
