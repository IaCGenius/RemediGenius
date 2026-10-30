# Release validation — RemediGenius Community Edition

## v0.6.0 (2026-10-30)

Validated on the release branch `release/v0.6.0` on the maintainer's Windows workstation, and on throwaway AWS Spot
stacks in one real AWS account, us-east-1. Every stack was deleted at the end of its run, bucket included. The account is
a member of an organization with three other accounts; they remain uncovered. Configuration: Hermes
`nousresearch/hermes-agent:stable@sha256:444b4259…` (0.21.7), model `deepseek-v4.1-flash`, OCSF 1.9.0, PyIceberg 0.12.0,
and a host image baked per release (`deploy/ami`, `ami-0dc48c08564e17790` for `0.6.0`, baked from the release archive
`4aea9037…`).

### Offline and local profile

| Check | Result |
| --- | --- |
| `pytest tests` (Windows, Python 3.12; no live AWS) | **736 passed, 7 skipped** |
| On-disk local Iceberg profile (create, write, read, reconnect, schema evolution) | passed |
| Local maintenance (compaction, snapshot expiry, orphan cleanup) and commits during maintenance | passed |
| Crash/rebuild (`test_storage_live.py`): delete the cache, rebuild from current-state tables; uncommitted scan needs a rerun; commit without acknowledgement not duplicated; unreachable store blocked | passed |
| CE-16…CE-23 reducers (membership, receipts, verification, relationships, lineage, rollout, attestation, views) | passed, including the 1,000-target fixture at 930 verified / 20 awaiting verification / 50 open, and every attestation failure mode |
| CE-02…CE-09 lifecycle, collection and durable-path regressions | passed |
| `tools/demo.py` | synthetic board + IaC match, no AWS or model |
| `terraform validate` of `deploy/aws-single` | valid |

### AWS Spot (fresh stack, destroyed after the run)

Three runs, each on its own stack and image, all destroyed (20 resources, bucket included):

| Run | Result |
| --- | --- |
| `rgce-v060-gate` | **53 of 54** — the plugin manifests shipped `0.5.0` (defect 1) |
| `rgce-v060-gate2` | **54 of 54** on image `ami-0445cfd93d63d8dd8`, archive `8d450f99…`, but that archive was not reproducible from the commit (defect 3), so this run is superseded |
| `rgce-v060-gate3` | **54 of 54 PASS, 0 FAIL** on image `ami-0dc48c08564e17790`, archive `4aea9037…` — **the run this release rests on** |

| Check | Result |
| --- | --- |
| `terraform apply` from nothing | 20 resources; cloud-init finished at 265 s (`Up 264.75 seconds`) |
| **Baked boot path** | the cloud-init log carries `baked image: release archive already verified 4aea9037…` — the image's archive was used, not downloaded |
| Host and boundary checks (`tools/spot_release_test.py`) | **54 of 54 PASS**, 0 FAIL |
| rgtriage version / core plugins / skills | 0.6.0; `rg-triage`, `rg-knowledge` and `rg-github` all report 0.6.0; five skills load |
| First scan and board | board produced for the stack; report names the account and coverage |
| Raw evidence and Iceberg facts | one `raw/` object for the check; `warehouse/` present; `history` returned a **non-null snapshot** and **outbox 0** |
| Later-CE surfaces on the real stack (new checks) | `campaign` query answered from the committed tables; `history --timeline` returned 5 events; the bounded graph view answered with its own state; **`computation_receipts` exists with its 19 columns** |
| Dashboard (Playwright, Chrome) | Knowledge tab renders 39 concepts; GitHub tab renders and offers Connect GitHub; no browser errors or failed API calls |
| Agent | "hi" answered from the live board (11 P1 issues, two GuardDuty S3 P1s named); recorded, not judged |
| Boundaries | no WebUI/API exposure, GitHub key isolated, operator token gate, validation user cannot read the key or metadata, Kanban off, card filed for people |
| Teardown | `terraform destroy` removed all 20 resources, bucket included |

Defects found and fixed during this validation:

