# Least-privilege deterministic rules

Apply these rules verbatim to statements found in the receipt. Do not expand them.

- `Action: "*"` on a non-service-linked role is a candidate for reduction. Cite the exact statement.
- `Resource: "*"` combined with a data-plane action (e.g., `s3:GetObject`, `dynamodb:Query`) is a candidate. Cite the statement.
- Trust policy that allows `sts:AssumeRole` from `"AWS": "*"` or a broad principal is a candidate. Cite the principal.
- Missing `aws:SourceAccount` or `aws:SourceArn` condition on a cross-account trust is noted as a gap only if the receipt shows the trust document.

Record each match as an observed fact before suggesting a narrower alternative.
