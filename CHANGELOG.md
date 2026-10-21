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
- **Multiple accounts:** run in your delegated-administrator account for an org-wide Security Hub, GuardDuty and Inspector
  view, and/or deploy one `RemediGeniusReadOnly` role per account with a StackSet. The instance role may assume it only
  inside your organization. See [docs/MULTI-ACCOUNT.md](docs/MULTI-ACCOUNT.md).
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
  container, knowledge library tools, proactive schedules, the optional third-party browser UI, the dashboard
  session-limit overlay, the retained EBS volume, and the separate storage/IAM stacks.

**Upgrading:** v0.3 is a new deployment, not an in-place upgrade. See [docs/UPGRADING.md](docs/UPGRADING.md).

## Earlier releases

v0.1.x and v0.2.0 shipped the investigation-workflow design (`ce-desk` profile, collector, validator, knowledge
library). Their notes, documentation and validation records remain in the git history at tags `v0.1.0`–`v0.2.0`.
