# Upgrade from the native preview

v0.1.0 keeps the same Hermes image, Qwen baseline, `ce-desk` identity and runtime
resource names. The source layout changes:

| Previous | Current |
|---|---|
| `profiles/native-sketch` | `profiles/ce` |
| `deploy/aws-native-sketch` | `deploy/aws-native` |
| `tools/native_sketch_data.py` | `tools/native_data.py` |

Legacy console, builder, broker and prototype deployments are not shipped. Shared
knowledge/evidence utilities and the offline sample remain. Historical source is
preserved in Git history; do not attempt to migrate old console data by treating
it as a native Hermes profile.

## Preserve your installation

Back up your deployment inputs and Terraform state, and the retained Docker/EBS
session volume before upgrading. S3 evidence is a separate durable layer. Keep
the previous source archive, digest and model settings. Checking out new source
does not upgrade a running container or replace its source archive.

For workstation mode, stop the launcher/container, retain its named volume and
private configuration, then run the existing launcher with `--upgrade`. Use the
same name/configuration; a new name creates a different volume. The helper backs
up replaced profile files and preserves model/session settings. See
[workstation instructions](WORKSTATION-HERMES.md).

## AWS Terraform source-path migration

Use the same backend/state and input values, not a new empty state. Resource
addresses are unchanged by the directory rename. For a local backend, securely
copy the existing state into `deploy/aws-native` after backing it up; for a remote
backend, configure the same backend/key/workspace. Keep only one active working
directory for future applies. Do not import or recreate the running stack.

Set `profiles_dir` to `profiles/ce` in private inputs if it was explicitly set to
the old path. Package/upload the new immutable source with
`tools/package_native_hermes.py`, then set the exact returned digest and key.
Initialize the renamed Terraform directory and inspect its plan. Unexpected
creates, deletions or replacements require investigation before applying.

The tested migration plan changed only the launch template, its Auto Scaling
configuration and the host policy's exact source object. Applying it can replace
the Spot host. Let the old host release its retained volume; never force-detach
it. After bootstrap, explicitly upgrade the retained profile using
`tools/upgrade_native_profile.py`, then verify integrity, model selection, login
and a fresh bounded read. See [AWS setup](NATIVE-CE-QUICKSTART.md).

For rollback, restore the prior input/archive references and profile backup using
the same state and volume, review a new plan, and verify again. Do not delete
state or the retained volume to repair an upgrade.
