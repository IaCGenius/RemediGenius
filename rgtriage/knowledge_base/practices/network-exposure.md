---
type: Security Practice
title: Network exposure
description: Expose only what must be public; keep administration ports, instance metadata and private services off the internet.
tags: [network, security-group, ec2, imds, exposure, cis, fsbp]
sources:
  - {id: ec2-controls, resource: "https://docs.aws.amazon.com/securityhub/latest/userguide/ec2-controls.html", title: Security Hub controls for EC2, author: aws-documentation}
  - {id: imds, resource: "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html", title: Configure the instance metadata service, author: aws-documentation}
generated: {by: remedigenius-ce/0.3.0, at: "2026-10-22T00:00:00Z"}
remedigenius:
  controls: [EC2.2, EC2.8, EC2.9, EC2.13, EC2.14, EC2.15, EC2.18, EC2.19, EC2.21, EC2.53, EC2.54, Lambda.1,
             SQS.3, SNS.4, EKS.1, OpenSearch.2, Redshift.1, SSM.1]
---

# Goal

No security group or network ACL allows the internet to reach SSH, RDP or database ports; the default security group
allows nothing; instances require IMDSv2 and have no public IP unless they serve the internet; managed endpoints
(EKS API, OpenSearch, Redshift, Lambda URLs) are private or authenticated.[^ec2-controls]

# Why it matters

Internet-wide scanners find an open port within minutes. IMDSv1 lets a server-side request forgery bug read the
instance role's credentials.[^imds] Exposure multiplies every other weakness: a vulnerable package on a private
instance can wait, the same package on a public one cannot.

# What checks it

| Control | Checks | Desk default |
|---|---|---|
| EC2.53 / EC2.54 / EC2.21 / EC2.13 / EC2.14 | no 0.0.0.0/0 or ::/0 to admin ports in security groups or NACLs | P1 when attached to running instances |
| EC2.19 / EC2.18 | no unrestricted high-risk ports; only authorized ports open | P1–P2 |
| EC2.2 | default security group restricts all traffic | P3 |
| EC2.8 / EC2.9 | IMDSv2 required; no public IPv4 address | P2 |
| Lambda.1 / SQS.3 / SNS.4 | no public invoke or `Principal: "*"` policies | P2 |
| EKS.1 / OpenSearch.2 / Redshift.1 | managed endpoints not public | P2 |
| SSM.1 | instances managed by Systems Manager (needed for patching) | P3 |

Inspector network-reachability findings and Access Analyzer show what is actually reachable; a finding that is both
exposed and vulnerable gets the toxic-combination bonus (+10).

# Investigate and fix

- [Security group ingress](/remedigenius/playbooks/security-group-ingress.md), [EC2 hardening](/remedigenius/playbooks/ec2-hardening.md)
  and [other common controls](/remedigenius/playbooks/misc-services.md) playbooks.
- Evidence: `ec2 describe_security_groups`, `ec2 describe_network_interfaces` (what the group is attached to),
  `ec2 describe_instances` (public IP, `MetadataOptions`).
- Replace SSH/RDP from the internet with Session Manager; put public services behind a load balancer and WAF.

# Build on it

- **Architecture** concepts: which services are meant to be public (and behind what), so the desk tells intended from
  accidental exposure.
- **Risk Exception** for a deliberately open port (a public SFTP endpoint), naming the exact security group.
- **Policy**: "no SSH/RDP from the internet; use Session Manager".

Related: [Inspector findings](/remedigenius/sources/inspector.md) · [Vulnerability and patching](/remedigenius/practices/vulnerability-and-patching.md) · [CIS AWS Foundations Benchmark](/remedigenius/frameworks/cis-aws-foundations.md)

[^ec2-controls]: Security Hub controls for EC2
[^imds]: Configure the instance metadata service
