---
type: Playbook
title: Generic remediation approach
description: 'Default approach when no specific playbook matches: verify, locate the code, propose a minimal change.'
tags:
- remediation
generated:
  by: remedigenius-ce/0.3.0
  at: '2026-10-21T00:00:00Z'
---

# Generic remediation approach

1. Read the finding's remediation text and URL (the AWS documentation for that control or finding type).
2. Verify current state with a read-only call (`rgtriage aws <service> <describe/get/list op>`); findings can be stale.
3. Locate the code (`rgtriage fix <ref> --iac <path>`). If no IaC defines the resource, say so: the fix is a
   console/CLI change now plus importing the resource into IaC to prevent drift.
4. Propose the smallest change in the user's existing style (same module, naming, provider version) as a
   unified diff. Explain blast radius and rollback. Never apply it.
5. After the operator applies: `rgtriage scan`, then `rgtriage decide <ref> fixing|resolved --reason "..."`.

**Related:** [securityhub findings](/remedigenius/sources/securityhub.md) · [where to look](/remedigenius/guides/where-to-look.md) · [how the desk works](/remedigenius/guides/how-the-desk-works.md)
