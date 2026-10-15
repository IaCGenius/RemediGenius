# Community Skills Pack

This pack adds ten focused skills to the RemediGenius CE Hermes profile. All skills follow the same grounding and deterministic contract already used by `ce-aws-security`.

## Grounding and Deterministic Contract

Every skill in this pack enforces:

1. **Evidence first** — Start from an existing S3 receipt (`ce_aws show` or shared-evidence) or a fresh bounded `ce_aws` read. Cite receipt ID, timestamp, and exact field values before any interpretation.
2. **Four-way separation** (required in every response):
   - **Observed facts** — Exact fields from the receipt or API response. No synonym substitution.
   - **Deterministic checks** — Local rules, mappings, or checklists stored in the skill’s `references/`. Apply them verbatim.
   - **Organizational knowledge** — Only content imported via `ce-knowledge`, cited by source path.
   - **AI proposal** — Clearly labeled, limited to at most three items, and marked “AI-generated — operator review required”.
3. **Critic gate** — Call `ce_review` before the final response (or state `NOT_REVIEWED` if unavailable). Supply the same evidence and references.
4. **No external API calls** — Skills interpret evidence already collected or local files the operator supplies. They never invoke external services or install tools.
5. **Limits** — Explicitly state coverage windows, pagination, “empty ≠ healthy”, and “change ≠ verified fix”.
6. **Provenance** — Each skill includes a short `PROVENANCE.md` noting original CE community content under Apache-2.0.

Skills compose with existing ones (`ce-aws-security`, `ce-aws-read`, `ce-knowledge`, `ce_case`). They do not add new collectors or write permissions.

## Skills

| Skill | Purpose |
|---|---|
| `ce-iam-least-privilege` | Draft tighter IAM policies from collected evidence |
| `ce-cis-mapping` | Map findings to CIS AWS Foundations / FSBP controls |
| `ce-s3-deep-dive` | Deep analysis of S3 public access and encryption |
| `ce-scanner-interpreter` | Interpret local Prowler / Checkov / Trivy reports |
| `ce-attack-path` | Grounded attack-path narratives from evidence |
| `ce-reassessment-playbook` | Structured post-change verification |
| `ce-business-context-prioritizer` | Apply organizational ownership and criticality |
| `ce-terraform-snippets` | Inspectable Terraform hardening snippets |
| `ce-cloudtrail-triage` | High-risk CloudTrail event patterns |
| `ce-case-summary` | Audit-ready Markdown case export |

## Contribution

Add new reference mappings or snippets under the skill’s `references/` directory. Keep deterministic checks as static data or simple checklists. Do not introduce external calls or unbounded queries. Update this document and the skill’s `PROVENANCE.md` when extending a skill.
