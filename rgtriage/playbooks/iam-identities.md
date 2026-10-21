# IAM users, keys and policies (IAM.1, IAM.2, IAM.3, IAM.5, IAM.8, IAM.22, Access Analyzer unused access, GuardDuty IAMUser anomalies)

**Means:** full-admin customer policies (`"Action":"*","Resource":"*"`), policies attached directly to users,
keys older than 90 days, console users without MFA, unused credentials or roles.

**Verify:** `rgtriage aws iam list_access_keys --params '{"UserName":"<u>"}'`,
`rgtriage aws iam get_access_key_last_used --params '{"AccessKeyId":"AKIA..."}'`,
`rgtriage aws iam list_attached_user_policies --params '{"UserName":"<u>"}'`, `get_policy_version`.

**Terraform:**
- Replace `aws_iam_user_policy_attachment` with groups (`aws_iam_group_policy_attachment` + `aws_iam_user_group_membership`), or better IAM Identity Center / roles.
- Narrow `"*"` actions in `aws_iam_policy_document` to the actions actually used (Access Analyzer can generate a policy from CloudTrail).
- Remove `aws_iam_access_key` for humans; workloads use roles (instance profile, IRSA, GitHub OIDC).
- Unused roles/users: delete after confirming `RoleLastUsed` / `PasswordLastUsed`.

**GuardDuty IAMUser/AnomalousBehavior or credential exfiltration:** treat the principal as possibly compromised.
Check CloudTrail for that key (`lookup_events` with `AttributeKey=AccessKeyId`). The operator deactivates the key
(`aws iam update-access-key --user-name U --access-key-id K --status Inactive`), rotates it and reviews its changes.

**Trade-offs:** removing permissions can break automation; stage changes and watch AccessDenied in CloudTrail.
