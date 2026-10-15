# Resume after reboot — RemediGenius CE

Updated 2026-10-15 (America/Chicago). Read this first when resuming.

## Latest MVP qualification

This supersedes older runtime/archive notes below. Baseline is us-east-1 and
Qwen 3.8 Max. See [MVP acceptance](MVP-ACCEPTANCE.md) and
[the illustrated walkthrough](MVP-WALKTHROUGH.md). Current deployed native archive:
`dc17c5cf50eb427844ba13ad94ed2fa0a16f9082180060870611af897f254705`.
Spot profile upgraded after replacement; all 59 integrity entries passed. Current
workstation profile and collector were also upgraded. Fresh public-source tests
passed on Windows and Linux. GitHub Actions remains billing-blocked; the operator
explicitly chose local verification for this preview. Do not wait on billing or
claim hosted CI success. Model-provider keys and all raw acceptance artifacts
remain private under ignored .rgce paths. No customer remediation was applied.

## Follow-up UI rerun

### Latest: critic shares loaded skill references

This section supersedes runtime/archive status below. Deployed source:
`67b72d056cf79fab67e789400cfca5c5ebdc1ed610663aab1482159c910b4248`.
The native post-tool hook captures actual skill_view results and shares them with
the critic automatically, alongside bounded CE evidence. No new operator setup.
See [CRITIC-CONTEXT-ACCEPTANCE.md](CRITIC-CONTEXT-ACCEPTANCE.md).

Full suite: 207 passed, 4 skipped. Final real Qwen run passed the targeted
publication/context checks: two loaded skill hashes exactly matched the critic
packet, two evidence excerpts, one review, no skill omission. Earlier final-answer
path typo remains recorded as PARTIAL; focused skill guidance corrected it in the
subsequent run. Prior session reference context survived Spot host replacement.
All 59 integrity entries passed; Qwen 3.8 Max retained. Login HTTP 200 and the
localhost 9121 tunnel restored. No new browser UI pass is claimed.

No acceptance model call remains running. Public CE repository:
https://github.com/IaCGenius/RemediGenius (main). Initial public snapshot
`e871b90` has the identical source tree as tested local commit `b34baec`.
The local development history remains on `codex/community-v0.1`; only the scanned
current tree was published, without its earlier history. Local `public/ce-main`
tracks `origin/main` for subsequent CE work. This is a preview, not a stable release
tag. Current source ZIP/checksum are identified by
`dist/native-preview/RELEASE.json`. Next work beyond this focused fix remains
assessment-linked knowledge-use history and simpler view activation; authenticated
Confluence sync and automatic chat attachment intake remain unshipped.

### Earlier: knowledge preview and publication

This section supersedes the source/archive status below. Cloud source:
`948e93e5cd86ddc26b2fb4c435c88dda0fe77e7b61c407284e1af581d53ffd05`.
Retained profile backed up/upgraded; 59 integrity entries passed, Qwen retained.
The localhost 9121 tunnel was restored and login health returned 200. Browser
tool initialization is still unavailable; no new browser acceptance is claimed.

Operator command `python -m rgce.knowledge_publish` previews an exported view
offline, then accepts the matching --publish token for bounded, verified S3 upload.
It does not activate a view or grant the agent write access. The real two-document
view was published to a new prefix and all six files read back. Repeat publication
left all six S3 VersionIds unchanged. Existing active knowledge remains selected.
Full suite: 202 passed/4 skipped; seven publication tests passed after the final
credential-error refinement. See `KNOWLEDGE-PUBLICATION-ACCEPTANCE.md`.

Real Qwen run `okf-publish` completed: correct commands, full citation path,
activation distinction and missing classification. Critic lacks retrieved-skill
context and made an unsupported objection; that limitation remains recorded.
No acceptance model call remains running. Private results are in `.rgce/`.
Current source ZIP and checksum are identified by `dist/native-preview/RELEASE.json`.
Next priorities: review-context grounding, assessment-linked knowledge-use history,
then simpler view activation. Confluence sync/automatic chat intake remain unshipped.

