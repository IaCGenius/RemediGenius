---
type: Playbook
title: EC2 instance hardening (EC2.8 IMDSv2, EC2.9 public IP, EC2.7 EBS default encryption, SSM.1 managed)
description: IMDSv2, public IPs, default EBS encryption and SSM management for EC2 instances.
tags:
- ec2
- imds
- hardening
sources:
- id: controls
  resource: https://docs.aws.amazon.com/securityhub/latest/userguide/ec2-controls.html
  title: Security Hub EC2 controls
  author: aws-documentation
- id: imds
  resource: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
  title: Use IMDSv2
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# EC2 instance hardening (EC2.8 IMDSv2, EC2.9 public IP, EC2.7 EBS default encryption, SSM.1 managed)

**Means:** IMDSv1 enables SSRF-to-credential theft; public IPs expose instances directly; unencrypted
EBS volumes; instances not managed by SSM cannot be patched centrally.

**Verify:** `rgtriage aws ec2 describe_instances --params '{"InstanceIds":["i-..."]}'` (MetadataOptions.HttpTokens,
PublicIpAddress) and `rgtriage aws ec2 get_ebs_encryption_by_default`.

**Terraform:**
```hcl
# inside aws_instance or aws_launch_template
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"
  http_put_response_hop_limit = 2 # 2 if containers on the host need IMDS, else 1
}

# EC2.7, once per region
resource "aws_ebs_encryption_by_default" "this" {
  enabled = true
}
```
Public IP: `associate_public_ip_address = false` on `aws_instance`; for launch templates set it inside
`network_interfaces { associate_public_ip_address = false }`.

**CloudFormation:** `LaunchTemplateData.MetadataOptions: {HttpTokens: required, HttpEndpoint: enabled}`.

**CLI:** `aws ec2 modify-instance-metadata-options --instance-id i-... --http-tokens required --http-endpoint enabled`

**Trade-offs:** old SDKs/agents that only speak IMDSv1 break; check the `MetadataNoToken` CloudWatch metric is 0
first. Launch template changes affect new instances only; roll the ASG. Removing a public IP needs a NAT/SSM path.

**Related:** [securityhub findings](/remedigenius/sources/securityhub.md) · [inspector findings](/remedigenius/sources/inspector.md) · [where to look](/remedigenius/guides/where-to-look.md) · [how the desk works](/remedigenius/guides/how-the-desk-works.md)
