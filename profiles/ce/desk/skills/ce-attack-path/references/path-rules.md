# Evidence-linked attack-path review

Each link requires evidence for the principal, permission, reachable resource and applicable conditions. Describe missing links as hypotheses, not a demonstrated path.
- BlockPublicPolicy=false alone does not make an S3 bucket public. Inspect effective account/bucket public-access blocks, policy/ACL grants, conditions and explicit denies. A wildcard Principal can be restricted by conditions. Object presence is not proof of readable or sensitive data.
- A broad IAM action is not proof of escalation. Inspect trust, caller authorization, boundaries, SCPs and conditions where available. s3:* alone does not establish IAM escalation; an observed trust policy does not prove anyone can assume the role.
- A security-group ingress rule is not proof of Internet reachability or compromise. Identify attachment, addresses/routes, NACLs, listener and authentication evidence; report missing components.
- Link only observed identities/resources. At most three hypothesized steps; no fabricated hops or exploit execution.

Reference: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html
