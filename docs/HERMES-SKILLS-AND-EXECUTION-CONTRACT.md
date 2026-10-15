# Skills and execution responsibilities

Hermes chooses and explains; readable skills guide repeatable investigations;
the CE runtime and scoped AWS executor enforce supported operations and bounds.
Prompts are not a security boundary. See [runtime controls](CE-RUNTIME.md) for the
implemented preflight, budgets, tool gate and review-context behavior.

Environment knowledge comes from configured targets, available operations,
selected knowledge and dated AWS receipts. Source availability is not proof that
findings were collected. Unknown scope, coverage or applicability stays explicit.

## Responsibilities of the existing skills

| Skill | Job | Finish condition |
|---|---|---|
| ce-aws-read | Establish scope, use supported SDK operations, retrieve exact records | Receipt plus requested bounded data, or a specific failure |
| ce-aws-security | Select the AWS investigation workflow and interpret source evidence | Concise evidence-backed answer/proposals with limits |
| shared-evidence | Read previously collected evidence when no fresh run was requested | Relevant receipt and files; no redundant discovery on a fresh run |
| ce-knowledge | Apply selected business context and scoped exceptions | Applicable guidance cited, or the specific ambiguity identified |
| ce-source-tools | Discover genuinely usable integrations | One configured route or a precise missing integration; no improvised adapter |
| ce-explain-review | Explain actions, failures, limits and review evidence | Traceable outcome and bounded improvement proposal |

One single CE profile uses these skills. No additional agent personas or approval
committee are required. Business knowledge answers “what matters here”; skills
answer “how to investigate”; tools answer “what happened when this request ran.”


See [release validation](RELEASE-VALIDATION.md) and [limits](LIMITS.md).
