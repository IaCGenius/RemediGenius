# Upgrade or migrate RemediGenius CE

Record your source commit and package SHA-256 before changing a deployment.
Back up Terraform state, private inputs, the retained volume and the latest S3
checkpoint. Check that a recovery copy is readable before removing old resources.

## Move from a Lambda-based deployment

The single-compute deployment uses a **different Terraform stack and state**.
Do not point `deploy/aws-single` or `deploy/workstation-storage` at the state of
`aws-native`, `aws-workstation` or an older prototype. This is a migration, not a
source-directory rename.

1. Keep the old stack's exact source, state and inputs in a private backup folder.
2. Preserve S3 evidence and runtime data. Old releases may not have the new S3
   checkpoint mechanism; retain their EBS snapshot or Docker volume too.
3. Install the new stack with a distinct name and empty Terraform state, following
   [AWS setup](../deploy/aws-single/README.md) or [workstation setup](LOCAL-COMPUTE-WORKSTATION.md).
4. Test a real scoped read, knowledge use, cases and tool validation. Do not assume
   old receipts or configuration prove the new runtime works.
5. Import selected knowledge deliberately. Full legacy runtime-state conversion
   is not an automatic migration feature. Keep old conversations recoverable.
6. Remove the old stack using its old source and state after checking its backups.
   Disable its separate schedules too. Never delete unrelated account resources.

The earlier source remains in its immutable Git tags. The current stack creates
no Lambda collectors or EventBridge schedules.

## Update a single-compute workstation

Stop the launcher and back up its retained volume and private configuration.
Update a clean checkout, review the change log, then run:

```bash
python tools/native_workstation.py run --config .rgce/workstation.json --upgrade
```

Use the same workspace name and configuration to retain sessions and knowledge.
The explicit upgrade updates RemediGenius CE profile files and preserves model/session settings.
A new workspace name creates different local storage. Do not run two agents
against the same retained home or S3 checkpoint prefix.

## Update a single-compute Spot installation

A Git pull alone does not update a running instance. Package the reviewed source,
update the stack's source ZIP input, inspect the Terraform plan and apply it.
The new launch-template version is used for subsequent instance launches; do not
assume the existing host has changed.

During a maintenance window, checkpoint and stop compute through `running=false`,
then apply `running=true`. The retained volume takes precedence over S3 restore.
Boot preserves existing user/profile files; changing the source package alone is
not permission to overwrite a customized profile. An explicit profile upgrade
must be performed against a backed-up retained home using the packaged
`tools/upgrade_native_profile.py`, with `--guard-default`. Review customizations
before doing this; do not mount one home into two running Hermes agents.

After any update, inspect package integrity, model access, sessions, knowledge,
a fresh read and the latest checkpoint. Keep the prior source and backup until
these checks pass. Existing answers are not rewritten.