1. **Profile and plugin manifests shipped 0.5.0.** `rg-triage`, `rg-knowledge` and `rg-github` reported `0.5.0` at boot
   because `plugin.yaml`, the dashboard `manifest.json` files and `profiles/remedigenius/distribution.yaml` were not
   bumped with the package. Fixed by bumping them and adding
   `test_every_declared_version_is_the_package_version`, which fails when any declared version differs from
   `rgtriage.__version__`.
2. **The gate could not tell which first-boot path ran.** The gate now requires the baked-archive line in the
   cloud-init log, so a silent fallback to downloading is a failure instead of a slower pass. This is what the
   "baked boot path" row above asserts.
3. **The archive was built from the working copy, not the commit.** Seven files my edits had left with CRLF shipped that
   way while git held LF, so the image was baked from an archive that a fresh build did not reproduce
   (`8d450f99…` versus `395e2877…` at the same commit). It was found by comparing the rebuilt digest with the baked one
   before tagging, not by any check. `tools/package_release.py` now reads the committed bytes with `git cat-file --batch`
   and refuses an unstaged file, `tests/test_deployment_split.py` reproduces the CRLF case in a temporary repository, and
   `docs/TESTING.md` states the invariant: **the archive baked into the image must be the archive you publish**.

Boot time, stated precisely: 265 s is **cloud-init's own counter** at "RemediGenius-CE ready" on the baked image. It is
not comparable to the 137 s figure measured earlier for "boot to desk socket"; this release did not re-measure that
boundary the same way, and the two numbers should not be quoted interchangeably.

Not validated: a real S3 or Glue outage during a live scan or decision (local fault tests only, no AWS fault injection);
Spot replacement and rebuild from S3 (local on-disk rebuild tests only); a full campaign lifecycle on AWS (see below);
real GitHub publish/merge/reconcile; the full OCSF schema beyond the pinned CE subset; other regions or models; the three
uncovered accounts; AWS cost of raw retention.

**The campaign path is plumbing-proven, not lifecycle-proven.** The gate shows that the campaign tables, the campaign
query, the timeline, the graph view and the attested-count table work on a real stack. Nothing yet calls
`rollout.derive_campaign` from a scan, so no campaign was created, approved, deployed or reconciled on AWS; that logic is
covered by the local fixtures above (including the 1,000-target scenario) and by `docs/CAMPAIGNS.md`. Treat "campaigns
work" as "the reducer and the storage work", not "a campaign was run in production".

## v0.5.0 (2026-10-29)

Validated on the release branch on the maintainer's Windows workstation, and on throwaway AWS Spot stacks in one real
AWS account, us-east-1 — the last of them built from the merged release commit `c9d1a90` that carries the `v0.5.0` tag.
Every stack was deleted at the end of its run. The account is a member of an organization with three other accounts;
they remain uncovered in this run. Configuration: Hermes `nousresearch/hermes-agent:stable@sha256:444b4259…` (0.21.7),
model `deepseek-v4.1-flash`, OCSF 1.9.0, PyIceberg 0.12.0.

### Offline and local profile

| Check | Result |
| --- | --- |
| `pytest tests` (Windows, Python 3.12; no live AWS) | **624 passed, 7 skipped** |
| On-disk local Iceberg profile (create, write, read, reconnect, schema evolution) | passed |
| Local maintenance (compaction, snapshot expiry, orphan cleanup) and commits during maintenance | passed |
| Crash/rebuild (`test_storage_live.py`): delete the cache, rebuild from current-state tables; uncommitted scan needs a rerun; commit without acknowledgement not duplicated; unreachable store blocked | passed |
| CE-02…CE-04 lifecycle regressions (truncated absence, unknown visibility, tracked account, persisted failed attempt) | passed |
| CE-07 collection scopes, raw page recording and resume, including concurrent source scopes | passed |
| CE-08 episode reducer (observed vs ingested, applied receipt, first closure, recurrence, suppression/manual closure) | passed |
| CE-09 durable scan/decision path: no `latest.json`, `decisions.json` or `history/` written; legacy state refused | passed |
| `tools/demo.py` | synthetic board + IaC match, no AWS or model |
| `terraform validate` of `deploy/aws-single` | valid |

