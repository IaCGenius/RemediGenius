---
type: Guide
title: "Evidence: identity and trust"
description: Who can assume a role or use a principal, read from the trust policy itself; GitHub OIDC, SAML, external accounts and services.
tags: [remedigenius, evidence, iam, trust, oidc]
sources:
  - {id: oidc, resource: "https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services", title: Configuring OpenID Connect in Amazon Web Services, author: github-documentation}
  - {id: aa, resource: "https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-findings.html", title: IAM Access Analyzer findings, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
---

Question shapes: "who can assume this role?", "does it trust every GitHub repository?", "which roles can be assumed from
outside the account?", "is this external account expected?".

## Reads that decide it
1. `iam get_role RoleName=<name>`: `AssumeRolePolicyDocument` is the evidence. Read `Principal` (AWS account or role,
   `Federated` provider, `Service`) and every `Condition` key. Also `RoleLastUsed` and `CreateDate`.
2. GitHub OIDC[^oidc]: the `token.actions.githubusercontent.com:sub` condition decides the scope.
   - none → any workflow in any repository that can request a token for this audience;
   - `repo:owner/*` or `*` → every repository of that owner (or everyone);
   - `repo:owner/repo:*` → one repository, but any branch, tag, environment **and pull request** (`:pull_request`);
   - `repo:owner/repo:ref:refs/heads/main` or `:environment:prod` → pinned.
   Check `:aud` is `sts.amazonaws.com`.
3. External AWS principals: is there an `sts:ExternalId` or `aws:PrincipalOrgID` condition? Is the account in the
   organization (`organizations describe_account`, management or delegated account only)?
4. Many roles at once ("which roles trust outsiders?"): `iam list_roles` returns every trust policy; page with `Marker`
   until `IsTruncated` is false and say if you stopped early.
5. A second opinion from AWS: `accessanalyzer check_no_public_access` (policy document + resource type) evaluates
   without reading your assumptions into it. It is an evaluation, not observed configuration.

## Limits to say out loud
- An Access Analyzer finding's `condition` summary is not the policy. An empty summary does not prove a missing
  condition; the trust policy decides[^aa]. Access Analyzer re-analyzes on change, but its timestamps do not tell you
  when the policy changed; without CloudTrail (90 days) or Config history you cannot date a change.
- `RoleLastUsed` is approximate and per region; absence of CloudTrail events beyond 90 days says nothing.

## Stop when
The principal and every condition are quoted from the live document and mapped to who can assume the role. Expand only if
the user asks what the role can do (load the effective-permissions guide) or usage looks suspicious (rg-investigate).

Related: [effective permissions](/remedigenius/guides/evidence-effective-permissions.md) ·
[identity and root](/remedigenius/practices/identity-and-root.md) · [where to look](/remedigenius/guides/where-to-look.md)

[^oidc]: Configuring OpenID Connect in Amazon Web Services
[^aa]: IAM Access Analyzer findings
