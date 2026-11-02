# Terraform provider coverage

Use for whether a resource or feature is supported. Prefer the repository lock-file version; for an unpinned
question state the versions checked. Confirm resource existence before discussing arguments.

Compare `hashicorp/aws` and `hashicorp/awscc` where relevant. Classify results as native resource verified,
Cloud Control provider resource verified, or support not established by the inspected sources. The latter is
not proof of no support. Adding awscc requires another provider and a reviewed lifecycle/import plan.

Search results may be incomplete. A missing service slug or top-match result is not an exhaustive resource
index. Verify exact resource docs for the chosen version and compare semantics rather than names. An open
issue can be stale; it does not alone prove an unresolved gap. A CloudFormation type does not establish
that a generated awscc resource is available in the chosen release.

Report the source/version and uncertainty. Do not dump whole provider catalogs into chat.
