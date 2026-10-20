# Community Skills Pack

This pack adds ten focused skills to the RemediGenius CE Hermes profile. All skills follow the same evidence and review workflow already used by `ce-aws-security`.

## Evidence and review workflow

The skills guide the model; runtime controls enforce tool boundaries. They use:

1. **Evidence first** — Start from an existing S3 receipt (`ce_aws show` or shared-evidence) or a fresh bounded `ce_aws` read. Cite receipt ID, timestamp, and exact field values before any interpretation.
2. **Four-way separation** (when relevant):
   - **Observed facts** — Exact fields from the receipt or API response. No synonym substitution.
   - **Guided checks** — Readable references applied by the model. These are not executed deterministic validators.
   - **Organizational knowledge** — Selected imported context with source paths, or explicitly identified operator-provided context; never treat it as an AWS fact.
   - **AI proposal** — Clearly labeled, limited to at most three items, and marked “AI-generated — operator review required”.
3. **Critic gate** — Call `ce_review` before the final response (or state `NOT_REVIEWED` if unavailable). Pass the draft through the normal review tool; the runtime includes captured evidence and references, with omission counts when context is bounded.
4. **No new integrations** — Skills interpret evidence already collected or local files the operator supplies. They use only existing bounded RemediGenius CE tools and do not install scanners or add arbitrary network access.
5. **Limits** — Explicitly state coverage windows, pagination, “empty ≠ healthy”, and “change ≠ verified fix”.
6. **Provenance** — Each skill includes a short `PROVENANCE.md` noting original RemediGenius CE community content under Apache-2.0.

Skills compose with existing skills (`ce-aws-security`, `ce-aws-read`, `ce-knowledge`) and the `ce_case` tool. They do not add new collectors or write permissions.

## Skills

| Skill | Purpose |
|---|---|
| `ce-iam-least-privilege` | Draft tighter IAM policies from collected evidence |
| `ce-cis-mapping` | Map findings to CIS AWS Foundations / FSBP controls |
| `ce-s3-deep-dive` | Deep analysis of S3 public access and encryption |
| `ce-scanner-interpreter` | Interpret selected readable Prowler / Checkov / Trivy report excerpts |
| `ce-attack-path` | Grounded attack-path narratives from evidence |
| `ce-reassessment-playbook` | Structured post-change verification |
| `ce-business-context-prioritizer` | Apply organizational ownership and criticality |
| `ce-terraform-snippets` | Inspectable Terraform hardening snippets |
| `ce-cloudtrail-triage` | High-risk CloudTrail event patterns |
| `ce-case-summary` | Markdown case summaries |

## Contribution

Add new reference mappings or snippets under the skill’s `references/` directory. Keep guidance concise and cite versioned sources. Do not introduce external calls or unbounded queries. Update this document and the skill’s `PROVENANCE.md` when extending a skill.

For AWS procedure routing and decision briefs, see [Security triage](SECURITY-TRIAGE.md).