### Latest: OKF usability update

This supersedes the runtime source below. Deployed archive:
`68624e0b34f9a3a350894312001a80ba952891d3c2a0c6478462eaabe8168d0a`.
The retained profile was backed up/upgraded; all 59 integrity entries passed and
Qwen 3.8 Max remains configured. Local tunnel is restored on port 9121; its login
health check returned 200. Browser automation could not initialize, so no new UI
pass is claimed. Real Qwen run `okf-guided` completed; no model test is pending.

Read `NATIVE-KNOWLEDGE-QUICKSTART.md` and `OKF-USABILITY-ACCEPTANCE.md`.
The knowledge skill now guides one-input onboarding and explains context's effect.
Operator CLI supports inventory, explicit replacement and source references.
Replacement preserves old originals/views and inherits scope/title unless supplied.
Full suite 195 passed/4 skipped before the final inheritance refinement; six focused
library tests and an isolated real-policy refresh passed after that refinement.
No customer policy or cloud configuration was changed by the knowledge test.
Qwen's policy/onboarding answer was useful but shortened citations: record PARTIAL,
not a completed knowledge-use ledger. Exact source files and hashes remain available.

Shared knowledge publication remains an operator operation. Next usability ideas:
preview-and-publish command, assessment-linked knowledge-use history, then selected
source refresh. Do not claim direct Confluence sync or automatic chat ingestion.
The final source ZIP/checksum live under `dist/native-preview/`; use RELEASE.json
for the current commit. No GitHub destination has been supplied.

### Current authoritative continuation — 2026-10-15 UTC

The deployed and explicitly activated runtime archive is
`95c2bb2d330d5608053dc546e0dbc01a0232abc58a4275390f398be7c4917b26`.
All 58 integrity entries passed; Qwen 3.8 Max and manual Kanban remain configured.
No customer-cloud remediation was applied. Retained profile backups were created.

Read `CURRENT-CE-OFFERING.md`, the validated Archify diagram
`diagrams/ce-current-offering.html`, and `LAYERED-ASSESSMENT-ACCEPTANCE.md`.
The diagram is a timestamped snapshot; the acceptance report records later retests.
Eight terminal generations and saved-chat resume passed (about 1.28 GiB, no OOM).
The two-terminal/ten-minute overlay uses native Hermes cleanup and exact-source
hash verification. It is a compatibility overlay, not an upstream setting.
Updated workstation startup/login/integrity passed; test container is stopped,
volume retained. Repository suite: 192 passed/4 Windows skips; kiosk: 30 passed.

Real knowledge provenance/onboarding passed. Broad assessment remains PARTIAL.
CloudTrail counts/bounds independently matched AWS after projection corrections:
RECOVERED with an attribution caveat. Final remediation retest passed the targeted
format-consistency checks without claiming validation or applying changes. Keep
all original partial results. AI critique is not a deterministic approval gate.

Private named runs `priorities`, `proposal`, `cloudtrail`, `proposal-final` are
complete in `.rgce/layered-acceptance/`. No acceptance model call remains running.
Current tunnel is on localhost port 9121; its session identifier stays private.
after reboot use `tools/open-native-hermes.ps1 -WithLogin` privately.
Cloud EC2/SSM/Docker are running. Daily native assurance remains enabled.

Commit `246a121` preserves the main changes; the final follow-up commit preserves
acceptance and guidance corrections. Current deliverable metadata is
`dist/native-preview/RELEASE.json`; it identifies the exact source commit and ZIP.
No GitHub remote is configured. An asynchronous question asks the owner for a
repository URL or ZIP-only preview. Do not invent a destination or publish elsewhere.
This is an owner-reviewed friend-preview candidate, not autonomous assurance.

Everything below is historical and must not override this current status.

### Organization exception test supersedes NOT_RUN

