# How RemediGenius Community Edition works

RemediGenius Community Edition (RemediGenius-CE) splits the work in two:

- **Deterministic work**, done by the desk service (`rgtriage`): collecting findings, normalizing, deduplicating,
  scoring, grouping, locating IaC, validating Terraform, saving state.
- **Judgment**, done by the agent (Hermes with the `remedigenius` profile): briefing you, investigating, asking the one
  question that matters, and writing the code change.

No custom agent runtime: Hermes provides chat, the dashboard, skills, memory, schedules and messaging. RemediGenius-CE
adds one Python package, one profile (SOUL, five skills, one plugin), one dashboard tab (Knowledge) and two deployment
paths. Organization knowledge is one Open Knowledge Format bundle ([KNOWLEDGE.md](KNOWLEDGE.md)).

```mermaid
flowchart TB
  subgraph AWS[Your AWS accounts]
    SH[Security Hub] & GD[GuardDuty] & IN[Inspector] & AA[Access Analyzer] & CF[Config] & CW[CloudWatch alarms] & HE[Health]
  end
  subgraph Desk[Desk service - only component with AWS credentials]
    C[collect<br/>read-only botocore guard] --> N[normalize + dedupe] --> P[prioritize + group] --> B[board.md · latest.json · report.html]
    L[IaC locator + terraform validate]
    KB[(knowledge<br/>OKF bundle)] --> P
    K[checkpoints]
  end
  subgraph Agent[Hermes container - no AWS credentials]
    PL[plugin rg-triage<br/>tool · session-start board · guards] --- SK[skills rg-triage · rg-investigate · rg-iac-fix · rg-onboard · rg-knowledge]
    KT[dashboard tab Knowledge<br/>review · add · import · graph]
  end
  AWS -- read-only role --> C
  PL -- Unix socket: fixed list of triage commands --> Desk
  KT -- Unix socket: knowledge and knowledge-edit --> Desk
  K -- S3 or local folder --> D[(Durable storage)]
```

## The agent's surface

| Piece | What it does |
| --- | --- |
| `rg_triage` tool | `digest`, `scan`, `list`, `show`, `fix`, `aws` (one read-only call or policy evaluation, prefixed with an Evidence line: account, region, time, complete or partial), `validate`, `decide`, `doctor`, `onboarding`, `playbook`, `report`, `knowledge` (read-only views), `history` (current facts or committed history with the manifest and evidence id) |
| Session-start hook | puts the current board in front of the agent on the first turn; starts a background refresh when the scan is stale |
| Guards | blocks file writes outside the proposals folder; blocks reads of credential stores, keys, `.env` and Terraform state; routes every `decide` through Hermes's approval prompt |
| `/triage` | the board without a model call (interactive chat and gateways) |
| Skills | chosen by what the user wants: `rg-triage` (briefing, priorities, decisions, explaining and verifying findings or any configuration question), `rg-investigate` (suspicious activity: actors, timelines, compromise), `rg-iac-fix` (fixes, when asked), `rg-onboard` (accounts, access, sources), `rg-knowledge` (read, cite and draft knowledge). SOUL holds one evidence method for all of them; six evidence guides in the knowledge bundle say which reads decide each kind of question |
| Improvement | traces from Hermes hooks; offline evaluation, SkillOpt-style optimization and Propose–Probe–Compose in the Hermes container; grading and the security gate in the desk; candidates activated only after approval ([IMPROVEMENT.md](IMPROVEMENT.md)) |
| Knowledge tab | Hermes dashboard plugin `rg-knowledge`: overview and gaps, browse, review queue, Add form, document import with optional AI drafting, graph. Its backend holds no AWS credentials and changes the bundle only through the desk's `knowledge-edit` command |

The Hermes toolsets enabled are `skills`, `clarify`, `file` (repository reading plus writes to proposals) and
`rg_triage`. There is no terminal toolset, so the agent cannot run shell commands.

## Collection and volume

Sources per account and region: Security Hub, GuardDuty, Inspector, IAM Access Analyzer, AWS Config (non-Security Hub
rules), CloudWatch alarms in ALARM, and AWS Health (us-east-1; needs Business support, otherwise its events arrive
through Security Hub). Every source records coverage: `ok`, `not_enabled`, `denied`, `not_available` or `error`.
"No findings" is never confused with "not enabled".

The desk counts everything, reads in detail what can rank high, and shows fixes rather than findings:

| Source | Complete (cheap) | Read in detail |
|---|---|---|
| Inspector | totals plus fix units from `ListFindingAggregations`: AMI, ECR repository, Lambda function, package, CVE | CRITICAL and HIGH up to `detail_limits`, plus MEDIUM with a public exploit |
| Security Hub | — (no count API) | per severity up to `detail_limits`; capped tiers are reported as "at least N" |
| GuardDuty | totals by severity from `GetFindingsStatistics` | up to `max_findings_per_source`, highest severity first |

