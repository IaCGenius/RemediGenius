# Upgrade an existing CE installation

## Current main updates (no version bump)

See the [change log](../CHANGELOG.md) before updating. The answer-format and writing
changes are source updates after v0.1.3; the published tag/downloads do not contain
them. Use the source commit and package SHA-256 to identify your installation,
because the version string alone does not distinguish these changes.

For an existing workstation installation, stop its launcher, back up its named
volume and private inputs, and update a clean checkout with `git pull --ff-only`.
Review the change log, then run the existing configuration:

```bash
python tools/native_workstation.py run --config .rgce/workstation.json --upgrade
```

Keep that terminal open. Retrieve your login in a second terminal as described in
the workstation guide. Start a new bounded investigation in `ce-desk` and check
its [answer sections and references](ANSWER-CONTRACT.md). Existing saved answers
are not rewritten. Model settings, credentials and sessions are retained.

For Spot, follow the backed-up package/profile upgrade procedure below. A Git pull
does not update the running instance. These source updates were tested in isolated
local Hermes; they have not received a new Spot qualification. No infrastructure
change is required specifically for the answer-format or writing changes.

## v0.1.3

Back up retained state first. Keep the existing stack name, Terraform state, model
secret, evidence prefix and Docker/EBS volume. Apply the AWS infrastructure changes
with the same inputs; inspect the plan before proceeding. The larger default Spot
pool is t3.large/t3a.large with a 6144 MiB Hermes memory limit.

Boot recovery preserves installed user/profile files. Updating the mounted package
alone does **not** upgrade retained skills: use the explicit profile-upgrade helper
and restart the service during your maintenance window. Workstation `run --upgrade`
performs this step and keeps backups. For Spot, run the packaged
`tools/upgrade_native_profile.py` as the profile owner with the reviewed package
mounted at `/opt/ce-package`, `--home /opt/data/profiles/ce-desk --guard-default`.
Quiesce the service before mounting its retained home into an upgrade container;
restart afterward and verify package integrity, sessions and the selected knowledge.
Do not mount the volume into two running Hermes agents.

Retained model settings are preserved. The tested DeepSeek configuration is not a
forced migration of your provider or credentials. A successful startup probe checks
one tool call; follow it with a scoped investigation and inspect its actual receipts.

## Historical v0.1.1

v0.1.1 keeps the official Hermes image and existing model settings. It updates
the CE skills, runtime plugin and AWS read executor. Upgrade both the native
package/profile and the collector Lambda through your existing Terraform state;
updating only the chat profile leaves the old collector default in place.
Workstation users must also update their AWS workstation backend. Preserve
volumes, private inputs and secrets as described below.

An omitted interactive page budget now means one page. Explicit multi-page and
scheduled-check budgets are unchanged. Confirm the runtime receipt heading after
a fresh bounded read. See [validation outcomes](RELEASE-VALIDATION.md), including
the remaining remediation-draft limitation.

## Historical v0.1.0 layout migration

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

## Post-v0.1.0 network and reader changes

New AWS deployments default `associate_public_ip = false`. Supply a subnet with
NAT or equivalent access to required AWS APIs, model endpoints and package/image
registries. For an existing public-subnet deployment without NAT, explicitly set
`associate_public_ip = true` before applying. The private-subnet path has not yet
received end-to-end live qualification. Port 80 host egress remains for compatibility;
removing it has not been validated. Container outbound controls are unchanged.

Reader credentials and metadata now use root:10000 ownership, directory 0750 and
files 0440. The uid/gid 10000 container retains read access. Skills added to the
package are included in integrity checks and require an explicit profile upgrade.

The historical `native-hermes-sketch` Purpose tag is retained for compatibility; the source paths and user-facing product names use CE.
