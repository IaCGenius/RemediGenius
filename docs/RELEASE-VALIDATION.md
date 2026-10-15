# Current main: deterministic remediation validation

This addition follows v0.1.1; the existing release tag and downloads are unchanged.
Native package SHA-256:
`03adabba2ca146263950a3d2593c40b0fe3277a50b4fb2b8092e48a1bb8c727f`.
See [the pinned toolchain and scope](REMEDIATION-VALIDATION.md).

- Local and clean-export suites: 104 passed. The initial run with an outdated
  system boto3 failed four storage tests; the established CE virtual environment
  passed. Those failed runs were not treated as acceptance.
- Six direct real-tool checks: invalid and corrected CLI, Terraform and
  CloudFormation artifacts produced the expected FAIL/PASS results. These were
  explicitly constructed artifacts, not fabricated AWS findings.
- Local Qwen: the previous invalid Config CLI proposal was corrected and passed
  actual CLI parsing; fresh AWS evidence still showed unmet live prerequisites.
- Local Qwen: Terraform and CloudFormation both exercised actual FAIL → diagnostic
  → correction → PASS cycles in two attempts. A standalone Terraform proposal also
  passed with provider 6.68.0. The Terraform loop passed again after restarting onto
  the final package. Audit used actual tool results, not just model summaries.
- Spot Qwen: CLI validation passed; Terraform and CloudFormation each returned
  FAIL then PASS on attempt 2/3, confirmed from actual tool records. Both runtimes
  used the final package above. Retained-state replacement completed, authenticated
  chat/board passed, all 90 integrity entries matched, and prior knowledge files
  and conversation history remained present.
- Runtime boundary: a fourth validation attempt is rejected before worker contact.
  A failing tool result remains FAIL in the runtime-owned heading even if prose
  says otherwise. No arbitrary shell, plan or apply is exposed.
- Container inspection: read-only root, no data mounts, no credentials, dropped
  capabilities; connections to internet and instance metadata failed.

A tool PASS does not certify model prose. One CloudFormation response incorrectly
claimed a default S3 Retain deletion policy despite the critic disputing it. That
claim is wrong: set deletion/replace policies explicitly according to the intended
lifecycle. The template's syntax pass did not validate that narrative. No proposed
customer-cloud changes were executed. This distinction is intentional and is shown
in the runtime heading: syntax/schema validation is separate from security impact,
resource existence and deployment approval.

## Historical v0.1.1 validation

Qualified scope: AWS us-east-1, Qwen 3.8 Max, one ce-desk profile. This release
includes the ten reviewed community skills; their source branch was merged,
not copied into an unrelated implementation.

The final native package SHA-256 is
`ff7d22c9dae0eb55b7abbd3f7bfa601fc6d6fcb571f5b7e526ebab7dc4a06d32`.
Both deployment paths use the official Hermes 0.21.7 image pinned to
`sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b`.
Local Docker assembles this image with the CE package; CE does not publish a
custom rebuilt Hermes image.

| Check | Outcome |
|---|---|
| Deterministic tests | 101 passed, including a clean source export |
| Installed wheel | Clean target installation and explicitly synthetic offline demo passed |
| Live collector bounds | Both deployment collectors returned one page when the budget was omitted and two when explicitly requested; incompleteness stayed visible |
| Local Qwen functional runs | Six scenarios completed: two one-page phrasings, explicit two-page collection, organizational knowledge, remediation proposal and persistent case |
| Spot Qwen functional runs | The same six scenarios completed; natural-language page requests produced 1, 1 and 2 pages respectively; knowledge and evidence-linked case workflows exercised |
| Critic context, both runtimes | Every loaded skill/reference reached the critic in all twelve final scenarios; no reported omissions |
| Spot upgrade and access | Encrypted backup completed; host replacement finished; prior knowledge and session history retained; authenticated chat and board passed; all 89 integrity entries matched |
| Local persistence | Restart retained all six sessions and the evidence-linked case; authenticated chat and Kanban access passed; all 89 package integrity entries matched |
| Scheduled collection | Both deployed scheduled-check functions returned OK on real evidence; no model calls required |
| Reader boundary | Direct EC2 access with the local container reader identity was denied |
| Remediation draft quality | **PARTIAL**: final local draft still used an invalid AWS CLI flag; no proposal was applied or provider-validated |

This is functional testing with real model calls and live AWS reads, alongside
code tests. Process completion alone was not treated as proof of answer quality.
Both case workflows recovered from one rejected argument before saving their
notes; these were recovered attempts, not first-attempt passes. Spot critique
corrections were recorded on the case. Narrative reasoning can still overstate
what an empty current Config response establishes about historical coverage;
read the scoped receipts and do not infer that older history never existed.

The first candidate exposed dropped review guidance and incorrect CloudFormation
attribute placement. The final candidate retained all three proposal guides and
put CloudFormation attributes at resource level. However, its CLI proposal used
`--recorder-name` where `start-configuration-recorder` requires
`--configuration-recorder-name`. This illustrates the remaining draft-quality
limit: AI critique can miss syntax and semantic errors. Do not copy a generated
fix into production without validation. Runtime receipts describe observations;
an AI review label does not validate commands or infrastructure templates.

Tests used Hermes conversations on each deployed runtime. Login/board checks
used HTTP; this is not a claim of exhaustive browser automation. No customer-cloud
remediation was executed. Local validation substitutes for unavailable hosted CI;
a successful GitHub Actions run is not claimed. Other models, regions, every AWS
resource type and every possible question are not qualified by these checks.

See [limits](LIMITS.md), [coverage](AWS-CAPABILITIES.md) and
[upgrade instructions](UPGRADING.md). Earlier results below are historical and
must not be mistaken for the final candidate's pagination behavior.

## Historical v0.1.0 validation

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


## Historical community-skills integration checks

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
| Natural-language one-page request | Partial: used the three-page default, correctly disclosed actual scope; see [collection-limit caveat](LIMITS.md#collection-limits) |
| Explicit page bound | With ce-aws-read loaded and `max_pages=1`, exactly one page was collected and all five loaded skill/reference files reached the critic |
| Controlled injection test | Rejected the explicitly constructed malicious command; runtime warning appeared; no AWS reads or writes in this test |
| Organization context and reassessment | Used retained selected knowledge and fresh scoped Config evidence; no invented classifications or verified fix; incorporated the critic's removal of an unsupported KMS proposal |
| Critic context | Every skill/reference loaded in these checks reached the critic; no skill-context omissions reported |
| Preservation and access | Retained knowledge files present, session history retained, credential refresh readable with 0750/0440 modes; 89 integrity entries matched |

These representative checks do not individually qualify every new skill or every
possible output. Source reads used real AWS responses; the injection example was
explicitly a constructed test, not a fabricated AWS finding. The existing v0.1.0
tag and release archives are unchanged; this section describes newer main.
