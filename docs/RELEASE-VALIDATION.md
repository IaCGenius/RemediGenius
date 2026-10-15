# v0.1.0 validation

Validated baseline: AWS us-east-1, Qwen 3.8 Max, Hermes 0.21.7, one ce-desk profile.
Other models and regions are configurable but not qualified by this release.

| Check | Result |
|---|---|
| Retained tests | 74 passed on Windows and on exported Windows/Linux source |
| Packaging | Clean wheel installation and offline sample passed |
| Terraform | Native stack validation passed; retained-installation upgrade completed |
| AWS upgrade | Backup completed; retained sessions, knowledge and credentials preserved |
| Native runtime | All 59 packaged integrity entries matched; login and authenticated chat passed |
| Qwen | Fresh scoped Config reads and retained organizational knowledge used |
| Critic context | Both loaded skills and six evidence excerpts included, without omissions; final answer incorporated corrections |

These are targeted checks, not exhaustive AWS coverage or proof that every model
answer is correct. No customer-cloud remediation was executed. Generated fixes
remain drafts requiring operator review and appropriate validation. Review context
is bounded; large case lists should be narrowed to individual cases. Broad
assessment interpretation and narrative attribution still require human review.

Local checks were used; successful GitHub Actions execution is not claimed.
See [limits](LIMITS.md), [AWS coverage](AWS-MVP-CAPABILITIES.md), and
[upgrade instructions](UPGRADING.md).