The operator subsequently supplied a real S3 encryption rule and requested a test.
See [organization-policy acceptance](ORG-EXCEPTION-ACCEPTANCE.md). Its knowledge
view is now connected on S3 and the cloud runtime. Real Qwen policy decisions and
one bucket read passed; separate metadata retrieval was skipped, so provenance
coverage remains PARTIAL. No purpose classification or expiry was invented. Raw
test artifacts and the prior knowledge view are in `.rgce/org-policy-test/`.
The old NOT_RUN statement below describes the earlier rerun only.

The previously blocked native PTY source read has now completed: installed Hermes
hardcodes `ttl=30*60, max_sessions=16` in `web_server_chat.py` rather than exposing
the assumed environment settings there. Do not invent configuration knobs. No
memory/session-lifecycle fix has been applied by the organization-policy test.

### Immediate resume point — memory incident

The latest deployed source is
`61060624c427dbb4388fdfe9e9164fbcc77ac712c4f8b6beecf5f8a86111f383`.
Commit `f5ec9aa` preserves the main instruction corrections. Later local edits
remain uncommitted; preserve them. Do not treat the older ZIP as this final candidate.

A real container memory-limit event interrupted the saved-proposal retest at
2026-10-15 01:15:43 UTC (October 14 evening, America/Chicago). Kernel logs show a
Hermes process killed by the container memory cgroup. Container limit is 3 GiB on
the medium Spot host; subsequent memory use returned to about 570 MiB. Several
native chat sessions had accumulated during serial tests. Service remained active
but the browser lost its connection. Treat this as a runtime reliability defect,
not merely a failed answer. Do not claim the interrupted proposal retest passed.

Installed Hermes already has native PTY lifecycle controls: `PtySessionRegistry`
accepts ttl/max_sessions; `reap_idle` removes detached expired sessions and the
capacity path evicts an idle session. Inspect `/opt/hermes/hermes_cli/web_server_chat.py`
around lines 1–85 to learn its supported configuration before changing anything.
Do not invent variable names or add a custom reaper. Verify saved conversation
resumption and repeated New chat behavior after any configuration change.

The last SSM command (recorded in `.rgce/native-sketch/last-command.json`) reads
those definitions. Its submission succeeded, but fetching its result was blocked
because automatic approval review hit a usage limit. No unsafe-action verdict was
issued. Do not bypass the approval mechanism; resume elevated work when available.

Pending candidate source
`a17e5e0a26508f846f2073407cce9837f79109036ccd25637ef830f9e588f82e`
contains one additional CloudTrail denominator instruction. It was uploaded and
planned, **not applied**. `.rgce/resumed-ui/final-skills.tfplan` has the usual three
source-pin-related updates. Re-plan if adding native session configuration.

Completed original cases: 16 exercised, five PASS, ten PARTIAL, one RECOVERED;
two NOT_RUN. Owner explicitly chose to leave the real organizational-exception
case untested. Matching repository-source case also remains untested in this run.
Targeted EC2 retest passed using deterministic aggregation and independent AWS
verification. Targeted saved-fix, CloudTrail denominator and limit retests are
unfinished. Preserve baseline results rather than replacing them with later passes.

Private progress/config/scripts are under `.rgce/resumed-ui/`; its run.json points
to the external raw results. Current tunnel session is retained in the active tool
session; reopen `tools/open-native-hermes.ps1` after reboot. Complete private report,
public acceptance notes, Git commit and source ZIP only after resolving/retesting
the runtime issue. No GitHub remote is configured.

See [UI rerun](UI-RERUN-2026-10-15.md) before treating the earlier targeted
acceptance as final. A longer live investigation found additional skill-level
proposal and limit-explanation errors. Corrections and promotion are in progress;
private progress, transcripts, rollback inputs and plans are in `.rgce/resumed-ui/`
and the external test-results directory recorded by its `run.json`.

## Final native preview acceptance

