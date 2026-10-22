# AWS capabilities consumed — RemediGenius Community Edition

Reviewed each release. RemediGenius-CE consumes AWS-native conclusions where they exist and adds organizational
context and the code fix. boto3 floor: 1.42 (Security Hub V2 APIs). Last reviewed for v0.3.0 (2026-10).

| Service | API used | Consumed | Not consumed (yet) |
| --- | --- | --- | --- |
| AWS Security Hub (current, OCSF) | `DescribeSecurityHubV2`, `GetFindingsV2` (`class_name = Exposure`) | exposure findings: severity, traits, related resources / attack path, remediation, as AWS reported them; AWS Critical/High exposures are never ranked below P1/P2 | other OCSF classes (read through the services directly or CSPM), resource inventory (`GetResourcesV2`), trends |
| Security Hub CSPM | `GetFindings` (ASFF), finding aggregators | control failures, third-party findings | insights |
| GuardDuty | `ListFindings`, `GetFindings` | threat findings; Extended Threat Detection attack sequences (`AttackSequence:*`) ranked first | malware scan details, runtime coverage statistics |
| Inspector | aggregation APIs, `ListFindings` | CVEs, exploitability, EPSS, network reachability, fix units | code security, SBOM export |
| IAM Access Analyzer | `ListFindingsV2`, `GetFinding`, policy checks | external access (trust read from the policy itself), internal access, unused access (summary) | policy generation |
| IAM | `Get*`, `List*`, `SimulatePrincipalPolicy` | trust and permission documents, simulator verdicts including SCPs | — |
| AWS Config | compliance by rule | non-compliant rules | configuration timelines beyond on-demand reads |
| CloudTrail | `LookupEvents` (90 days, management events) | who / what / when for investigations | CloudTrail Lake, data events (hand-off: [beyond the desk](../rgtriage/knowledge_base/guides/beyond-the-desk.md)) |
| CloudWatch, Health | alarms, Health events | operational context | — |
| EC2, Lambda, RDS (footprint) | first-page lists per region | regions with resources outside the scan scope | — |

When a capability is off in a region, coverage says so and the board shows it as a blind spot.
