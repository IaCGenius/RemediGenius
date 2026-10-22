# Release validation — RemediGenius Community Edition v0.3.0

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