Read [native preview acceptance](NATIVE-PREVIEW-ACCEPTANCE.md) and root
[START-HERE](../START-HERE.md). Both workstation Docker and AWS Spot use the same
native CE profile. Final cloud runtime source archive:
`091fc4db0acd7251f3167cee438164438ba9abfcb3576e262a7a1eeecdab87a9`.
The retained profile was explicitly upgraded with a backup; all 56 instruction/
runtime integrity entries passed. Qwen and manual Kanban settings were verified.
Both existing cases survived the Spot replacement. Earlier archive pins below
are historical, not the current deployed package.

Final real-source Qwen session `20261014_235844_2647f9` corrected Terraform variable
declaration, plan/state handling and the unsupported CloudFormation MFA Delete
path. Cloud browser session `20261015_000105_dbfbe6` appended the CloudFormation
correction to the retained waiting case and reassessed fresh evidence without
applying a fix. Private outputs and rollback inputs are in `.rgce/final-release/`.

Local acceptance compute is stopped, with its named volume and backup retained.
Its separate test-only daily schedule is disabled in the private Terraform inputs.
The main cloud CE schedule remains enabled. The cloud tunnel must be reopened
after reboot using `tools/open-native-hermes.ps1 -WithLogin` in a private terminal.
No GitHub remote is configured; no public release or hosted CI is claimed.
Final browser session `20261015_001315_1a685b` passed the admitted-tool explanation
and latest daily-report check on that final package. Both cases and three comments
on the waiting MFA case remained visible after replacement. Share the source ZIP
under `dist/native-preview/` with its `RELEASE.json`/SHA256SUMS; start at root
`START-HERE.md`. Never share `.rgce/` or the private test transcripts.

## Workstation deployment increment

The new native Docker launcher is `tools/native_workstation.py`; its isolated AWS
backend is `deploy/aws-workstation`. Read `WORKSTATION-HERMES.md` and
`WORKSTATION-ACCEPTANCE.md`. Private acceptance inputs/results/backup are under
`.rgce/workstation-acceptance/`. The test backend is `rgce-local-acceptance` and
has its own daily schedule, bucket and scoped roles; no extra EC2 was created.
At that workstation increment the cloud deployment was not changed; the final
acceptance above subsequently upgraded it. Local test compute is stopped
after acceptance; its named volume is retained. Restart with the private config
using the launcher's `run` action for ongoing credential refresh.

The tested local Qwen session survived container replacement and an offline restore
to a fresh volume. Complete UI/release gates remain listed in `V0.1-RELEASE-PLAN.md`;
do not describe this workstation acceptance as full release certification.

## Operating-loop increment (latest work)

See [operating guide](OPERATING-LOOP.md) and
[acceptance record](OPERATING-LOOP-ACCEPTANCE.md) before relying on earlier status.
Daily deterministic collection now runs independently of Spot. Native Kanban cases
retain findings/proposals and explicit closure decisions. The CE runtime admits
local ce_case tracking writes, while AWS execution remains read-only. Review uses
bounded same-session context and truthful critique labels. Default dashboard routing
uses the CE model and tool boundary. Worker dispatch remains disabled.
Live inputs, source pins, rollback archives and verification output are in
`.rgce/native-sketch/`. Never publish that private directory. Stop/disable the
schedule separately from the Spot ASG when suspending all collection.

The final operating-loop source archive is pinned to
`6f4990ab00fbc4918ebb6d3c73b0c413044befdf499b918fa3465acac182ba84`.
Real open case `t_3554b5cc` retains the Config issue and its unapplied proposal.
Read the acceptance record for final verification rather than treating the archive
pin as proof of product readiness. This repository has no GitHub remote configured.

## Prototype retirement and current host sizing (2026-10-14)

The owner requested retirement of the earlier `rgce-hermes-preview` deployment.
Its broker/console were stopped, an encrypted root-volume snapshot was requested,
and its ASG minimum, maximum and desired capacity were set to zero. The old
instance was verified terminated. Private snapshot/instance identifiers are in
`.rgce/retired-preview.json`; check snapshot completion there before relying on
recovery. Existing S3 data, secrets and IAM resources were retained, not deleted.
The private `hermes-cloud.tfvars.json` now has `running=false`; the legacy module
also caps maximum capacity at zero when disabled. Its Terraform state has not
been refreshed after the direct AWS change; refresh/plan before any future apply.
Do not restart this prototype as part of reconnecting to native Hermes.

