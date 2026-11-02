# Useful MCP capabilities for RemediGenius CE

This is unreleased work validated on the current disposable Spot lab. The purpose is to complete a remediation
or knowledge task, not accumulate connections. Existing Hermes MCP discovery, catalog, configuration, tool
selection and authentication remain the integration layer. `rg-capabilities` supplies RemediGenius-specific
routing; `rg-iac-fix`, `rg-onboard` and `SOUL.md` point to it.

## What an individual user gets

The account connection reevaluation is in [AWS connections](AWS-CONNECTIONS.md). Managed AWS MCP is now an
standard bounded desk transport on EC2, not a general-purpose script tool in Hermes. This supersedes the initial
catalog-only assessment below; public Knowledge, Terraform and DeepWiki remain separate native connections.

| Need | Reused capability | Result for the user | Setup |
| --- | --- | --- | --- |
| Understand an AWS finding/control | AWS Knowledge MCP | Current AWS explanation and exact API verification fields with source citations | Native Hermes catalog, no account |
| Propose correct Terraform | HashiCorp official Terraform MCP | Resource arguments for the repository's provider version | Public Registry runtime, no HCP account |
| Use AWS specialist guidance | AWS Knowledge `aws___retrieve_skill` | Relevant AWS-authored skill and references loaded on demand | Enable this read tool explicitly; pinned Hermes excludes it by default |
| Understand Prowler/public code | Existing DeepWiki MCP | Repository navigation and explanation; verify exact code against upstream revision | Native Hermes catalog, no account for public repositories |
| Bring organization knowledge | Existing vendor document MCPs | Selected documents become cited References and unreviewed OKF concepts | Provider sign-in and chosen document scope |

For example, a Terraform question selects Registry search/details, preserves the requested provider version,
then uses AWS documentation for the verification API. A real finding fix continues through the desk's existing
proposal, validation and proof-of-done workflow. An IAM conceptual question can discover `aws-iam`, retrieve it
and its relevant reference, and explain the policy condition without reading any AWS account.

## Dynamic onboarding and use

1. The skill identifies the missing capability and the question it would answer.
2. In **Knowledge → Sources → Manage connections in Hermes**, add the existing vendor/catalog entry to profile
   `remedigenius`. Select the needed read tools and complete provider sign-in there.
