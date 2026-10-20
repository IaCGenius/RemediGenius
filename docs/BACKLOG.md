# Product backlog

Requested 20 October 2026. Reference:
[AWS Well-Architected Agent](https://docs.aws.amazon.com/wellarchitected/latest/userguide/agent.html)
and [InfoQ](https://www.infoq.com/news/2026/10/aws-well-architected-agent/).

Keep Hermes, deterministic evidence and operator-controlled changes. Improve the
experience around goals, workload context, decisions and implementation.

| Work | Intended result | Status |
|---|---|---|
| Account onboarding | Small instance-role scan; saved status, scope, times, gaps; confirm purpose | First version available for operator UI review |
| Knowledge onboarding | Conversational wizard; reusable workload brief; review and publish | Skill flow available for operator UI review |
| Goal-aligned recommendations | Why an issue matters here and goes first | Skills implemented; consistency to improve |
| Durable recommendations | Evidence, decision, dependencies and verification in existing cases | Tools exist; coherent experience to mature |
| Application relationships | Observed links distinguished from inferred dependencies | Discuss before expanding |
| Trade-offs | Security benefit and supported operational/cost implications | Guidance exists; consistency to improve |
| Changed-evidence review | Revisit decisions using scheduled comparisons | Collection exists; scheduled LLM review not enabled |
| Executive presentation and latency | Decision first, evidence underneath | Needs improvement |

## Two onboarding flows

**Account:** instance profile → bounded baseline scan → saved status → operator
confirms/corrects business interpretation → recurring refresh. Confirmation does
not grant AWS access. Discovery is not a full inventory or a security verdict.
Denied reads, partial pages and unrecorded resources remain explicit. Further
exploration uses the existing investigation workflow.

**Knowledge:** ask what matters → establish scope → capture purpose, goals,
owners, constraints and exceptions when supplied → review a small Markdown draft
→ explicit publish → reuse selected context. One conversation, one ce-desk profile.
Unknown is acceptable. Names do not establish resource purpose.

The first implementation uses Hermes chat and readable status documents. A new
graphical wizard and scheduled LLM prioritization remain discussion items.

## Acceptance

- Last background status is available without a new investigation.
- Status shows observed time, next expected refresh, scope and partial/failed reads.
- Stopped compute stops collection; S3 keeps timestamped results.
- User can review and publish knowledge in chat, then read it in a new session.
- Context changes proposed priority, not source severity or permissions.
- No new credentials, IAM grants or automatic remediation required.
