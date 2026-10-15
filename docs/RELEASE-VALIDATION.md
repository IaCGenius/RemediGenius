# v0.1.0 release validation — 15 October 2026

Scope: AWS us-east-1, Qwen 3.8 Max, pinned native Hermes and one `ce-desk` profile.
Bedrock is deferred by the owner. The model/image and permission boundaries were
not changed for this cleanup.

| Check | Result |
|---|---|
| Retained Windows test suite | 74 passed |
| Exported source, Windows | 74 passed |
| Exported source, disposable Linux environment | 74 passed |
| Native Qwen with renamed package | Completed successfully in 118 seconds; fresh Config definitions/status, scope and receipts; missing knowledge remained unknown |
| Critic context | Both loaded skill hashes included, four evidence excerpts, no skill omission |
| Terraform validation / formatting | Passed for renamed native stack |
| Migration plan using copied state | 0 additions, 3 in-place updates, 0 destructions; not applied |
| Python distribution | Clean 0.1.0 wheel installed separately; knowledge modules and offline sample passed with network blocked; legacy console/API excluded; upstream rule licence retained |

The reduced test count reflects removal of archived console/builder components
and their tests, not removal of failing tests for retained functionality. Complete
pre-cleanup source and test history were preserved before removal. Constructed
contract tests and offline demo data are not presented as live AWS evidence.

Pi's advisory grader gave the native run full marks but noted that suggested
follow-up operation availability was not independently established in its packet.
The observed read results and loaded context were inspected separately. Model
critique is not proof of every recommendation. No customer remediation was run.

The existing cloud deployment was left running on its prior accepted archive;
private state/configuration backups were verified. This is not a claim of a new
cloud deployment or browser UI test for v0.1.0. The native package was exercised
in isolated local Docker with real scoped AWS reads and Qwen. Prior actual
workstation/Spot/UI acceptance is retained in [MVP acceptance](MVP-ACCEPTANCE.md).

GitHub Actions remains billing-blocked; local verification is the owner-approved
alternative. See [upgrade instructions](UPGRADING.md) before changing a retained
installation and [limits](LIMITS.md) for the release boundary.
