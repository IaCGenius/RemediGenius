# IAM policy review prompts

Quote the observed Effect, Action/NotAction, Resource/NotResource, Principal and Condition before interpretation. Wildcards in Deny statements can restrict access; do not flag them as grants.
- Broad Allow actions/resources are candidates for investigation, not proof of unnecessary access. Some AWS actions require Resource="*". Identify actual workload needs and supported resource-level permissions before narrowing.
- Review trust and caller policies separately, including boundaries/SCPs/conditions when available. Do not invent callers, resource ARNs or usage history.
- aws:SourceAccount/aws:SourceArn address supported AWS service-to-service confused-deputy cases; their absence is not a generic cross-account defect. Third-party role trust may instead require ExternalId and explicit trusted principals, depending on the integration.
- A limited CloudTrail window cannot prove an action is unused forever. Supply a draft plus missing usage/dependency context, verification and rollback. Preserve service-linked-role ownership.

References: https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html and https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html
