# Azure and GCP: what carries over, what changes

Hermes and the agents run on any cloud (Docker). What changes is the layer that touches the cloud.

| Piece | AWS (this release) | Azure (planned) | GCP (planned) |
|---|---|---|---|
| Agents, skills, Morning Brief | Docker on EC2 | Same, Docker on a VM | Same, Docker on Compute Engine |
| Read-only access | IAM role: ViewOnly + SecurityAudit + data-read denies + ExternalId | Service principal: Reader + Security Reader, no data actions; workload identity federation | Service account: Viewer + Security Reviewer (custom role, no data permissions); workload identity federation |
| Collector + rules (no AI) | Own collector, 3 checks | Prowler (Apache-2.0) as collector, mapped to SkillResult | Prowler, mapped to SkillResult |
| Kiosk | Lambda + code signing + Step Functions | Azure Functions + Durable Functions; signing enforced in the gate | Cloud Run functions + Binary Authorization + Workflows |
| No inbound ports | SSM | Azure Bastion / Run Command | IAP TCP forwarding |
| Secrets | Secrets Manager + KMS | Key Vault | Secret Manager + Cloud KMS |
| Terraform | `deploy/aws` | `deploy/azure` | `deploy/gcp` |

## Seams already in place

- Results carry `provider` (`aws` / `azure` / `gcp`; validated by `skillresult.py`). Facts files carry `provider`.
- Checks are folders of rules (`profiles/analyst/skills/remedigenius/<check>`), so new checks are new folders.
- The deploy inputs are the same for every cloud: model endpoint and key, schedule, accounts, kiosk on or off.

## Order

1. AWS (this release).
2. GCP: Binary Authorization gives real signature enforcement for the kiosk.
3. Azure: more of the enforcement sits in the gate.

Rough effort per cloud: a week for hosting and read-only access, a week for Prowler collection and mapping, 2–3 weeks
for the kiosk.
