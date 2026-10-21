# Root account use and protection (GuardDuty Policy:IAMUser/RootCredentialUsage, IAM.4, IAM.6, IAM.9, CloudWatch.1, CIS 1.x)

**Means:** the root user makes API calls, has access keys, or lacks (hardware) MFA. IAM policies cannot
restrict root; only SCPs can, and not in the management account. A high GuardDuty `Service.Count` of
root API calls usually means root access keys are embedded in a script or tool.

**Investigate (read-only):**
- Finding context: API, source IP, ASN, country, first/last seen, count (`rgtriage show <ref>`).
- `rgtriage aws iam get_account_summary` → `AccountAccessKeysPresent`, `AccountMFAEnabled`.
- `rgtriage aws cloudtrail lookup_events --params '{"LookupAttributes":[{"AttributeKey":"Username","AttributeValue":"root"}],"MaxResults":50}'`
  → which APIs, IPs and user agents. Unknown IP/ASN = treat as compromise.

**Fix (operator):**
1. Not you: rotate the root password, enable MFA, delete root access keys, then review CloudTrail for persistence (new users, keys, roles, trust policy changes).
2. Yours (a tool using root keys): give the tool a least-privilege IAM role, switch it, then delete the root keys.
3. Enable hardware or virtual MFA on root (console only; not possible with IaC).
4. In an AWS Organization: use centralized root access management for member accounts and an SCP that denies root:
```hcl
data "aws_iam_policy_document" "deny_root" {
  statement {
    sid       = "DenyRootUser"
    effect    = "Deny"
    actions   = ["*"]
    resources = ["*"]
    condition {
      test     = "StringLike"
      variable = "aws:PrincipalArn"
      values   = ["arn:aws:iam::*:root"]
    }
  }
}

resource "aws_organizations_policy" "deny_root" {
  name    = "deny-root-user"
  type    = "SERVICE_CONTROL_POLICY"
  content = data.aws_iam_policy_document.deny_root.json
}
```
5. Alerting (CloudWatch.1): metric filter
`{ $.userIdentity.type = "Root" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != "AwsServiceEvent" }` (see cis-metric-filters).

**Trade-offs:** SCPs never apply to the management account. Deleting root keys breaks whatever uses them;
identify the user agent first.
