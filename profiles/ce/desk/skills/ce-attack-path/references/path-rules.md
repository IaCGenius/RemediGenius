# Attack-path connection rules (local)

Only link steps when both ends are observed in receipts:

- Public S3 bucket (BlockPublicPolicy=false or policy with Principal "*") may connect to data-exfiltration inference if the bucket contains objects (object count observed) or is referenced by another finding.
- IAM role with `s3:*` or `iam:*` on "*" may connect to privilege-escalation inference if the role is assumable (trust policy observed).
- Open security group (0.0.0.0/0 on 22/3389) may connect to initial-access inference only if the instance ID is also in a finding.

Do not create additional hops beyond the observed resources.
