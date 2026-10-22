# Changelog — RemediGenius Community Edition (RemediGenius-CE)

## v0.3.0 — Security Desk

RemediGenius-CE is rebuilt around one idea: once an AWS account is connected, the right findings reach you first,
explained, with the code change that fixes them.

**New**
- **One Hermes profile, `remedigenius`.** Every conversation opens with the attention board: P1 first, what changed,
  blind spots, one next step. `/triage` shows it without a model call.
- **Desk service (`rgtriage`)** collects Security Hub, GuardDuty, Inspector, IAM Access Analyzer, AWS Config,
  CloudWatch alarms and AWS Health across accounts and regions. Every call is read-only, enforced by a botocore guard
  even with admin credentials. Coverage gaps are reported as blind spots.
- **Explainable prioritization** (P1–P4): severity, active threats, root use, exposure, exploits and EPSS, detection
  gaps, toxic combinations, business criticality, goals. Findings that share a fix become one issue. Access Analyzer
  severity reflects who is trusted (for example, GitHub OIDC without a repository condition is HIGH).
- **Scale:** Inspector totals and fix units (AMI, ECR repository, Lambda, package) come from aggregation APIs. Detail
  is read only for what can rank high, Security Hub is not read twice, and storage is bounded. 40,000 Inspector findings
  scan in about a second in the scale test.
- **Investigations** with bounded read-only AWS calls; the agent states what it could not see.
- **IaC fixes:** locates the Terraform, CloudFormation or CDK that deployed a resource (evidence-ranked), proposes a
  diff, and runs `terraform validate` on a scratch copy. Remediation playbooks for common controls and threats.
- **Decisions** (acknowledged … resolved) go through Hermes's approval prompt.
- **Multiple accounts, onboarded automatically:** at every scan the desk detects its organization, its Security Hub /
  GuardDuty / Inspector delegated-administrator rights, and every account where the `RemediGeniusReadOnly` role can be
  assumed. Those accounts are read from then on, with their existing findings as a baseline. The board shows accounts
  read fully, findings-only and not covered. `rgtriage onboarding` (or asking the agent) prints the one-time StackSet
  command filled in for your environment. The instance role may assume the role only inside its own organization, with
  no organization id to configure. See [docs/MULTI-ACCOUNT.md](docs/MULTI-ACCOUNT.md).
- **Knowledge in Open Knowledge Format (OKF v0.2):** one bundle per installation, replacing v0.2's knowledge library
  with a standard format. It ships guides (how the desk works, where to look for evidence), a guide per finding source
  and the remediation playbooks as OKF concepts. Your Application, Account, Risk Exception and Security Goal concepts
  change priorities once a person has reviewed them, and every effect is cited by path in the finding's reasons. Risk
  exceptions expire and their findings return. The agent reads, searches and cites the bundle (`rg_triage
  action=knowledge`) and drafts what it learns into a review queue; it can never approve. The dashboard **Knowledge**
  tab (Hermes dashboard plugin) has overview and gaps, browse, review, a guided Add form, document import (PDF, Word,
  PowerPoint, Excel through markitdown, installed on first use) with optional AI drafting that shows the token
  estimate first, and a graph view. See [docs/KNOWLEDGE.md](docs/KNOWLEDGE.md).
