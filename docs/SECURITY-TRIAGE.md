# Security triage and implementation planning

RemediGenius CE turns AWS-native findings into an evidence-backed decision brief.
It uses pinned AWS procedures, selected organizational knowledge and the existing
read-only execution boundary. It does not claim that a human consultant reviewed it.

## Try it

- "Review my Security Hub findings. What should we address first, and why?"
- "These are production services. Use the selected ownership and exception notes
  to prioritize the findings. Show where the context changes your recommendation."
- "Plan the first issue: suggested owner, dependencies, change approach, validation
  and rollback. Do not apply anything."
- "Save this implementation plan as a Kanban case." (Saving requires your request.)

Supply business context in chat for the current discussion or select shared
knowledge documents for reuse. A title in the knowledge index is not policy content.
No automatic publication or formal risk acceptance is implied.

## What the answer means

| Part | Meaning |
|---|---|
| Assessment | Main conclusion and why it matters in the selected scope |
| Recommended order of action | AI-proposed sequence, grounded in evidence and your context; not a new AWS severity |
| What supports this | Source observations with evidence references |
| Your context | Relevant selected knowledge that affected the answer, when supplied |
| What remains uncertain | Material gaps, including incomplete collection or unverified conditions |
| Next decision | The useful next choice, without automatic implementation |
| Evidence trail | Read status, scope, time, pagination and receipts |

The brief considers the collected population; it must disclose when only a subset
was inspected. Counts are not unique issue counts. Related controls can be grouped
without deleting their source records. Readable metadata is not proof of protection.
A concise brief highlights priorities; it is not a claim of exhaustive incident
response or complete coverage of every AWS security service.

## Skills and boundaries

- `ce-aws-security`: intent routing into AWS's existing procedure references.
- `ce-aws-read`: SDK-based read execution, deterministic evidence and pagination.
- `ce-security-brief`: relevance, business context, priority rationale and presentation.
- `ce-remediation-plan`: proposed implementation work, ownership, dependencies and
  verification; adapted from the MIT-licensed Rifteo remediation planner.
- `ce-validate-fix`: real CLI/IaC checks for requested artifacts; never cloud apply.

At workflow start, up to three procedure names are selected from the packaged
registry. Their exact text and hash are saved with the investigation and supplied
to planning, interpretation and review. Existing stages, IAM and read/action budgets
are unchanged. There is no extra reporting agent or rewriting model call.

## Skills.sh review

| Candidate | Decision |
|---|---|
| [AWS aws-security](https://www.skills.sh/aws/agent-toolkit-for-aws/aws-security) | Reuse pinned procedure registry and references; adapt execution to RemediGenius tools. Separate advisory/remediation extensions from upstream factual summaries. |
| [Rifteo remediation-planner](https://www.skills.sh/rifteo/skills/remediation-planner) | Adapt concise ordered work; retain MIT attribution. Replace fixed effort ranges and easy-wins-first rules with evidence, dependencies and operator decisions. |
| [Anthropic internal-comms](https://www.skills.sh/anthropics/skills/internal-comms) | Review audience/purpose and conclusion-first principles. No templates/files copied; retain our focused security brief rather than install newsletter workflows. |
| [Anthropic stakeholder-comms](https://www.skills.sh/anthropics/knowledge-work-plugins/stakeholder-comms) | Directory result found, but the corresponding path was not present in the inspected current source tree. Not installed. |
| [Google mantis-advise](https://www.skills.sh/google/mantis/mantis-advise) | Directory description concerns code security and Mantis knowledge dependencies. Not adopted for AWS findings; no source-level vetting claimed. |

Discovery counts and directory audit badges are not security guarantees. Pins,
licenses and modifications are recorded in the adopted skills' PROVENANCE.md files.
No third-party installer, MCP server or new cloud permission is introduced.

## What is reused and what RemediGenius adds

| Responsibility | AWS upstream skill | RemediGenius integration |
|---|---|---|
| Finding collection | Service-specific API procedures and source formats | Select those procedures inside the existing scoped reader and workflow |
| Summaries | Service, standards, control and severity summaries | Group supported related issues and explain a proposed order of attention |
| Business context | AWS service context | Selected operator knowledge, ownership, asset purpose and scoped exceptions |
| Implementation | Primarily factual read-only guidance | Separate requested plan, CLI/IaC drafts, actual tool validation and reassessment |
| Review | Instructions for the consuming agent | Freeze selected procedure text with the evidence packet used by interpretation and critique |

For a general Security Hub request, the established ASFF source includes integrated
products. It must not silently become a compliance-only query. Explicit standards
questions use the standards workflow. Source severity stays intact in both cases.

## Validation and current limits

The focused response-contract and procedure-context checks passed (25 tests).
Live native-dashboard testing with DeepSeek v4.1 Flash exposed an initial
compliance-only routing error. After correcting the skills, a repeat of the same
general Security Hub question collected findings across integrated products with
one AWS read. It proposed investigating threat alerts before posture gaps and
explained that order without changing AWS severity.

The observed UI turn took about 3 minutes 43 seconds. The response still contained
more identifiers and collection detail than an executive brief needs. This is an
improvement in advisory behavior, not a guarantee of polished or correct advice on
every run. The planning check avoided invented owners and claimed execution, but
the browser helper opened a different conversation; that check does not establish
same-session continuity. No cloud remediation was performed. This was focused
validation, not a new test of every referenced AWS procedure.
