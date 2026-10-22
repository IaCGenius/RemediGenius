# Upgrading RemediGenius Community Edition

## Within v0.3.x

- **Spot:** rebuild the archive (`python tools/package_release.py --spot …`), `terraform apply`, then replace the instance
  (or scale to 0 and back). The new instance restores state from S3, and code-owned profile files (SOUL, skills,
  plugin) are refreshed on every boot. Your `config.yaml`, `.env`, conversations, `triage.yaml` and decisions are kept.
- **Docker workstation:** `git pull`, then `python tools/workstation.py start` (it rebuilds the desk image and re-syncs the profile).
- **Existing Hermes:** `git pull`, then `python tools/install_local_hermes.py`.

## From v0.2 (`ce-desk`) to v0.3

v0.3 replaces the v0.2 design. The `ce-desk` profile, the collector, validator and knowledge tools, and the retained
EBS volume are gone. There is no in-place migration: deploy v0.3 as a new stack (or with a new workstation data folder)
and remove the v0.2 deployment when you no longer need it. Keep the v0.2 Terraform state and bucket until you have
exported anything you want from them; v0.2 remains available at tag `v0.2.0`.

Checkpoints written by v0.3 are not compatible with v0.2 backups, and v0.3 never reads v0.2 state.

**Knowledge from v0.2:** v0.2 stored reviewed knowledge with OKF-style frontmatter. Export it from the v0.2 deployment
(its library folder or the exported concept files), zip the `.md` files, and import the zip in the v0.3 **Knowledge**
tab: each concept lands in the review queue, where you approve it into the bundle. Plain documents (policies, runbooks)
can be imported directly. See [KNOWLEDGE.md](KNOWLEDGE.md).
