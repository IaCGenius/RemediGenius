# Validation records

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