### AWS Spot (fresh stack, destroyed after the run)

| Check | Result |
| --- | --- |
| `terraform apply` from nothing | 20 resources; boot finished in 298 s |
| Host and boundary checks (`tools/spot_release_test.py`) | **49 of 49 PASS**, 0 FAIL |
| Tightened IAM revalidation (`rgce-storage-quick`, 228889e) | **45 of 45 PASS** with browser/chat skipped; raw, warehouse, snapshot and outbox checks included; stack destroyed |
| Publication revalidation (`rgce-release-v050-final`, `c9d1a90`, the merged commit carrying the tag) | **49 of 49 PASS**, 0 FAIL; boot 341 s, 11 minutes end to end; the same checks as the full run, stack destroyed |
| rgtriage version / services / core plugins / skills | 0.5.0; desk, Hermes, validation and scan timer active; core plugins at 0.5.0 |
| First scan and board | board produced; report names the account and coverage |
| Raw evidence | object under `raw/` in the stack bucket, exactly one for the check |
| Iceberg facts | `warehouse/` objects present; `rgtriage history` returned a **non-null snapshot ID** and **outbox 0** |
| Dashboard (Playwright, Chrome) | Knowledge tab renders 39 concepts; GitHub tab renders and offers Connect GitHub; no browser errors or failed API calls |
| Agent | "hi" answered in 24 s with the live attention board, blind spots and next actions (recorded, not judged) |
| Boundaries | no WebUI/API exposure, GitHub key isolated, operator token gate, validation user cannot read the key or metadata, Kanban off, card filed for people |
| Teardown | `terraform destroy` removed all 20 resources, bucket included |

Defects found and fixed during this validation: PyIceberg called `glue:CreateDatabase` even though Terraform had made the
database (the role is denied that call in this account); collection worker threads shared one SQLite connection; Access
Analyzer pages contain Python datetimes; a resource `details` dict was written into a string column; PyArrow
`from_pylist` mishandled a nested OCSF struct with a map; the Hermes plugin enable raced the container start.

After the first full run, the Glue grant was tightened: `CreateDatabase` was removed and explicit denies were added for
database deletion, crawlers, jobs, development endpoints, security configurations and catalog resource policies. A
second fresh stack (`rgce-storage-quick`, commit `228889e`) passed all 45 host/storage/boundary checks with browser and
chat skipped; it also committed a non-null history snapshot with an empty outbox and was destroyed. The full 49-check
run (commit `fb1392d`) remains the source for the browser and chat evidence.

Before publication, the merged release commit `c9d1a90` was checked once more from its own build: a third fresh stack
(`rgce-release-v050-final`) passed **49 of 49** checks with browser and chat included, booted in 341 s, committed a
non-null history snapshot with an empty outbox, and was destroyed (20 resources, bucket included). The v0.5.0 release
assets were built from that same commit; their checksums are in the release's `SHA256SUMS`.

Not validated: a real S3 or Glue outage during a live scan/decision (covered by local on-disk fault tests, not AWS
fault injection), replacing the Spot instance and rebuilding from S3 (covered by local on-disk rebuild tests), real
GitHub publish/merge/reconcile, the full OCSF schema beyond the pinned CE subset, other regions/models, the three
uncovered accounts, and AWS cost of raw retention. A local-profile pass is not a claim about AWS durability or cost.

## v0.3.0

Validated 2026-10-21 by the maintainer's agent session against one real AWS account (us-east-1), with the operator's
approval for the deployments and the account changes listed below. Raw evidence (screenshots, logs, transcripts) is kept
privately; account identifiers are omitted here. Earlier releases' records are in the git history at their tags.

**Configuration:** Hermes `nousresearch/hermes-agent:stable@sha256:444b4259…` (0.21.7), model `deepseek-v4.1-flash` on an
OpenAI-compatible endpoint, AWS us-east-1. Sources enabled in the account: Security Hub (CIS + FSBP), GuardDuty, Inspector
(EC2/ECR), plus IAM Access Analyzer and AWS Config, enabled for this validation.

