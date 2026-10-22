---
type: Playbook
title: Other common controls (KMS.4 rotation, Lambda.1 public invoke, SNS/SQS public policies, ECR.1 scan on push, EKS.1 public
  endpoint)
description: KMS key rotation, public Lambda invoke, public SNS/SQS policies, ECR scan on push, public EKS endpoints.
tags:
- kms
- lambda
- sqs
- sns
- ecr
- eks
sources:
- id: controls
  resource: https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-controls-reference.html
  title: Security Hub controls reference
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# Other common controls (KMS.4 rotation, Lambda.1 public invoke, SNS/SQS public policies, ECR.1 scan on push, EKS.1 public endpoint)

**Terraform:**
- KMS.4: `enable_key_rotation = true` on `aws_kms_key` (symmetric customer keys only).
- Lambda.1: remove `aws_lambda_permission` with `principal = "*"`, or add `source_arn` / `source_account`.
- SQS.3 / SNS.4: replace `"Principal": "*"` with specific principals or add `aws:SourceArn` / `aws:SourceAccount` conditions.
- ECR.1: `image_scanning_configuration { scan_on_push = true }` on `aws_ecr_repository` (or Inspector enhanced scanning).
- EKS.1: in `aws_eks_cluster.vpc_config` set `endpoint_public_access = false` and `endpoint_private_access = true`, or restrict `public_access_cidrs`.

**CloudFormation:** `EnableKeyRotation: true`; `AWS::Lambda::Permission` with `SourceArn`;
`ImageScanningConfiguration: {ScanOnPush: true}`; `ResourcesVpcConfig.EndpointPublicAccess: false`.

**Related:** [securityhub findings](/remedigenius/sources/securityhub.md) · [where to look](/remedigenius/guides/where-to-look.md) · [how the desk works](/remedigenius/guides/how-the-desk-works.md)
