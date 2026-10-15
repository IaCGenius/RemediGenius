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
See [limits](LIMITS.md), [AWS coverage](AWS-CAPABILITIES.md), and
[upgrade instructions](UPGRADING.md).


## Post-v0.1.0 main: community skills review

The community skills pack was reviewed and corrected before integration. It adds
model-guided workflows, not new cloud-write permissions or scanner integrations.
Versioned framework mappings must come from supplied evidence; an absent mapping,
empty result or changed field is not a passing security assessment.

- Local checks: 96 tests passed, including packaged skill/reference integrity,
  invalid-request rejection and fixed output-warning behavior. A clean source
  export was also tested and scanned for private configuration and identifiers.
- Terraform: validation passed; deployment changes used the existing retained
  volume and an encrypted backup. The official Hermes image and model stayed pinned.
- Cross-region negative check: an existing out-of-region S3 bucket read through
  the us-east-1-only executor returned an explicit error, not a healthy result.
- Not qualified here: macOS end-to-end setup, the private-subnet/NAT deployment
  path, removal of port-80 host egress, or a newly recorded video demo.

The output warning is a conservative text-pattern aid, not policy evaluation or
permission to execute a proposal. It can flag quoted/restrictive policy context,
miss other hazards, or require human interpretation. No warning is not a safety
certification. The skill checks themselves remain model-guided.


Live Qwen checks on the updated Spot runtime:

| Check | Outcome |
|---|---|
| Framework/attack-path interpretation | Used returned control/version metadata and kept hypothetical exposure separate from observations; no false prose command warning |
| Natural-language one-page request | Partial: used the three-page default, correctly disclosed actual scope; see [collection-limit caveat](LIMITS.md#natural-language-collection-limits) |
| Explicit page bound | With ce-aws-read loaded and `max_pages=1`, exactly one page was collected and all five loaded skill/reference files reached the critic |
| Controlled injection test | Rejected the explicitly constructed malicious command; runtime warning appeared; no AWS reads or writes in this test |
| Organization context and reassessment | Used retained selected knowledge and fresh scoped Config evidence; no invented classifications or verified fix; incorporated the critic's removal of an unsupported KMS proposal |
| Critic context | Every skill/reference loaded in these checks reached the critic; no skill-context omissions reported |
| Preservation and access | Retained knowledge files present, session history retained, credential refresh readable with 0750/0440 modes; 89 integrity entries matched |

These representative checks do not individually qualify every new skill or every
possible output. Source reads used real AWS responses; the injection example was
explicitly a constructed test, not a fabricated AWS finding. The existing v0.1.0
tag and release archives are unchanged; this section describes newer main.