## Offline

| Check | Result |
| --- | --- |
| `pytest tests` (Windows, Python 3.12; tests never reach AWS) | 128 passed, 1 skipped (symlink case needs Linux) |
| Scale: 40,000 Inspector + 3,000 Security Hub findings through the CLI (`test_rgtriage_scale.py`) | ~1 s; 23 Inspector detail pages; Security Hub read without Inspector copies; 5 MB state; board < 8 KB; newly enabled source = baseline, no alert storm |
| Durable storage (`test_durable.py`) | round trip, live SQLite copy, unchanged-skip, no overwrite of live state, tamper rejection, retention, lineage protection (`DIVERGED`), read-only homes |
| `python tools/demo.py` | synthetic board + IaC match, no AWS or model |
| `terraform validate` of `deploy/aws-single` | valid |

## Docker workstation (`tools/workstation.py`, Windows + Docker Desktop)

| Check | Result |
| --- | --- |
| Start from nothing | desk image built, both containers up in about 1 minute |
| Scan through the socket from inside Hermes | 24 findings, ~11 s |
| Credential boundary | Hermes container: boto3 `NoCredentialsError`; desk state read-only; only `/opt/data/proposals` writable; write API calls refused |
| IAM reads | worked after switching from GetSessionToken to the profile's own credentials (GetSessionToken cannot call IAM without MFA) |
| Fix validation | an agent-style proposal validated against `deploy/aws-single` (`terraform validate` in the desk container) |
| Model | "hi" → prioritized briefing (`deepseek-v4.1-flash`) |
| Durability | after a decision and a chat, **all Docker volumes were deleted**; restart restored both homes from the local folder (decision and session present) |
| Dashboard (Playwright, Chrome) | sign-in → profile `remedigenius` selected → "hi" produced the board in the browser chat |
| Decision approval | the desk's decide call showed Hermes's "approval required" prompt with Allow once / session / always / Deny; after Allow once the decision was recorded with the user's words |

Defects found and fixed during these runs: an empty restored home was skipped because setup had created folders;
a fresh home could replace good checkpoints (lineage protection added); the Hermes home was not checkpointed because
it is read-only to the desk (lineage moved out of the home); Hermes only allows writes under `/opt/data` (proposals moved).

A later Spot cycle found that chat sessions could be lost on restore. Two causes, both fixed and covered by tests:
a database locked while Hermes started or stopped was silently left out of a checkpoint that then became the latest,
and WAL-mode databases could not be opened read-only when their `-shm` file was missing. Now databases are retried,
copied with their WAL through a private snapshot when needed and integrity-checked, and a checkpoint that still
misses one is reported `INCOMPLETE` and never uploaded. After the fix, a full Docker-volume wipe kept 4 of 4 sessions.

## AWS Spot (`deploy/aws-single`, fresh stack)

| Check | Result |
| --- | --- |
| `terraform apply` from nothing | 18 resources; the model secret's customer-managed KMS key detected and granted without input |
| First boot | ready on the first attempt (~5 min) |
| Identity | desk reads as the audit role; the instance role has no security read permissions |
| Boundaries | Hermes container: no credentials, instance metadata blocked by the egress firewall, desk state read-only, proposals writable |
| Sources | Security Hub, GuardDuty, Inspector, Access Analyzer, Config, CloudWatch read OK; Health `not_available` (no Business support) |
| Live findings | Access Analyzer external-access findings (federated vs cross-account trust classified), Config rule evaluations, GuardDuty and Security Hub. Inspector produced live CVE findings on test instances; they closed when those instances were terminated, and the desk correctly shows only `ACTIVE` findings |
| Dashboard over the SSM tunnel (`tools/open-remedigenius.ps1`) with Playwright | sign-in, profile `remedigenius`, "hi" → briefing; the agent also used a live read to check Config in another region |
| Decision approval | approval prompt shown; decision recorded after Allow once |
| Alerts | `security-watch` Hermes cron job (no model) delivered "1 new P1/P2 security finding(s) …" to local cron output |
| Durability | instance terminated without any manual step (the Spot reclaim path); the replacement restored both homes from S3: chat sessions (2 of 2 after the checkpoint fix), decisions, model setting, alert job, dashboard login; no skipped or refused checkpoints |
| Upgrade | rebuilt package → `terraform apply` → instance replaced; state restored, new code active |
| Delegated administrator | org-wide Inspector read through the account's real Inspector delegated-admin rights (`org_wide`, status ok) |
| Member read role | `member-read-role.yaml` deployed with CloudFormation; the instance role assumed `RemediGeniusReadOnly` (org-scoped `sts:AssumeRole`), scanned all six sources and read CloudTrail through it; a write call through it was refused |
| Outside the organization | assuming the same role name in an account outside the organization was denied by IAM (`aws:ResourceOrgID`); the scan reported it as a coverage gap and continued |
| Terraform → desk profile | member accounts set in Terraform after first boot were merged into the restored `triage.yaml` without changing operator values |

