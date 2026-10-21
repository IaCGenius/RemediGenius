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
