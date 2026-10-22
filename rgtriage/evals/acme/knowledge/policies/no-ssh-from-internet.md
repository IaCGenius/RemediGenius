---
type: Policy
title: No SSH or RDP from the internet
description: Administration goes through AWS Systems Manager Session Manager, never open ports.
generated: {by: "human:eval", at: "2026-10-01T00:00:00Z"}
verified: [{by: "human:eval", at: "2026-10-01T00:00:00Z"}]
---

Security groups never allow 22 or 3389 from 0.0.0.0/0 or ::/0. Fixes remove the rule and use Session Manager instead.

Applies to [network exposure](/remedigenius/practices/network-exposure.md) and the [security group playbook](/remedigenius/playbooks/security-group-ingress.md).
