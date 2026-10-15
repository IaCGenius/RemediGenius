# Native CE runtime acceptance

Validation date: 2026-10-14 UTC. Publication is an owner decision. This report
separates observed live behaviour from constructed regression cases.

Candidate assessment: ready for supervised, read-only AWS preview feedback, with
the model narrative limitation below disclosed. This is not an all-pass narrative
evaluation or a sign-off for autonomous remediation. No public release was made.

## Candidate

- Hermes 0.21.7, official image pinned to
  `sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b`.
- Native CE source package SHA256:
  `8bd0d0602b08f0292c25774cdca11c48e1a499eb892a17773e6864cfc13d5820`.
- One native `ce-desk` profile, actual Qwen3.8-max provider calls, two configured
  AWS account aliases. No fabricated live findings or mock AWS adapters.

## Deterministic checks completed

185 repository tests passed; four symlink-dependent tests skipped on the Windows
host. The separate kiosk suite passed 30 tests. All 38 rule cases and seven
result-view checks passed. Terraform validation passed and the reviewed CE-only
plans applied without deleting the evidence bucket or retained session volume.
Run the repository checks with its installed `.venv` and dependencies. A separate
system-Python attempt lacked the document libraries and current AWS SDK and failed;
that is retained as an environment failure, not counted as a passing run.

Twenty-four runtime regression cases include tool admission, missing preflight,
request/deadline limits, denied-operation retry suppression, knowledge traversal,
review cancellation, honest empty-review status and preservation of the draft
and collection facts when display evidence is large. These are constructed local
boundary tests, not AWS acceptance evidence.

The comparator was also exercised against the actual two Security Hub snapshots
that triggered the earlier bug. It returned 24 unchanged findings; rotating
pagination tokens no longer create a false change. Partial or incompatible
snapshots return INCOMPARABLE.

## Live source and persistence checks

GuardDuty list_detectors, Inspector list_coverage, Access Analyzer list_analyzers,
Config describe_configuration_recorders, Security Lake list_data_lakes and
Security Hub get_findings returned successfully. Macie get_macie_session returned
AccessDeniedException. Every artifact listed by those seven reads matched its
S3 receipt hash. A successful metadata API is not proof the service is enabled,
healthy, recording or covering the whole organization.

Spot replacement restored the retained state. The final inspected host had 19 native
sessions preserved and the candidate source/image pins above. The package, evidence
cache and temporary reader-credential mounts were read-only. The public profile
upgrade procedure backed up the retained profile, preserved model configuration
and restarted successfully. This is same-AZ retained-volume recovery, not a
cross-region disaster recovery test or session backup to S3.

Fresh native profile installation also succeeded in an isolated official-image
container with networking disabled and no persistent writable mounts. This tests
offline profile installation from the packaged files, not an offline model or
offline cloud deployment. Source packaging produced identical SHA256s on two runs.

## Native UI / Qwen journeys

Final candidate tested through native Hermes UI with real Qwen calls and source
receipts. No synthetic findings were substituted for AWS responses.

| Journey | Observed result | Assessment |
|---|---|---|
| Security Hub investigation | 24 ACTIVE findings: 2 CRITICAL, 2 HIGH, 4 MEDIUM, 16 LOW; selected knowledge identified as CE guidance, not organization policy; three proposals | Source facts and proposal-only boundary verified |
| Identical-query reassessment | 24 before/after; 13 changed records, zero added/removed; direct raw comparison found changes only in UpdatedAt, LastObservedAt and ProcessedAt | Deterministic result correct; model identified timestamp refresh, but misstated user silence about remediation (see known defect below) |
| Two-account EC2 | default: 6 records (2 running, 1 stopped, 3 terminated); sandbox: 0; each query exhausted within one page | Counts/states independently checked against raw records; empty result not labelled secure |
| Five-day EC2 CloudTrail | 100 distinct event IDs across two pages; 2 DryRun API errors; only about 39 minutes returned; has_more=true | Counts, identities and incomplete time coverage verified; no claim of complete five-day assessment |
| Macie / Security Lake boundaries | One denied Macie request, no retry; Security Lake returned an empty local list; configuration-versus-recording-status and historical/data-event query gaps named | Denied, empty and unavailable capabilities correctly distinguished; no fabricated execution |

All five final turns returned one AI_REVIEWED critique each. The native session
used only ce_aws (17 calls including reads/projections/comparison), ce_knowledge
(3), ce_review (5), and skill_view (4). Seven actual cloud collection receipts
were inspected; all ten raw/normalized artifacts referenced by them matched
their recorded SHA256s. No terminal or generated-code tool was used by the agent.
These observations apply to this session and pinned package, not every possible
future prompt. Raw traces and screenshots remain private.

The earlier two-snapshot regression also produced UNCHANGED on genuinely identical
finding sets. The final live comparison above produced CHANGED because AWS refreshed
source timestamps; neither result proves remediation. The source records remain
the reference when model prose or a model critique disagrees.

## Defects found and corrected during validation

- Security Hub comparison previously treated transport tokens as finding changes.
- CloudTrail normalization lacked deterministic decoded API errors and identities.
- The original synchronous native review request outlasted its nominal timeout
  because native request handling could retry. The corrected review uses the
  native asynchronous facade under a total cancellation deadline, once per turn.
  A short Qwen probe then completed in about five seconds using native auxiliary
  reasoning_effort: none; that is now the shipped utility default, without changing
  the main investigation model.
- The pinned image uses Hermes's YAML module; the public upgrade utility now uses
  it with a PyYAML fallback for ordinary Python environments.
- Older skills suggested terminal execution; the guarded profile now clearly
  distinguishes operator utilities from admitted agent operations.
- The critic initially treated missing earlier-session evidence as fabrication
  and confused the configured page ceiling with a specific request's page limit.
  Its packet now includes actual request arguments, collection facts and runtime
  budgets, and explicitly marks its current-turn context boundary. The agent must
  reconcile critiques against receipts; a critique is not a factual authority.

Failed attempts are retained in private validation logs. They are not relabelled
as first-attempt passes. Raw account details, model credentials and customer
findings are excluded from the publication material.

## Scope that must remain explicit

The final candidate still has a model-level narrative defect: during reassessment,
Qwen correctly reported the deterministic change and unchanged compliance/severity,
but paraphrased the user's lack of a remediation statement as a statement that no
fix occurred. The prompt and runtime context explicitly prohibited that inference.
This is not a deterministic-layer failure and is not recorded as a clean narrative
pass. A critic also made some incorrect objections to valid earlier evidence.
Human review remains necessary; model review does not eliminate hallucinations.

No automatic remediation or generated-code kiosk is admitted in this profile.
Security Lake support is metadata, not querying lake records. Not all 44 listed
SDK operations were live-tested, and not every provider/backend is validated.
A model critique is not an independent proof. Missing or timed-out critique must
remain NOT_REVIEWED. Native streaming can display draft text before the final
output hook; the persisted final answer carries the review label.

Terraform requires an existing bucket, subnet and provider secret. Account-role
onboarding is explicit. There is no scheduled EBS backup or organizational role
rollout. S3 and EBS retention incur charges after compute is stopped. Read the
[quickstart](NATIVE-CE-QUICKSTART.md) and [runtime contract](CE-RUNTIME.md).