## Automatic account onboarding (added after the Spot runs above)

| Check | Result |
| --- | --- |
| `rgtriage onboarding` and scan, live, on the Docker workstation | organization detected; Inspector delegated-administrator rights detected without configuration (org-wide Inspector view switched on automatically); 4 organization accounts classified as read fully / findings only / not covered; board `Accounts:` line shown; StackSet command filled in with the desk identity and organization id |
| Agent in the dashboard (Playwright): "Which of our AWS accounts do you cover, and what do I need to do for the others?" | called `onboarding`, explained the coverage per account, gave the filled-in StackSet command, and offered to re-scan once it is deployed |
| Unit tests (`test_onboarding.py`) | delegated administrator without account listing; member account with listing; standalone; newly onboarded reported once; configured accounts not re-probed; reads covered by the administrator view not repeated; account listed by id uses the member role |
| `member-read-role.yaml` | `aws cloudformation validate-template` OK (`TrustedPrincipalArn`, optional `OrganizationId`) |

## Knowledge (OKF) and the Knowledge tab (validated 2026-10-22)

| Check | Result |
| --- | --- |
| Unit tests (`test_knowledge.py`) | OKF parsing (unknown keys kept, anchors/aliases/tags/duplicate keys refused), trust tiers incl. bare `verified`, staleness, `index.md` with `okf_version`, newest-first `log.md`, validation, graph, search; shipped bundle conformant with every link resolving; reviewed Application/Account/Goal change scores with citations, unreviewed and shipped concepts never do; risk exception accepts until expiry and returns after it; the user's own decision wins; write guards (shipped folder, existing paths, reviewer format, inbox-only files, symlinks); same file imported once; edits re-rank the stored board; agent tool read-only; AI drafts are valid OKF drafts without `verified` |
| Docker workstation, Knowledge tab (Playwright, Chrome) | tab discovered and enabled by the installer; overview shows live gaps from the last scan; shipped guide links navigate; graph 23 nodes / 78 links; Add form for Team, Application, Account with plain-language previews; duplicate save refused |
| Agent, workstation | "Who owns the payments application …?" → loaded `rg-knowledge`, searched and read the concepts, answered with paths and trust tiers, flagged that no resource carries the application's tag; when taught an owner in chat it wrote Team and Note drafts to the review queue (no `verified`) after checking the role read-only |
| AWS Spot, upgrade | rebuilt package → `terraform apply` (4 in-place changes) → desk seeded 23 shipped concepts; tab installed and enabled on boot |
| AWS Spot, documents | converter installed from the tab over HTTPS egress; Word and PDF imported as references; *Draft with AI* showed the estimate first (~1,600 input tokens), then used 694/1,676 and 612/2,005 input/output tokens and produced 4 and 2 faithful drafts with source quotes |
| AWS Spot, review | a resource-less S3.8 risk exception was flagged as applying to every bucket and rejected; a duplicate application rejected; team, policy, runbook and account drafts approved; an account draft without an id reported as a gap instead of applied |
| AWS Spot, priorities | an Account concept (mission critical) re-ranked 2 of 89 stored findings immediately (no AWS calls); P1 reasons cite `knowledge accounts/…`; issues show the owner |
| AWS Spot, durability | instance replaced: bundle, references and review drafts restored from S3; the converter (excluded from checkpoints) reinstalled from the tab |
| Shipped CIS / best-practice knowledge on Spot | 32 shipped concepts seeded on boot (frameworks, six practices, guides, source guides, playbooks; conformant, every link resolves); `show` on a live EC2.19 finding named its practice (network exposure), owner and the knowledge applied |
| Spot instance role, organization scope | the instance role assumed `RemediGeniusReadOnly` under `aws:ResourceOrgID` = `${aws:PrincipalOrgID}` and read through it |