`rgce-native` sizing assessment before migration: A live sample showed 1,159 MiB host
memory used, 6,317 MiB available, and 680 MiB for Hermes. CPU averaged 3.7% across
41 five-minute CloudWatch samples since this host launched (roughly three hours),
with a 77.3% maximum including startup. No kernel OOM entries were returned.
This supports testing t3.medium (4 GiB), not a claim of measured peak-memory safety.
Before resizing, lower the current hardcoded Docker 6 GiB limit to fit the host
with OS headroom, preserve the retained data volume, and verify startup and a real
investigation. A t3.small (2 GiB) offers less headroom and is not recommended yet.
Follow-up authorized by the owner: native ASG now offers t3.medium and t3a.medium,
using price-capacity-optimized Spot selection in the existing Availability Zone.
The new bootstrap uses a configurable 3,072 MiB container limit. Private rollback
inputs/archive and a quiesced session-volume snapshot are recorded under
`.rgce/native-sketch/pre-downsize.tfvars.json`, `source-before-downsize.zip` and
`downsize-backup.json`. See the verification addendum below before relying on it.

### Medium Spot verification

Migration completed 2026-10-14. AWS selected t3.medium; t3a.medium remains an
eligible alternative. The old native t3.large is terminated and the retired
prototype ASG is empty. Both retirement and pre-migration encrypted snapshots
completed. Terraform applied only three updates (host policy archive pin, launch
template and native ASG); no storage resources were destroyed.

Dashboard HTTP 200; 23 prior sessions present, 24 after the smoke test; all
profile integrity hashes matched when checked inside the container namespace.
Docker limit is 3,221,225,472 bytes. A real Qwen3.8-max native CLI turn completed
in about 62 seconds, reading live Config recorder configuration through ce_aws
and returning an evidence-linked answer. Receipt run:
`6827f50e2f474980b1deb600c5bd6e0a`. This was a runtime smoke test, not an exhaustive
finding-quality or concurrent-load acceptance test. Container peak during startup
and this test was 886,669,312 bytes (about 846 MiB); cgroup OOM counters were zero.
Private diagnostics: `downsize-*.json`, `downsize-plan.log`, `downsize-apply.log`,
and SSM command results under `.rgce/native-sketch/`. The model transcript is
retained at `/data/medium-model-check.jsonl` on the encrypted session volume.
Reconnect the SSM tunnel after host replacement using tools/open-native-hermes.ps1.

Latest research: [Remediation follow-up and context](REMEDIATION-FOLLOWUP-AND-CONTEXT.md)
recommends reusing native Kanban for optional manual tracking and explicit closure,
then targeted CloudFormation/Config/repository context. Installed board storage and
tools were inspected; no dispatcher, board access or AWS scope changed. Read its
tracking-only safeguards before enabling Kanban: current launch config has review
dispatch enabled and CE chat does not admit board tools.

Latest owner direction: experiment with the current system before finishing the
remaining vision. Read [Vision checkpoint](VISION-CHECKPOINT.md) for the implemented
versus planned boundary and review the owner's experiments before continuing work.
The knowledge-conflict direction below remains proposed, not a new implementation.

Skill-only follow-up: `ce-aws-security` now includes triage → AWS CLI/Terraform/
CloudFormation fix preparation → reassessment, with `references/ce-fix-preparation.md`.
The CLI-first follow-up is deployed; see [remediation acceptance](REMEDIATION-SKILL-ACCEPTANCE.md)
for live-Qwen results, corrections and remaining limits. No execution permissions
changed. Current native tools cannot clone repositories,
write patches or run Terraform/CLI validation; supplied source can guide draft edits.
It was installed through the integrity-checked profile upgrade with backups.
The previously shared preview bundle does not contain this change.