- **Trust and closure (issues #4–#10):**
  - Evidence: answers cite evidence ids for observed facts; the desk flags cited ids it never returned. When evidence
    does not settle a question the agent says "not confirmed" (and what would confirm it) or asks you. Desk-derived
    signals are labelled ("path not verified", "desk heuristic").
  - Coverage: every board starts with what was inspected (accounts, regions of enabled, sources) and lists regions
    with resources outside the scan scope; scope can be confirmed once and recorded.
  - Current AWS signals: Security Hub exposure findings (OCSF, `GetFindingsV2`) with AWS's traits, attack path and
    remediation; AWS Critical/High exposures and GuardDuty attack sequences are never ranked lower than AWS rates them;
    Access Analyzer internal access. boto3 ≥ 1.42. Capability matrix: [docs/AWS-CAPABILITIES.md](docs/AWS-CAPABILITIES.md).
  - Could vs did: configuration answers what could happen, logs what did; beyond the evidence the agent names the
    boundary and hands off (new guide "Beyond the desk's evidence" with Athena / CloudTrail Lake queries).
  - Fix records: deciding to fix starts a record with owner, PR and a proof of done; the desk advances it at every scan
    (in PR → deployed → verified, reopened, stalled) and shows it on the board and in a Fixes view.
  - Business context: the board shows "N of 5 basics set"; the agent prefills account, application, owner, IaC and
    policy suggestions from tags, Organizations and CODEOWNERS; facts you state in chat become active with one click;
    batch approve in Review.
  - Data flow: the installer and the dashboard show where data goes, once; `doctor` says whether the model endpoint is
    local or third-party ([docs/DATA-FLOW.md](docs/DATA-FLOW.md)).
- **Answers from live evidence:** a finding is a lead, not proof. Every AWS security question (explain or verify a
  finding, or a question without one, such as "which roles can be assumed from outside?") follows one method: scope,
  the smallest read that decides it, stop when supported, and an answer split into observed, inferred and gaps.
  Six evidence guides (identity and trust, effective permissions, network exposure, data protection, detection and
  history, vulnerabilities) say which reads decide a question and what they cannot show. Skills are assigned by what
  the user wants: explaining an exposure no longer starts a fix.
- **IAM evidence:** the IAM policy simulator (including SCPs) and Access Analyzer policy checks are allowed as
  evaluations; the agent reads policy documents, never infers permissions from names. Every AWS read starts with an
  Evidence line (account, region, time, complete or partial). With several readable accounts the read must name one.
  Reads that return credentials are refused. Access Analyzer GitHub OIDC findings are classified from the role's
  actual trust policy (none, wildcard, one repository with any branch or pull request, pinned) instead of the
  analyzer's condition summary.
- **Continuous improvement, gated and human-approved:** redacted execution traces from Hermes hooks with `/rate`
  and correction detection; an offline evaluation organization (17 deterministic desk checks, 16 agent tasks with
  train/validation/test splits and critical tasks); SkillOpt-style skill optimization and Harness²-style
  Propose–Probe–Compose replayed with read-only tools on your configured model; lessons split into skill lessons and
  organization facts (review queue only); knowledge-gap discovery; skill and knowledge consolidation; `Guidance:`
  lines that point findings to the right skill and practice; a deterministic security gate (safety lint, protected
  regions, strict held-out improvement, no critical regression, desk checks, OKF validity) before a person approves; an
  Improve tab with the candidate queue, diffs, rollback and a nightly Hermes cron review. See
  [docs/IMPROVEMENT.md](docs/IMPROVEMENT.md). The shipped `rg-investigate` skill already includes one improvement learned
  this way (cite the finding ref, playbook and knowledge a conclusion relies on), gated and reviewed.
- **Alerts:** a `security-watch` Hermes cron job reports only new P1/P2 findings, with no model calls.
- **Durable state:** the Hermes home and desk state are checkpointed to S3 (Spot) or a local folder (workstation) every
  2 minutes, after scans and decisions, on stop and on Spot interruption notices. Restore is verified, and lineage
  protection stops a fresh home from overwriting good state.
- **Deployments:** a disposable Spot instance (no retained volume; restores from S3) and a Docker workstation path
  (`tools/workstation.py`). Both run a desk process holding the only AWS credentials and a pinned Hermes container
  holding none. The Spot stack grants KMS decrypt for a customer-managed model-secret key automatically.
- Validated model: `deepseek-v4.1-flash`.
- Offline demo: `python tools/demo.py`.

**Removed** (available at tag `v0.2.0`)
- The `ce-desk` profile and its runtime plugin, the deterministic collector and read catalog, the fix validator
  container, the v0.2 knowledge library commands (replaced by the OKF bundle and the Knowledge tab), proactive schedules, the optional third-party browser UI, the dashboard
  session-limit overlay, the retained EBS volume, and the separate storage/IAM stacks.

**Upgrading:** v0.3 is a new deployment, not an in-place upgrade. See [docs/UPGRADING.md](docs/UPGRADING.md).

## Earlier releases

v0.1.x and v0.2.0 shipped the investigation-workflow design (`ce-desk` profile, collector, validator, knowledge
library). Their notes, documentation and validation records remain in the git history at tags `v0.1.0`–`v0.2.0`.