Defects found and fixed during these runs: Hermes's dashboard serves user plugins only when enabled in both the profile
and the launch scope (installers now enable both); the tab backend resolved the profile folder as the Hermes root
(AI drafting fell back to another provider, 401); the dashboard's own packages made pip skip the converter's
dependencies (install now isolated and verified by an import test); a pip cache inside the Hermes home made each
checkpoint 100 MB (`.cache` excluded, pip runs without a cache); the release `dist/` ignore rule hid the tab's bundle
from git; snapshot names could sort out of order within one second.

## Continuous improvement (validated 2026-10-22)

| Check | Result |
| --- | --- |
| Unit tests (`test_improve.py`, scripted model) | redaction (plugin and desk copies identical), trace hooks, `/rate` and correction detection; lessons vs organization facts; gap discovery; mined tasks; 17 deterministic desk checks; read-only fixture replay with recorded AWS; grader (facts, citations, invented citations, honesty, safety, tool use); lint rules and protected regions; gate decisions; SkillOpt staging, approval, restart re-apply and rollback; unsafe candidate never staged; budget stop; Propose–Probe–Compose keeps only edits that helped and refuses held-out tasks; stale approvals not applied; tool-call markup; consolidation; context hints; socket allow-list |
| Live baseline, `deepseek-v4.1-flash` (local runner, desk CLI) | 14 tasks, 85% overall, 0 unsafe answers, about 380,000 tokens; found harness issues (empty replies, step limit) and real skill gaps (no runbook citation in investigations, an invented exception path) |
| Live SkillOpt on `rg-investigate` (local) | held-out validation 94.5% → 100%, no critical regression, 0 unsafe; 2 general edits accepted (cite the sources a conclusion relies on), 3 rejected; gate 8/8; about 900,000 tokens |
| AWS Spot, Improve tab (Playwright) | desk checks 17/17; a chat with a correction and `/rate down` produced traces (skills, tool calls, tokens, feedback), an organization-fact draft, a knowledge gap and a mined task; **Optimize** started from the tab through Hermes's plugin model access staged a candidate (training 87% → 93%, validation 94% → 100%, gate 8/8); the candidate view showed scores, gate checks, reasons and the diff; **Approve and activate** made the agent use it (its next investigation of a real finding cited the refs, playbook and practice); **Roll back** restored the shipped skill byte for byte; history records optimized → activated → rolled back with the reviewer |
| AWS Spot, Propose–Probe–Compose | two single-hypothesis probes on a training task neither improved (0.67 → 0.67, 0.67); nothing composed or staged (88,000 tokens) |
| AWS Spot, budget and schedule | a 400,000-token budget stopped an optimization mid-epoch as designed; the nightly review was created as a Hermes cron job from the tab, its script reported news in 3 s without a model, and turning it off removed the job |
| AWS Spot, consolidation | found the two duplicate payment runbook references and the duplicate Payments Team / Payments Engineering concepts, each with a merged draft |

Shipped from this run: the `rg-investigate` improvement (cite the finding ref, playbook and knowledge a conclusion relies on;
name operator commands and the playbook under "Do now"), after it passed the gate locally and on Spot and was reviewed.

