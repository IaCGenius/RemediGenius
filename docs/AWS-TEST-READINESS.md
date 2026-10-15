> Historical rc5 baseline. See [rc6 acceptance](RC6-ACCEPTANCE.md) and [current AWS onboarding](AWS-ONBOARDING.md) for the implemented skills-first path and live tests.

# CE AWS test readiness — 2026-10-12

**Ready for staged integration testing preparation; not ready to test or release every proposed feature.** The rc5 local/browser and mock-AWS tests are recorded in RC5-ONBOARDING-VALIDATION.md. Those tests do not establish live AWS, Hermes inference or deployment success.

## Verified against the existing account

Read-only IAM and Lambda metadata inspection confirmed:

- `rg-readonly-self` exists, requires an ExternalId and trusts the Hermes host. Its explicit deny includes S3 object content and CloudWatch log content.
- `rg-hermes-host` and `kiosk-rg-agent-builder` exist. Builder trust references the Hermes host.
- `RemediGeniusCommunityReadOnly`, currently required by CE collectors, does not exist.
- `kiosk-rg-gate` and `kiosk-rg-sandbox` are Active, report successful last updates and use Python 3.13. This is configuration status, not a successful execution test.

No secrets, log/object contents or model credentials were retrieved. No Lambda was invoked, infrastructure modified, or engine restarted.

Private precursor runbooks supplied reusable dogfood, role-chain, sandbox and teardown test methods. Their machine-specific locations stay outside public release artifacts. Historical successes must be repeated against CE's actual release artifacts.

## Test order and release gates

| Stage | Current readiness | Completion evidence |
|---|---|---|
| Local console, rules and knowledge | Offline and browser tests passed | Repeat against final wheel on a clean workspace |
| Skills + ordinary files, without MCP | Investigation skill and knowledge exports exist; full investigation export and CLI retrieval missing | A fresh Hermes session reads an exported workspace, resolves current guidance, cites receipts and prepares a proposal without MCP |
| AWS SG and Security Hub | Collectors implemented; CE role missing | Restricted-role reads, correct account/region, useful results, explicit unavailable/partial coverage |
| CloudTrail, CloudWatch, S3 object | Collectors implemented and mock-tested | Named source access, bounded successful reads, denied-source tests, no admin fallback, evidence and metadata preserved |
| Hermes/model interpretation | Runtime handoff exists; live CE end-to-end untested | User-selected provider, intentionally selected evidence, citations, AI labels and no invented findings |
| Optional kiosk | Existing gate/sandbox and local module available; reader/output permission design and all-runs pause unfinished | Pinned code/dependencies, consent, restricted canary, S3 output receipts, stop/pause behavior, denied access and cleanup |
| Fresh install/release | Pending | Install packaged CE independently of the SaaS checkout; complete documented onboarding and verify no private account data in artifacts |

## Account reuse without changing the SaaS boundary

Use the same account as the test environment, with a separate CE workspace, role and explicitly selected test sources. Do not weaken `rg-readonly-self` to make new content readers work. Its configuration-only restriction is intentional. The generated CE source policy can seed the test role, but its trust and permissions must match the chosen operator and sources before deployment.

Select a known small JSON/JSON.gz object and log group (prefer synthetic content), one region and a short time window. Role/trust setup, any test fixture creation and optional compute deployment are separate cloud mutations from collection. Review their concrete IaC changes before applying. Do not treat old runbook commands as instructions to resume the parked engine.

For v0.1, either finish and validate the optional kiosk reader path, or explicitly exclude it from supported release functionality. Likewise, do not describe skills-first operation as complete until the file/CLI route has been built and tested without MCP. Passing configuration collectors alone is not the full product acceptance test.
