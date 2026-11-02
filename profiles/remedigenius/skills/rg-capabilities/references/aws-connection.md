# AWS connection and investigation

The desk owns AWS access. `rg_triage action=doctor` identifies configured investigation transport and account/source
coverage; transport configuration is not connection certification. Use one scoped `action=aws` read to prove it.
Every answer must keep account, target region, observation time, transport and completeness attached to evidence.
The MCP endpoint region and queried resource region are separate. With multiple accounts, explicitly select the
finding's account. Never widen scope to all accounts/regions because an upstream skill recommends it.

## Choose the smallest connection

- Existing CE AWS deployment: reuse its explicit audit role through the desk. No AWS keys or OAuth login in chat.
- Direct SDK remains the collection backend and the default investigation transport.
- Optional managed MCP uses AWS's official signed transport behind the same structured read command. It adds
  no prompt tools, no model-authored scripts, no IAM grants and no silent direct fallback.
- The operator enables it on the standard host using `deploy/aws-single/install-aws-investigation.sh enable`;
  `disable` returns investigation to direct. This is operator setup, not an agent shell action.
- Individual workstation users can use an existing SSO profile plus an explicit scoped read role; install the
  package's `aws-mcp` extra and set `aws_investigation.transport: managed_mcp` in triage.yaml.
- Native OAuth may simplify a separate user-owned MCP connection, but inherits the chosen identity's access.
  Do not suggest signing in with administrator access. OAuth compatibility with CE's pinned Hermes and a
  complete CE onboarding flow are not certified; don't describe this as a working one-click CE feature.

## Keep prompts small

Use the existing account-read tool; managed API schemas and sandbox instructions stay inside the desk transport.
For documentation, discover only the needed AWS Knowledge tools. Search for one relevant AWS skill, then fetch
only the needed reference. Stop when the question has enough evidence. Do not list every connector in answers.
Use specialized managed EKS/ECS/SageMaker or AWS Labs tools only for a demonstrated missing workflow, with their
own scoped access and live verification. AWS-hosted managed endpoints and installable AWS Labs servers are not
the same thing. Neither a vendor name nor a tool's readOnlyHint proves least-privilege permissions.

## Failures and limits

| Observation | Explain and do |
| --- | --- |
| Expired/revoked credentials | Account access unavailable; operator refreshes the source SSO/session. Never ask for tokens |
| Access denied or organization restriction | Missing evidence, not a healthy resource. Identify the needed read; do not recommend blanket administrator access |
| MCP outage, timeout or invalid response | No new evidence. Existing board/history and direct collection remain available; label their age. No repeated blind retry loop |
| MCP pending task | Not completed. Do not invent a result. The bounded desk transport currently refuses pending results; operator can retry a narrower query |
| Pagination/output cap | Partial or unverified completeness; never claim all resources checked or findings resolved. Absence may also reflect API defaults/filters, not truncation |
| Unknown service/SDK operation | Unsupported, not absent. Do not bypass by running scripts or obtaining credentials |
| Secret, object-content or log-content read refused | Preserve the metadata boundary. Document/KB retrieval requires a separate explicitly scoped knowledge connection |

AWS MCP can report `isError=false` while its result body says `status=error`; tool invocation alone proves nothing.
The desk requires a successful matching API execution record and a structured result. MCP auto-pagination has a
cap, so even a successful response does not certify exhaustive coverage. Collection still determines coverage.
For example, EC2 DescribeRegions without AllRegions reports enabled regions; absence of disabled opt-in regions
is expected filtering, not evidence that a page was truncated. Never infer the cause of missing rows from a cap warning.

Consult approved OKF before recommending changes. Cloud observations are time-bound evidence, not permanent
organization policy. If the user wants to preserve guidance, draft a cited Reference/runbook through rg-knowledge
for review; don't automatically approve MCP output. Keep remediation in the proposal/validation workflow.