## User direction

Keep CE simple and Hermes-first: one native `ce-desk` profile, readable skills,
selected organization knowledge, deterministic collection and evidence, disposable
compute, S3 storage and a separate scoped execution boundary. Preserve the hosted
v2 work; do not replace the native experience with the older custom console.
The owner decides what to publish. No public release has been made.

Latest agreed next direction: **simple knowledge-conflict resolution**. Preserve
both sources, check whether scope/dates actually conflict, use explicit supersession
or applicable exceptions, and ask the operator only when the unresolved conflict
changes a recommendation. Save a small readable resolution record with scope,
reason, source versions, operator and review date. Allow unresolved decisions;
continue unaffected work. Revisit after relevant source/scope/expiry changes.
Do not add a separate approval committee or silently trust the newest upload.
This direction is agreed, but its native runtime implementation has not been done.

## Saved source and publication state

Repository: `C:\work\remedigenius-community`, branch `codex/community-v0.1`.
Working tree was clean before this handoff was added. Relevant commits:

- `88dca3b`: native execution gates and bounded review.
- `f0ab4ed`: grounded review and real AWS acceptance report; tested source candidate.
- `073b4a0`: CE value, extension points, proposed MCP/API/A2A and finding decisions.
- `24c1deb`: knowledge staging/use visibility and proposed control mapping.

This handoff and its README link are committed separately; use `git log -5 --oneline`
and `git status --short` to find the latest state. No GitHub remote is configured.
Local commits survive an ordinary reboot but are not an off-device backup.
The separate hosted-product repository was not modified in this work.

Shareable source preview already exists:
`dist/remedigenius-native-ce-v0.1-preview-f0ab4ed.zip`

SHA256: `50744492ac87412db45d58960e8ac19544c96d06a62d84b018857466b1c176b1`.
It contains the tested candidate, not the later product/knowledge documents or this
handoff. Rebuild a new bundle after future implementation/acceptance; do not relabel
this archive as containing later commits. `dist/` is intentionally Git-ignored.

## What runs and where

- Dedicated AWS stack/ASG `rgce-native`, region `us-east-1`; Spot host running at
  last validation. No cloud stop/change was requested for the workstation reboot.
- Official Hermes 0.21.7 container, pinned image digest:
  `sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b`.
- Deployed native source ZIP SHA256:
  `022651ca7fae49c3c9178724a129146b64bf1d77a3c03b6a63cececf8c868bc1`.
- Qwen3.8-max through the existing configured provider. Use Hermes provider routing;
  do not introduce another model transport or print credentials.
- Source evidence and selected published knowledge: S3. Hermes sessions, profile
  config and runtime audit: retained encrypted EBS. This is not an S3 session backup
  or cross-region disaster recovery. Last replacement restored 19 sessions.
- Native plugin: `profiles/native-sketch/desk/plugins/ce-runtime`.
  Tools: `ce_aws`, `ce_knowledge`, `ce_review`; skill viewing and clarification
  are admitted. Terminal/generated-code/unreviewed tools are blocked.
- Separate AWS read Lambda: `rgce-native-aws-read`; SDK/IAM manifest supports
  44 operations across 10 services. Not all operations were live-tested.

Rebooting the workstation closes the local SSM tunnel and browser automation;
it does not itself stop the cloud ASG. Cloud costs continue while resources run.
Spot may be replaced independently, so discover the instance through the ASG;
do not reuse a historical instance ID.

## Reconnect after reboot

1. Check local source status and read the acceptance report before editing.
2. Ensure your normal AWS operator login is valid (refresh it using your existing
   authentication method if expired). Do not place credentials in files or chat.
3. Run in PowerShell and leave the terminal open:

   ```powershell
   C:\work\remedigenius-community\tools\open-native-hermes.ps1
   ```

