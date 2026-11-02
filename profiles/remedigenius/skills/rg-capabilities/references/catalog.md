# Capability choices

Reviewed 2026-11-01. Discover available tools at runtime; provider catalogs and authentication can change.

| Capability | Existing implementation | Onboarding and scope | When useful |
| --- | --- | --- | --- |
| AWS documentation and vendor skills | AWS Knowledge MCP, native Hermes `aws-knowledge` catalog entry | No account; HTTPS endpoint. Select documentation reads and, when desired, `aws___retrieve_skill` (excluded by the pinned Hermes catalog by default) | AWS controls, IAM procedure guidance, exact verification API fields |
| Terraform Registry | HashiCorp official `terraform-mcp-server` | Public Registry tools need no HCP account. Use a version-pinned local runtime; public documentation tools only | Provider arguments and module interfaces for proposals |
| Public repository guidance | Native `deepwiki` catalog entry | No credentials for public repositories; pin/verify upstream revision for exact code claims | Prowler check navigation and interpretation |
| Organization knowledge | Existing Atlassian, Notion, Dropbox, GitLab, Linear, Craft catalog entries; official Drive MCP configuration | User-selected scope and provider sign-in; read tools only | Policies, runbooks, ownership and prior decisions → OKF drafts |
| S3-backed knowledge | AWS Labs Bedrock Knowledge Base Retrieval MCP | Existing KB and independently scoped retrieval role; not blanket S3/audit access | Cited passages when a user already has a KB |
| Cost implications | AWS Pricing MCP; Billing and Cost Management MCP for actual spend | Separate AWS permissions; pricing estimate versus observed bill must remain distinct | Estimate incremental remediation cost; only if cost is part of the decision |
| Account investigation | Existing desk first; CloudTrail, CloudWatch or IAM MCP only for a demonstrated gap | Separately scoped identity and reviewed tools, not enabled by default | A needed query the desk cannot express; no automatic IAM expansion |
| Managed AWS account reads | Official AWS MCP through the desk's optional bounded transport | Reuses an explicit audit role; see [connection choices](aws-connection.md). No general script tool in Hermes | Configuration evidence using existing structured account-read commands |
| General AWS operations | AWS API / Cloud Control MCP | Broad capabilities require separate qualification; no duplicate default connection | Only a demonstrated gap beyond the bounded desk workflow |

AWS deprecated its old Terraform MCP in favor of HashiCorp's official server. Do not install the old package or
recreate its API wrapper. Local Terraform validation already belongs to the desk; HashiCorp's public Registry
tools supply the missing documentation. HCP run management is a different execution model and is not enabled.

AWS Agent Toolkit provides security, IAM, storage, networking, observability and other skills. Prefer retrieving
the relevant current skill through AWS Knowledge rather than copying a broad package. Full Well-Architected
reviews have their own coverage and scoring contract; do not claim one from a few security findings.

Sources:
- https://awslabs.github.io/mcp/
- https://github.com/awslabs/mcp/blob/main/docs/migration-terraform.md
- https://developer.hashicorp.com/terraform/mcp-server/reference
- https://docs.aws.amazon.com/agent-toolkit/latest/userguide/skills.html
- https://github.com/aws/agent-toolkit-for-aws/tree/main/skills
