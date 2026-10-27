# Upgrading RemediGenius Community Edition

## To v0.4.0 (from v0.3.x)

Spot: rebuild the archive, `terraform apply`, then replace the instance (the same steps as within v0.3.x). The new instance restores your state
from S3; nothing needs migrating. What changes:

- **The Hermes WebUI is removed.** Use the dashboard (`tools/open-remedigenius`): it has the Chat tab, Knowledge, Improve and the new GitHub tab.
  Why: Knowledge, Improve, GitHub and Kanban only ever lived in the dashboard, so a second UI showed a different, partial picture, and it was a
  third-party image to re-pin and re-test with every release. The `-WebUI` / `--webui` flags of the open-console scripts are gone.
- **The `webui` Terraform variable is gone.** If your tfvars file sets `webui = ...`, delete that line (Terraform only warns about an unknown
  variable in a tfvars file, but an explicit `-var webui=...` is an error).
- **The agent's API server is no longer exposed.** It was opened to the private container network (port 8642, with a shared key) only for the WebUI.
  Hermes still starts its own API server, but on loopback inside the agent container: nothing is published for it and nothing outside can reach it. The boot
  removes the old shared key (`/data/hermes/.remedigenius-api-key` and `API_SERVER_KEY` lines in the `.env` files), the old WebUI service, container
  and volume if present, and the generated wiki view (`/data/hermes/rg-wiki`, **Insights, LLM Wiki**), which only the WebUI showed. The desk no longer
  writes it (`RGTRIAGE_WIKI_DIR` has no effect).
- **Your WebUI data is left alone.** Its own folder, `/data/hermes/webui`, stays; delete it in an SSM session when you are sure you no longer need it.
  Conversations are stored by Hermes and stay available in the dashboard.
- **New: GitHub.** The dashboard has a GitHub tab (Spot only) to connect one repository so fixes can become pull requests into your
  development branch; see [GITHUB.md](GITHUB.md). It adds a separate validation service, the `rgdesk` command, `tflint` and `cfn-lint`, and PyYAML 6.0.3.
- **Fixed:** the Kanban dispatcher is now verified off at boot. On a v0.3.3 Spot it could be on in the default profile.
- **Docker workstation and existing Hermes:** nothing changes there except that the GitHub tab is not available (the key cannot be kept away from the agent).

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
