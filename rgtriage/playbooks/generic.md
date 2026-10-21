# Generic remediation approach

1. Read the finding's remediation text and URL (the AWS documentation for that control or finding type).
2. Verify current state with a read-only call (`rgtriage aws <service> <describe/get/list op>`); findings can be stale.
3. Locate the code (`rgtriage fix <ref> --iac <path>`). If no IaC defines the resource, say so: the fix is a
   console/CLI change now plus importing the resource into IaC to prevent drift.
4. Propose the smallest change in the user's existing style (same module, naming, provider version) as a
   unified diff. Explain blast radius and rollback. Never apply it.
5. After the operator applies: `rgtriage scan`, then `rgtriage decide <ref> fixing|resolved --reason "..."`.
