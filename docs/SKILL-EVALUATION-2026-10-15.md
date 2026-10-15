# Skill evaluation: 15 October 2026

This is a bounded behavioral evaluation, not proof that an LLM will answer every
AWS question correctly. Native Hermes used Qwen 3.8 Max; local Pi with DeepSeek
provided candidate suggestions and advisory grading. The reusable lab, prompts
and private traces stay outside CE in the maintainer's v2 repository.

## Promotion decision

Two broader procedure rewrites were rejected. High model-grader scores missed
incorrect status terminology, invented organizational approval requirements,
and invalid Terraform syntax. Neither rewrite replaces the existing working
procedure. Only four small Markdown guidance edits are promoted:

- Use explicit operator knowledge now; publication enables shared reuse.
- Apply category rules when scope is established, without inventing per-resource
  approval documents. Keep accepted-risk case closure a separate action.
- Do not equate independent source fields or make counts broader than the read.
- Prefer conventional multiline Terraform; distinguish syntax checks from
  provider validation, planning and execution.

## Observed results

| Evaluation | Observation |
|---|---|
| First broad comparison | Two questions compared; baseline had one incomplete runtime, candidate recovered from an API error. Candidate rejected after manual review of population terminology. |
| Second broad comparison | Three paired questions completed; a fourth candidate completed natively but grading stopped at the configured context cap. Both policy answers invented approval requirements. Candidate Terraform failed the actual parser. Remaining cases were not run. |
| Focused four-file package | Six native Qwen runs completed: operator rule, minimal knowledge intake, missing metadata, Terraform syntax, lifecycle versus security state, and evidence freshness. |
| Final knowledge clarification | Two additional native Qwen runs completed; both used category guidance without requiring per-resource approval, preserving unknown purpose and distinguishing case closure. |
| Existing deterministic boundary checks | 36 passed. These are constructed contract checks, separate from native model/AWS runs. |

The focused Terraform output passed the installed Terraform parser/formatter.
It was not provider-validated, planned or applied. Its Config starting template
still needed operator/provider work to establish recorder start behavior; do not
treat it as a complete deployable remediation. No customer AWS changes were made
by the evaluations. Real reads used the configured account and us-east-1; no
fabricated AWS responses were substituted.

## Limits and why the change stays small

The final tests support the specific guidance corrections, not a statistical
claim of general superiority. Some answers remained too long; automated grading
also inferred details not independently supported by the trace. Reused failure
cases are regressions, not unseen holdouts. Critique remains advisory and bounded.
Future improvements should demonstrate transfer across behaviors and sources,
retain failed attempts, and use deterministic validation where available.

The native package selected for promotion has SHA-256
`38d41ade74f5c00df9e718d699ebb60e7731e30d77916b705855dbc37fb80b18`.
Deployment verification is recorded in the current resume handoff.

## Deployed cloud verification

Terraform applied three in-place updates, with no additions or destructions.
The existing Spot replacement process retained the profile volume. The profile
upgrade backed up prior files; all 59 integrity entries matched and Qwen remained
selected. No lab plugin was present; dashboard login returned HTTP 200.

A final deployed Qwen run exited successfully. Fresh Config definition and status
reads both returned successful empty lists. It preserved their regional scope,
did not infer overall security coverage, and used the existing logs-only policy
without inventing a per-bucket approval requirement. The critic received the exact
loaded skill hash and six evidence excerpts, with no skill omission. No customer
remediation or case write was requested or performed. The answer remained verbose
and used descriptive case-closure wording; no case-disposition execution was
tested in this run. AI_CRITIQUED is advisory, not certification.