4. Open `http://127.0.0.1:9121` and select `ce-desk`. In another terminal, if needed:

   ```powershell
   C:\work\remedigenius-community\tools\open-native-hermes.ps1 -ShowLogin
   ```

   This retrieves the dashboard login; keep the displayed values private.
5. If no host is available, inspect ASG/SSM and startup first. Do not blindly
   re-provision infrastructure, delete storage, or run Terraform apply as a reconnect
   step. A cold pinned-image pull can take several minutes.

## Verification already completed

- Repository suite: 185 passed, 4 Windows symlink-dependent skips, using `.venv`.
- Separate kiosk suite: 30 passed; 38 rule cases and 7 result-view checks passed.
- Terraform validation and reviewed CE-only deployment applied.
- Clean offline profile installation in the official container passed.
- Five native UI/Qwen journeys: Security Hub investigation, reassessment,
  two-account EC2, bounded five-day CloudTrail and Macie/Security Lake coverage.
- Seven collection receipts / ten raw-normalized artifacts verified against hashes.
- Final trace used only approved evidence, knowledge, critique and skill tools.
- Source hygiene scan checked 425 files before later documentation additions.

**Not a clean narrative pass:** Qwen correctly reported the deterministic
reassessment but once paraphrased missing information about remediation as the
user saying no fix occurred. The critic also made incorrect objections to evidence
outside its excerpts. Human review remains necessary. See the acceptance report;
do not erase these failures or claim model review certifies correctness.

Macie was access denied; Security Lake returned an empty local list. CloudTrail
was intentionally partial at its page cap. These are honest environment/coverage
results, not evidence of secure organization-wide posture. Timestamp-only finding
changes were correctly detected, not counted as remediation.

## Documentation to read next

1. [Product and integration contract](CE-PRODUCT-AND-INTEGRATION-CONTRACT.md).
2. [Knowledge use and control mapping](KNOWLEDGE-USE-AND-CONTROL-MAPPING.md).
3. [Runtime enforcement](CE-RUNTIME.md) and [acceptance](CE-RUNTIME-ACCEPTANCE.md).
4. [Native quickstart](NATIVE-CE-QUICKSTART.md) and [AWS execution](AWS-READ-EXECUTION.md).

Implemented: operator knowledge intake/selected file views; skill-driven scope/date/
conflict interpretation; source-native Security Hub compliance metadata retained.
Not implemented in native CE: deterministic knowledge-use receipts, persistent
conflict resolution, automatic suppression/reopening, general control-mapping skill,
native external MCP/API bridge, A2A, or continuous reassessment scheduling.
The preserved `rgce/` console/MCP/knowledge resolver contains reusable concepts,
but is not automatically wired into the native deployment. Do not advertise it as such.

## Private local operational material

`.rgce/native-sketch/` is preserved on disk and intentionally ignored by Git.
It includes private tfvars, source ZIP, SSM diagnostics, UI screenshots/transcripts,
verification results and helper scripts. Terraform local state also needs to be
retained. Do not delete these directories or upload them with public source.

Useful private files:

- `native.tfvars.json`, `source.zip`, `ops.py` (AWS/SSM inspection helper).
- `qwen-context-final-ui.log`, `trace-current.json`, `answers-current.json`.
- `final-receipt-verification.json`, `verify-final-receipts.py`.
- `context-plan.log`, `context-apply.log` and SSM `command-*.json` files.
- `.rgce/ce-release-tests-context-venv.log`.

Use `.venv/Scripts/python.exe` for repository tests. System Python lacked document
dependencies/current SDK and produced unrelated failures; do not mistake that for
the tested environment. Some Windows async tests require execution outside sandbox
restrictions. Read commands before reusing private test/deployment helpers.

## Resume instruction

“Read docs/RESUME-HANDOFF.md. Continue with the simplest native Hermes knowledge
conflict-resolution approach, keeping readable source/version references and clear
knowledge-use explanations. Reuse existing components; distinguish proposed features
from shipped ones. Preserve v2 and the existing evidence. Test any runtime change
before updating the deployment or release claims.”