- Products read directly are excluded from Security Hub queries server-side, so nothing is read twice.
- Only the top `max_stored_findings` (default 20,000) ranked findings are stored. The agent reads a pre-rendered
  board of under 8 KB.
- A newly readable source is a *baseline*, not thousands of "new" alerts. For capped sources, "new" means first
  seen after the previous scan, and nothing is called resolved unless both scans read that source completely.
- `tests/test_rgtriage_scale.py` runs 40,000 Inspector and 3,000 Security Hub findings through the CLI in about a second.

## Prioritization

Score = source severity (CRITICAL 60, HIGH 45, MEDIUM 25, LOW 10; vulnerabilities get 75%) plus signals, each written
into the finding's `reasons`:

| Signal | Points |
|---|---|
| Threat detection; compromise/exfiltration/impact types | +10 / +20 |
| Root credentials used (by call volume) | +15 / +25 / +40 |
| Public exposure (exposure controls, Access Analyzer public, network reachability) | +15 |
| Exploit available / EPSS ≥ 0.1 / fix available | +12 / +5 / +3 |
| Detection or audit gap (Config.1, CloudTrail.*, GuardDuty.1 …) | +8 |
| Toxic combination: more than one risk type on the same resource | +10 |
| One fix (AMI/image/function rebuild) clears ≥100 / ≥1,000 findings | +5 / +8 |
| Business criticality (reviewed Application/Account concepts, then `triage.yaml`, then env tag) | −10 … +15 |
| Matches a stated business goal (Security Goal concept or `triage.yaml`) | +1 … +15 (default +5) |
| Threat with no activity for 30+ days | −10 |

P1 ≥ 70 (act now), P2 ≥ 50 (this week), P3 ≥ 30 (backlog), otherwise P4. Findings that share one fix collapse into
one issue: the same control across standards, one package across many CVEs and instances, and all 14 CIS CloudWatch
metric-filter controls. Decisions (acknowledged, investigating, fixing, accepted_risk, false_positive, suppressed,
resolved) hide or annotate issues; they are local triage records and do not change AWS. A reviewed Risk Exception
concept acts as an `accepted_risk` decision until it expires. Every knowledge effect is cited with the concept path.

## IaC fixes

`fix` indexes Terraform (variables, `.tfvars`, local `.tfstate` ids), CloudFormation/SAM templates and CDK output, then
ranks candidate code by evidence:

- **high**: a CloudFormation logical-id tag or Terraform state id equals the resource, or a literal name matches
- **medium**: a resolvable name pattern or prefix matches
- **low**: the same resource type with a computed name, which the agent must confirm
- **none**: not in the indexed code, or an account-level control that needs a new resource

It also lists the blocks that configure the resource (for example `aws_s3_bucket_public_access_block`) and loads the
remediation playbook. The agent writes a diff, saves it to the proposals folder and runs `validate`
(`terraform init -backend=false`, `validate`, `fmt` on a scratch copy; no plan, no apply, no AWS credentials).

## Durable state

The desk's facts are not in an archive any more. Every collected AWS response is in S3 `raw/`, and findings, scans,
coverage, decisions, fix and GitHub events are Iceberg tables in `warehouse/` ([STORAGE.md](STORAGE.md)). Local
SQLite is a cache and commit outbox that a new instance rebuilds; current-state tables make that rebuild fast.

`rgtriage/durable.py` still checkpoints the Hermes home, the GitHub configuration and the small configuration home
(`triage.yaml`) to S3 on Spot, or to the local folder on the workstation:

- consistent copies of live SQLite databases (online backup); per-file SHA-256 manifest; the pointer is written last
- unchanged homes are skipped; 10 snapshots kept per home
- restore happens only into an empty home and verifies every hash. Live state always wins.
- **lineage**: a home may only replace checkpoints it descends from. A fresh machine whose restore did not run is
  refused (`DIVERGED`) instead of overwriting good state.
- triggers: every 2 minutes, after scans and decisions, on service stop, and on an EC2 Spot interruption notice
- the desk state home is no longer part of the archive; facts and the cache are rebuilt from S3/Iceberg

## Concepts borrowed from the AWS Well-Architected Agent

| Well-Architected Agent | RemediGenius-CE |
|---|---|
| Agent profile: accounts, Regions, goals | `triage.yaml`: accounts, regions; Account and Security Goal knowledge concepts |
| Execution role + read-only access role per account | audit role / member read roles with `SecurityAudit`; automatic discovery at every scan; `rgtriage onboarding` |
| Application context: tags and criticality | Application concepts (tag match → `mission_critical` … `test_development`, owner), `environment_tag_keys` |
| Goal-aligned prioritization | criticality and goal boosts in the score, shown in the reasons |
| Ready-to-deploy IaC with trade-offs | diff, `terraform validate`, blast radius and rollback; you apply it |
| Scheduled refresh | scan timer plus a session-start refresh when stale; `security-watch` alerts |
| Builds on existing services | the AWS security services above are the sources; no custom detectors |
