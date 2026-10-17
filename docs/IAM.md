# IAM: who can do what

The operator provisions CE. Hermes never receives administrator credentials.
The authoritative policies below are readable Terraform, separated into `iam.tf`.

| Role | Who assumes it | Can do | Boundary / limits | Source |
|---|---|---|---|---|
| Read executor | Lambda | AWS SecurityAudit/ViewOnlyAccess metadata permissions, explicit inventory actions, assume configured member roles, write evidence prefixes and logs | CE tools do not admit cloud mutations or arbitrary object-content reads | `modules/aws-read-executor/iam.tf` |
| Discovery collector | Lambda | Describe native-source availability; write its catalog and logs | Remediate resources | `modules/native-source-discovery/iam.tf` |
| Scheduled worker | Lambda | Invoke read executor, read/write scheduled evidence, write logs | Call a model or apply fixes | `modules/assurance-schedule/iam.tf` |
| Scheduler invocation | EventBridge Scheduler | Invoke scheduled worker | Investigate or read the account directly | `modules/assurance-schedule/iam.tf` |
| Workstation invoker | Explicit operator IAM principal | Invoke executor and read returned evidence prefixes | Direct customer-resource mutations | `deploy/aws-workstation/iam.tf` |
| Spot reader invoker | Spot host | Invoke executor and read returned evidence prefixes | Host/admin permissions | `deploy/aws-native/iam.tf` |
| Spot host | EC2 | Bootstrap S3 source, exact model/dashboard secrets, attach retained volume, SSM, invoke discovery and assume reader role | Model does not receive host credentials; explicit SSM parameter deny | `deploy/aws-native/iam.tf` |
| Member read role | Exact trusted executor with configured external ID | SecurityAudit/ViewOnlyAccess plus inventory reads in member account | CE tools do not admit remediation | `deploy/aws-native/member-read-role.json` |
| Optional generic read role | Configured principal with external ID | SecurityAudit/ViewOnlyAccess plus inventory reads | CE tools do not admit fixes | `modules/aws-read-access/iam.tf` |
| Optional storage role | Configured principal | Dedicated storage prefixes per module policy | Arbitrary account administration | `modules/workspace-storage/iam.tf` |

Resource addresses remain unchanged when IAM moves between files. Before an
upgrade, inspect the plan: a file split alone must not replace roles.

## Inventory identity and execution boundary

The inventory candidate expands IAM metadata-read permission using AWS-managed
SecurityAudit and ViewOnlyAccess policies. These policies are broader than CE's
admitted tool catalog and AWS can update them. Review their current contents before
deployment. The managed attachments do not inherit the region condition on the
separate inline policy; the executor enforces the configured target/region on each
request. Organizational SCPs and permission boundaries remain effective.

Hermes submits structured SDK requests to Lambda; it never assumes the customer
role itself. Lambda assumes a configured member role with its external ID and a
session policy. Ordinary requests retain their single-operation session policy.
Cloud Control requests also use audit/view session policies so AWS resource handlers
can perform downstream reads. The target role must grant those permissions too.
The chat cannot select RoleArn or a private Cloud Control handler. No direct
Bedrock provisioning or model-invocation API is admitted by this inventory change.

Responses and receipts go to the configured evidence prefix in S3. A missing
handler permission is returned as a failed source read; it does not trigger an
automatic permission grant or an administrator-credential fallback.

## Operator policies

[deploy/operator-iam](../deploy/operator-iam) creates two **administrator-assigned**
managed policies: provision and daily use. It does not attach either automatically.
Provide exact account, region, stack names, buckets and model-secret ARNs. Outputs
`provision_json` and `daily_use_json` can be pasted into the IAM console instead.

Provisioning is privileged: it can manage the named roles/policies, pass them to
AWS services, and create infrastructure in the selected region. It is intended
for trusted infrastructure administrators, not Hermes or untrusted operators.
The EC2/Auto Scaling statement is region-wide; this is an explicit starting
policy, not a claim of universal least privilege. Apply organizational boundaries
and SCPs. Admins must pre-create required AWS service-linked roles when missing.
Daily use provides the invoker, exact secrets and tagged CE tunnel access; it does
not provision, destroy, publish knowledge or grant general SSM command execution.
Customer-managed KMS keys may need additional explicitly scoped decrypt rights.

## Derive and test the policy for your installation

1. In a sandbox, use a dedicated provisioning role and enable CloudTrail logging.
   Exercise create, update, stop/start and destroy, including your optional features.
2. Use IAM Access Analyzer **Generate policy** for that role and exact activity window.
   It requires a trail and a service role permitted to read its logs.
3. Review the generated policy: not every service has action-level generation;
   unexercised operations and PassRole may need explicit additions. Preserve
   resource and region constraints, not just the observed action list.
4. Attach the reviewed policy to a fresh test role with no other grants. Re-run
   create/update/destroy and daily-use flows; record denied actions and correct
   only the necessary permissions. An administrator-only pass is insufficient.

[Official policy-generation guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-generation.html).
