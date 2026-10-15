# rc6: implementation and acceptance evidence

This release candidate adds skills-first investigation folders, CLI access to evidence and resolved knowledge, a minimal AWS access module, and an optional operator-approved Lambda reader. MCP remains available but is no longer required for investigation. The console exposes readable exports and the packaged skill before its optional MCP configuration.

## Live AWS results

The owner authorized fresh CE roles and isolated test infrastructure in their existing AWS account. Terraform deployed a separate private synthetic bucket/log source, an unattached SG fixture, a restricted read role and the optional reader. The SaaS stacks and their stopped engine were not changed.

| Test | Observed result |
|---|---|
| Exact SG selection | The scoped collector found SGNET-002 on the selected unattached fixture |
| Security Hub | 24 existing findings read successfully; native services were not enabled or reconfigured |
| CloudTrail | Regional event-history read succeeded within the requested window and call budget |
| CloudWatch Logs | Selected synthetic group returned its test events |
| S3 object | Selected synthetic object read successfully |
| Wrong ExternalId | AWS AccessDenied |
| Unselected object | AWS AccessDenied |
| Source-role write attempt | AWS AccessDenied |
| Terraform fixture change | Removed only the synthetic SG's ingress |
| Reassessment | Comparable evidence; SGNET-002 returned RULE_NO_LONGER_MATCHES |
| Lambda without consent | Function rejected invocation payload |
| Approved Lambda read | Source read and S3 output succeeded; code and evidence hashes verified |
| Python/dependencies | Receipt records Python 3.13.15 and boto3 1.42.89; runtime minor is configured and dependencies hash-locked |
| Reader pause | Reserved concurrency zero; new invocation rejected with TooManyRequestsException |
| CloudFormation templates | AWS ValidateTemplate accepted all three generated source templates; no CFN stack deployed |

The reader is left paused, the SG fixture has no ingress, and test evidence is retained. Pausing does not kill already-running invocations or remove retained resources. Storage/log charges can remain. The deployed code is operator-reviewed fixed code; this does not validate arbitrary agent-generated code or the older advanced kiosk's deployment/pause boundary.

## Local and release-artifact checks

- 106 CE regression tests, 38 deterministic rule cases and 30 existing kiosk tests passed.
- Four Edge workflows passed: files-first export, general console, simple knowledge and source onboarding, including mobile checks.
- A fresh Windows environment installed the wheel outside the source checkout, ran demo/export/verification and collected the selected real S3 fixture through the scoped role. Installed package files were checked against the final wheel.
- A disposable Linux Python 3.12 container installed the wheel and passed demo, reassessment, file export/integrity, console API and packaged-skill checks without AWS/model credentials.
- The reader build normalizes Git line endings. Three reader build/handler checks passed, and ZIP source entries were compared with tracked source. The canonical bundle was deployed and its execution receipt verified.
- The final Terraform plan reported no drift. Source identifier checks passed; private account data and credentials are excluded from release artifacts.

## Skills and Hermes

A fresh Hermes conversation successfully used only `read_file` and `search_files` on a synthetic exported workspace and the investigation skill. It read evidence, deterministic findings, reviewed guidance and proposal files; cited record IDs; kept rule severity and AI interpretation separate; and supplied proposed verification/rollback without executing changes. The transcript is retained privately.

The generic provider selection initially failed with HTTP 401. The existing named provider succeeded without changing global model configuration or implementing provider code in CE.

With explicit operator disclosure consent, the combined **live AWS fixture -> selected files -> Hermes** test completed successfully. Nine file-tool calls stayed within the selected export and investigation skill; eight cited identifiers matched the export. No MCP or cloud tools were used. The answer retained critical severity, explained the baseline and scoped variation, rejected the synthetic source's embedded instruction, and proposed verification/rollback without executing changes. The completed runtime transcript was recovered and its scope/citation checks replayed without another model call.

Manual review identified a factual overstatement: attaching an ENI alone does not establish SSH exploitability; routing, listeners and other controls matter. The answer also described a narrative end-of-testing condition as expiry; automatic expiry was not demonstrated. These are recorded quality limitations, so this passes the integration/scope checks, not unconditional factual acceptance. AI output remains a draft for review.

AI output remains unreviewed interpretation. One successful conversation is not proof of universal prompt-injection resistance or factual correctness. File-tool selection and profiles are not OS isolation.

## Reproduce and inspect

- `scripts/test.ps1` / `scripts/test.sh`: local rules, knowledge, adapter, API and kiosk regression checks.
- `tests/live_acceptance.py`: explicit before/after, permission, reader and pause checks against the separate test stack.
- `tests/live_hermes_files.py`: explicit selected-file model test with tool-scope and citation checks; requires operator disclosure approval.
- `tests/linux_wheel_smoke.py`: disposable Linux wheel test with no cloud/model credentials.
- `tests/browser_files.py`: readable export, skill download, optional MCP and mobile layout.
- [Sanitized machine-readable results](acceptance/rc6-results.json).

Private AWS evidence, deployment logs, runtime receipts and transcripts remain under `.rgce/aws-acceptance` and `.rgce/hermes-files-test`. Their SHA256 manifest helps detect later edits; it is not an independent signature or attestation. They are excluded from public archives. Published source lets others reproduce the tests using their own separate fixtures.

## Release boundaries

This remains rc6, not a public GA release. It supports local operation, scoped collection, reviewed knowledge, skills/file investigation, proposals and bounded reassessment. Optional approved-reader compute is distinct from automatic remediation or autonomous arbitrary-code deployment. GitHub OAuth interoperability has not been exercised; local committed-repository intake is the tested foundation. Azure/GCP adapters remain future work. Publication and release tagging are separate steps.