3. **Test connection** uses Hermes's native MCP probe. Its tool count proves a handshake, not useful retrieval.
4. Start a fresh chat (or use Hermes's supported MCP reload), ask the representative question shown in Sources,
   and verify the actual tool result, citation and outcome.

The agent uses deferred tool discovery for available connections and retrieves AWS vendor skills on demand.
It does not silently install arbitrary executables or grant itself AWS access. Configuration changes do not
guarantee an existing chat has reloaded its tools. Existing authenticated document providers remain subject to
their own access checks; a disabled/catalog-only entry is not certified.

### AWS Knowledge and on-demand AWS skills

Use the existing Hermes `aws-knowledge` catalog entry. CLI equivalents:

```sh
hermes -p remedigenius mcp install aws-knowledge
hermes -p remedigenius mcp configure aws-knowledge
hermes -p remedigenius mcp test aws-knowledge
```

The selected tools used in this lab are `aws___read_documentation`, `aws___search_documentation`,
`aws___list_regions`, `aws___get_regional_availability` and `aws___retrieve_skill`. Skill retrieval was explicitly
enabled for this evaluation. Search results supply the exact skill name; the agent retrieves only the relevant
skill and linked reference. No broad AWS skill package is copied into the product. Vendor operational procedures
do not grant terminal access, AWS writes or approval authority.

### Optional Terraform runtime on the standard AWS host

Run the reviewed installer on the **CE host**, from the release/source tree:

```sh
sudo bash deploy/aws-single/install-terraform-guidance.sh
```

It extracts HashiCorp's official v1.4.1 binary from a digest-pinned image, installs it in the persistent Hermes
data directory and uses Hermes's existing configuration helper to register `terraform-registry`. Linux x86_64
and the standard `/data/hermes` → `/opt/data` container mount are required. A different existing connection is
preserved and reported for review. An identical connection keeps its enabled/disabled state.

The MCP runs over stdio with a clean environment and a nonexistent home directory, with no AWS/HCP/model
credentials. Both server startup and Hermes tool selection limit it to seven public Registry reads:
`search_provider_docs`, `get_provider_details`, `get_provider_capabilities`, `get_latest_provider_version`,
`search_modules`, `get_module_details`, `get_latest_module_version`.

HCP workspace/run mutation tools are not exposed. Local Terraform validation stays in `rg_triage`, which already
validates a scratch copy without applying. This is an upstream MCP installation, not extracted/reimplemented
Registry API code. AWS's old Terraform MCP is deprecated in favor of HashiCorp's official implementation.

The installer is optional and has not been wired into every fresh CE deployment or released archive. Its
existing-connection rerun passed on the lab; a separate fresh-stack release gate remains required.

## Catalog review: useful next, but not all enabled

| Candidate | Value | Decision for this edition |
| --- | --- | --- |
| AWS Pricing | Incremental cost of a proposed fix | Optional when cost is part of the question; separate permissions and a representative pricing query required |
| AWS Billing and Cost Management | Actual spend/anomalies | Optional, not equivalent to public list prices; no access granted in this lab |
| AWS CloudTrail / CloudWatch / IAM MCPs | More specialized investigations | First use existing desk reads; add only a demonstrated gap through a separately scoped connection |
| Bedrock Knowledge Base Retrieval | Cited passages from existing S3-backed knowledge | Useful for users who already have a KB; not a generic bucket ingestion connector |
| Managed AWS MCP | Live AWS configuration reads | Default EC2 bounded desk transport qualified below; no general script tool exposed to Hermes |
| AWS API / Cloud Control | Broad cloud operations and workflows | No duplicate default connection; separately qualify a demonstrated gap |
| AWS security/IAM/storage/networking/observability skills | Service-specific procedures | Discover on demand; map allowed reads to the desk and keep changes as proposals |
| AWS Well-Architected review skill | Broad architecture assessment | Separate opt-in workflow with its own completeness/scoring contract; not implied by a triage answer |
| HashiCorp Terraform style/test/refactor skills | General Terraform authoring and testing | Reviewed as optional references; retain repository conventions and pins. Do not introduce module refactors or provider upgrades for a small security fix |
| HashiCorp `provider-docs` skill | Author documentation for a Terraform provider | Not a provider-document lookup skill; not installed for CE remediation |
| Atlassian, Notion, Dropbox, GitLab, Linear, Craft, Drive | Organization context | Existing connectors; authenticated reads remain pending operator sign-in/material |

Public documentation requests reveal the search terms/resource types to the provider. Do not send secrets,
private Terraform state or full finding payloads to documentation tools. General AWS MCPs are not a way around
the desk's scoped access boundary. No new AWS permissions were granted for this work.

## Live evaluation and remaining limits

- Managed AWS MCP reevaluation: official proxy library 1.7.0 installed with existing desk pins preserved,
  then constrained against a captured Linux dependency snapshot. `pip check` and constrained installer rerun
  passed. A real region read through the agent-to-desk socket returned 17 regions and the managed transport
  evidence marker. Writes, sensitive-data reads, malformed parameters and an unknown account failed. A
  separately narrowed STS session produced a real IAM denial through MCP; no evidence was accepted, and a
  subsequent allowed read recovered. No IAM changes were made. Backups/hashes and private evidence are in
  lab steps 053–068. Browser session `bda04f5e` used three calls (skill, tool description, one desk read),
  reporting 17 regions, managed MCP and unverified completeness. Startup displayed 11 tools through native
  discovery; this change adds no model-facing AWS schemas. One explanation incorrectly linked absent opt-in
  regions to truncation; the on-demand reference now distinguishes API defaults/filtering from pagination.
  This is not proof of exhaustive account coverage. Focused local checks: 32 passed; initial Windows sandbox
  run stalled in asyncio's socketpair creation and passed outside that sandbox. Fresh install/replacement,
  OAuth, session expiry, multi-account end-to-end and large-result pagination remain release gates.
  Final socket replay passed all five cases after the error-handling changes. Explicit rollback returned a
  successful direct SDK read, then managed mode was restored and verified. The browser follow-up loaded
  only `rg-capabilities` and its connection reference (two skill calls, no AWS call), correctly distinguished
  DescribeRegions filtering from unverified pagination, and explained credential isolation and zero added
  AWS tool schemas. Screenshot: private `071-aws-managed-guidance.jpg`. Live skill edits from the maintainer's
  earlier testing were preserved rather than overwritten; those independent edits still need release review.

- Browser DeepWiki walkthrough for `prowler-cloud/prowler` Kubernetes hardening completed:
  visible calls included one wiki-structure read, one wiki-content read, six questions,
  and local reads/search of the returned large document (12 tool calls total including
  discovery). The answer covered five hardening areas, representative check IDs, verification
  suggestions, Kubernetes versus EKS scope, and index/version uncertainty. Private screenshot:
  `052-deepwiki-prowler-k8s.jpg`. No account/cluster or mutation tools appeared in the visible
  execution. This proves repository retrieval, not independent verification of every check ID.
  Release follow-ups: reduce repeated questions/full-wiki retrieval, enforce concise answers,
  and review overly broad claims about host namespaces, anonymous authentication, audit-log
  destinations and signing-key revocation before treating output as operational guidance.
- A second browser walkthrough asked about `ForAllValues:StringEquals` and absent
  `aws:TagKeys`. The visible execution loaded `rg-capabilities`, searched AWS documentation,
  called AWS skill retrieval and read documentation. The answer identified `aws-iam`,
  explained the absent-key pitfall and included a `Null: false` guard and AWS source links.
  Evidence: private `048-browser-aws-skills.jpg`. This is a routing/retrieval demonstration,
  not approval of a deployable policy. Follow-up review is needed for the answer's claim
  about optional tags and the terminal's duplicated condition lines. The direct SQLite
  metadata check returned no rows, so it does not independently establish the skill argument;
  the skill name here is attributed to the answer. A stale local SSM tunnel was restarted;
  server health remained active with HTTP 200. No server restart was needed.
- The maintainer's browser walkthrough caught a deployment gap: the process-wide
  `HERMES_TUI_TOOLSETS` override hid enabled MCPs from browser chat, despite successful
  connection probes and CLI requests. The AWS and workstation launchers now leave MCP
  discovery to native profile selection, while restricting default-profile built-ins.
  The disposable AWS lab was patched and restarted. A fresh browser chat visibly loaded
  `rg-capabilities`, made two Registry searches and two detail reads, and returned the
  5.100.0 example with all four public-access flags. This validates browser tool routing;
  it does not certify every statement in the generated answer. The answer's policy-status
  explanation still needs review: policy publicness and effective access are distinct.
  Focused host checks passed (21 passed, one skipped); the workstation launch change
  has not yet been exercised in Docker. Private evidence includes the browser screenshot.
- Native Hermes and browser connection tests passed: Terraform Registry seven tools, AWS Knowledge five,
  DeepWiki three. The Sources screen produced no browser JavaScript errors.
- A real Terraform request selected `rg-capabilities`, searched `hashicorp/aws` **5.100.0**, retrieved resource
  details, and used AWS documentation. Product tool-call traces establish actual use, not just an answer's claim.
- A real IAM request searched AWS guidance, retrieved `aws-iam` and `references/common-pitfalls.md`, and described
  `ForAllValues` with a `Null: false` condition. No account-read tool was used in these requests.
- Live answers exposed unwanted board references and an unnecessary `init -upgrade` suggestion. The local
  routing/startup instructions were corrected and the same requests replayed; detailed results are recorded in
  the private lab evidence. These examples are behavioral samples, not a comprehensive correctness guarantee.
  A second complete-answer check caught a trailing finding reference missed by the 4,000-character trace excerpt.
  The startup hook now injects the board only for recognized greetings/open-status requests; focused questions
  obtain evidence through tools and do not trigger the hook's background refresh. Hosts without the
  `user_message` hook field keep the legacy behavior; the pinned Hermes supplies it. Explicit board requests
  outside those greeting phrases still work through `rg_triage action=digest` or `/triage`.
  Final complete-answer checks passed for both requests: citations, correct Terraform version/arguments or IAM
  Null condition, no unsolicited upgrade and no real board references/account reads. Numeric example IDs were
  distinguished from actual board references rather than treated as leakage. Both installed plugin copies were
  synchronized; baseline and intermediate transcripts remain available for review.
- The first Terraform sidecar attempt was blocked by the existing network isolation. The sidecar was removed;
  stdio succeeded without weakening firewall rules. The optional installer rerun preserved the matching native
  connection. Runtime version/image digest and file hashes are recorded.
- New skill metadata validation and five focused startup-context regression checks passed. Full release gates,
  authenticated provider certification, broad AWS answer coverage and automatic source refresh remain pending.

Private manifests and evidence remain under `.rgce/knowledge-live-20261101/` and `/data/rg-lab/` on the disposable
lab. No release was tagged or published. The lab remains running for maintainer review.

## Upstream sources reviewed

- [AWS MCP catalog](https://awslabs.github.io/mcp/)
- [AWS Terraform MCP migration](https://github.com/awslabs/mcp/blob/main/docs/migration-terraform.md)
- [HashiCorp MCP reference](https://developer.hashicorp.com/terraform/mcp-server/reference)
- [HashiCorp v1.4.1 tool definitions](https://github.com/hashicorp/terraform-mcp-server/blob/v1.4.1/pkg/toolsets/registry.go)
- [AWS skill discovery](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/skills.html)
- [AWS Agent Toolkit skills](https://github.com/aws/agent-toolkit-for-aws/tree/main/skills)
- [HashiCorp skill catalog](https://github.com/hashicorp/agent-skills/blob/main/SKILLS.md)
- [HashiCorp Terraform style skill](https://github.com/hashicorp/agent-skills/blob/main/plugins/terraform/skills/terraform-style-guide/SKILL.md)
