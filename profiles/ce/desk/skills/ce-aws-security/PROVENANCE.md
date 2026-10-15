# Provenance

Adapted from aws/agent-toolkit-for-aws, Apache-2.0, commit
`2cb0fa1c2e668e1bb075028800b6b27efb95779e`. Previously reviewed in v2
`docs/ideas/skills-review.md` and pinned in the prior internal prototype/skills.lock.json.
That review recorded CAUTION, not an unconditional security guarantee.

Only upstream Markdown references and license are copied; no upstream executable
code or installer. New CE entry instructions select supported read operations
through ce-aws-read instead of local admin CLI/MCP credentials. Upstream SKILL
is preserved as background provenance, not active instructions. No organization
content from ai-memory was copied.

2026-10-14: CE-authored extension adds triage → chosen-format fix preparation →
reassessment to the same entry skill. references/ce-fix-preparation.md is original
CE workflow guidance, not upstream AWS material. It grants no additional tools or
write permissions and distinguishes draft output from executed validation.

2026-10-14 final UI regression: corrected a generated CloudFormation MFA Delete
property against the official AWS resource schema. CE-authored guidance now
distinguishes API/provider/template schemas, documents the unsupported native
CloudFormation path and requires correction of affected saved drafts. The same
pinned reference is supplied to the existing bounded reviewer; no new generator
or execution adapter was introduced.

2026-10-15: CE-authored entry guidance adds the existing AWS Config recorder-status
API to distinguish configuration from current recording. API semantics checked
against https://docs.aws.amazon.com/config/latest/APIReference/API_DescribeConfigurationRecorderStatus.html.
The deterministic executor admits that read through its operation manifest;
no new collector, generated code or customer-cloud write is introduced.
