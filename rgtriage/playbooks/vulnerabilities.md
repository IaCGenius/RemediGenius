---
type: Playbook
title: Software vulnerabilities (Inspector package/code findings on EC2, ECR images, Lambda)
description: 'Inspector CVE findings: prioritize by exploit, EPSS and reachability; fix in the image or package, not in place.'
tags:
- inspector
- cve
- vulnerability
sources:
- id: inspector
  resource: https://docs.aws.amazon.com/inspector/latest/user/findings-understanding.html
  title: Understanding Inspector findings
  author: aws-documentation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# Software vulnerabilities (Inspector package/code findings on EC2, ECR images, Lambda)

**Prioritize by:** exploit available, EPSS, network reachability, internet-facing workload, fix available.
A CRITICAL CVE with no reachable path and no exploit can wait behind an exploited HIGH on a public instance.

**Fix in code, not in place:**
- **ECR images:** bump the package or base image in the Dockerfile (`FROM ...:<patched tag>`), rebuild, push,
  and redeploy (task definition / Helm values reference the new digest). Context shows `packages[].fixed_in`.
- **EC2 from an AMI (`aws_instance.ami` / `aws_launch_template.image_id`):** move to a patched AMI (a `data "aws_ami"`
  lookup with `most_recent = true` on trusted owners, or your golden-image pipeline) and roll the ASG.
  Long-lived instances: SSM Patch Manager `AWS-RunPatchBaseline`.
- **Lambda:** bump the dependency in requirements.txt / package.json / lockfile or the runtime, then redeploy.

**Verify:** after redeploy, `rgtriage aws inspector2 list_findings --params '{"filterCriteria":{"vulnerabilityId":[{"comparison":"EQUALS","value":"CVE-..."}]}}'`.
Inspector rescans automatically on push/patch.

**Trade-offs:** major-version bumps can break the app; run its tests. Always show `installed -> fixed_in`.

**Related:** [inspector findings](/remedigenius/sources/inspector.md) · [where to look](/remedigenius/guides/where-to-look.md) · [how the desk works](/remedigenius/guides/how-the-desk-works.md)
