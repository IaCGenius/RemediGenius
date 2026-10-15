# rc5 onboarding validation — 2026-10-12

Implemented three bounded contextual collectors, a browser read-plan workflow, local CLI consent and one-page access checks, parameterized CloudFormation role export, workspace source review and agent prompt handoff. The user-facing plan states when AWS access has not been tested. Collection stays outside MCP and browser execution.

Validation completed:

- Full PowerShell regression: 97 CE tests, 38 deterministic rule cases, result-view checks and 30 existing kiosk tests passed.
- Final targeted onboarding suite: 13 passed, including the additional IAM role-path test after the full regression. Includes AWS SDK input-shape validation, restricted sessions, consent, pagination, errors and decompression bounds.
- Edge against the installed rc5 wheel: read plan, scoped template download, synthetic context import, immediate workspace review and source-only labeling passed.
- Existing simple-knowledge Edge workflow passed, including draft/review/use, Markdown review, AI handoff and mobile layout.
- `git diff --check` passed; only line-ending notices.
- Wheel built and installed into the existing CE virtual environment. Preview uses the previous `.rgce/review` data directory.

Live limitations:

- Read-only IAM existence check returned `NoSuchEntity` for the required CE role. No source data was fetched using administrator credentials, and no role was created.
- No CloudFormation deployment, Lambda execution, GitHub OAuth login or model inference was performed. Tests do not establish those integrations work in a customer's environment.
- Lambda reader class, separate output-writer permissions, all-runs pause and full lifecycle validation remain pending. Existing freeze allows live runs.
- New log/object sources are context available through existing MCP tools, not automatically correlated findings or automatic AI summaries.

No SaaS repository, running/stopped cloud infrastructure or external publication was changed.
