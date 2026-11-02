# IAM condition review

Check service/action support for each context key. Distinguish key names from values.

- ForAllValues can match an absent multivalued key. If an Allow requires that key, also require
  `Null: {"aws:TagKeys": "false"}` for that key. This restricts this statement; other Allows still matter.
- ForAnyValue does not match an absent key. To deny absence, use a separate applicable Deny with
  `Null: {"aws:TagKeys": "true"}`. Adding it to the same false-matching condition does not create OR logic.
- `aws:TagKeys` constrains names. Require intended tag values separately through supported RequestTag keys.
- Do not use set operators on single-valued RequestTag, ResourceTag or PrincipalTag context keys.
- Context key names are case-insensitive; value matching depends on the operator. IgnoreCase operators
  compare values, not tag-key spelling. Review duplicate-case tags and use a consistent naming policy.

Test absent key, permitted values and forbidden values. State whether tags are required or optional.
Simulation evaluates supplied scope/context and has limitations; inspect organization decision details when
returned. A simulated Allow is not proof of a successful real action.

Sources:
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-single-vs-multi-valued-context-keys.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html