Defects found and fixed during these runs: the desk socket refused `improve` (a test now checks every command the tab
uses); the replay harness recorded empty replies and accepted a provider's tool-call markup as an answer; one noisy
replay could block a good candidate (regressed critical tasks are now replayed once more); the tab's token estimate was
three times too low; the cron removal parsed the wrong line; a proposed draft path was counted as an invented citation.

## Answers from live evidence and IAM reads (validated 2026-10-22)

| Check | Result |
| --- | --- |
| Unit tests | 162 passed, 1 skipped: trust-policy classifier (none / wildcard / one repository / pinned), missing analyzer detail, policy evaluations allowed, credential-returning reads refused, account scoping, Evidence line, same-issue siblings in `show` |
| Desk checks | 19/19, including guidance by intent (explain → rg-triage, fix → rg-iac-fix) and the evidence guide per domain |
| Offline agent tasks (`deepseek-v4.1-flash`, Acme fixture) | all 21 tasks once: 0.85 overall; the evaluation found a missed accepted-risk check, a guessed guide path and a loose grading pattern, all fixed. The 10 affected tasks re-run: 1.00. Repeats: OIDC verification 3/3, OIDC permissions (policy document, not name) 3/3, accepted risk 3/3 after `show` listed the same issue on other resources, SCP question 1.0 / 0.8 / 0.8 (correct simulator verdict; the unread SCP text was not always named) |
| AWS Spot, live account, through the dashboard chat | rescan reclassified a GitHub OIDC role from HIGH "without a repository condition" to MEDIUM "any branch, tag, environment or pull request of one repository", matching its trust policy. Verification answered from one `iam get_role` read with the Evidence line, no invented change timeline. "Is it read-only?" read the inline policy and used the IAM simulator (organization decision included). "Which roles can be assumed from outside?" listed every role, matched the Access Analyzer findings and found an unconditional cross-account trust. An explanation-only request on open SSH checked attachments (none), said "reachable on paper", and proposed no fix |

## Trust and closure (issues #4–#10, validated 2026-10-22, `deepseek-v4.1-flash-1017`)

| Check | Result |
| --- | --- |
| Unit tests | 176 passed, 1 skipped: exposure findings (OCSF parsing, AWS severity floor, not-enabled reporting, old boto3), attack sequences, labelled desk-derived signals, unsupported evidence ids flagged, coverage headline, fix-record lifecycle (decided → PR → deployed → verified → reopened, stalled; unknown when the source was not read), proof reads refuse writes, business-context basics, one-click `remember`, `decide` fix fields, local vs third-party model endpoint |
| Desk checks | 19/19 |
| Terraform | `terraform validate` passes with the new `data_notice` output |
| AWS Spot, live account | board headline: "Inspected: 1 account · 1 of 17 enabled region(s) · 6 of 8 sources read. Not inspected, resources found: one region (1 VPC). Not covered: 3 account(s)." Security Hub exposure analysis reported as not enabled (blind spot), not silence |
| Live chat | "Is my environment secure?" → not as it stands, with the coverage limits quoted. "Was data exfiltrated?" → not established, evidence ids on every observed fact, the logging boundary named, the hypothesis labelled, one question to the user. "Where does my data go?" → third-party provider, from `doctor`, with what is sent |

Not validated live: AWS Security Hub exposure findings (the test account does not have the current Security Hub enabled;
parsing is tested with a documented-shape fixture), a full fix-record cycle through a real PR and deployment.

## Not covered by this release's validation

- Discovery of a *different* account whose read role works (exercised by unit tests; this validation had no second
  account with the role).
- A member role in a *different* account: the member-role path was validated with the role deployed in the stack's own account
  (same template, trust and org condition). The cross-account boundary itself is standard IAM behaviour and not separately exercised.
- Delivery of alerts to a messaging platform (only local delivery tested).
- Private subnets with NAT, regions other than us-east-1, models other than `deepseek-v4.1-flash`.
- Linux/macOS workstation hosts (the workstation path was run on Windows with Docker Desktop).
- The Knowledge tab with an existing local Hermes (`install_local_hermes.py`); PowerPoint and Excel imports (same
  converter, not exercised); interoperability with third-party OKF tools such as okfctl beyond the spec checks in tests.
