# Proposed MCP release: maintainer review

This is a scope proposal, not a release announcement. Confirm the feature set before assigning a version,
publishing artifacts or submitting a Hermes catalog entry.

| Feature | What the user gains | Added component | Evidence / release condition |
| --- | --- | --- | --- |
| Vendor-backed guidance | Explain AWS findings, choose valid Terraform arguments, understand Prowler | Existing AWS Knowledge, HashiCorp Registry and DeepWiki connections; routing skill | Exercised in live chat; packaged Spot recovery passed; existing-Hermes clean install not certified |
| Organization knowledge | Bring a document, retain its source, review AI drafts, reuse approved guidance | Source onboarding and improved OKF import/review workflow | File/PDF workflow exercised; authenticated vendor sources need their own end-to-end validation |
| Secure AWS investigation | Read the user's account using existing audit roles | Default managed AWS MCP transport behind the desk guard | Real read and denial checks passed again after packaged instance replacement |
| Historical analytics | Ask about observation counts, coverage and verification history | One deferred report tool, skill and isolated Athena MCP worker | Four reports, routing, standard provisioning and replacement passed; see validation limits |
| Focused context | Load the tool/skill needed for the task | Hermes native deferred discovery plus CE task routing | Live analytics used about 13.6k total context; this is not a measured MCP-only overhead delta |

The current queue, deterministic priorities, proposal validation, human approval and committed-batch history
remain the foundation. An MCP connection does not grant AWS write authority. Analytics does not certify closure.

## Recommended scope

Include all five groups, with AWS transport and analytics enabled by default on the standard EC2 deployment. Present vendor document sources
as supported onboarding routes only where they have been validated; do not advertise every catalog entry as
a working integration. The remaining validation limits are explicit in [release validation](RELEASE-VALIDATION.md).

Do not include a Hermes marketplace listing in the feature claim until its package and catalog submission have
been accepted. Do not ship lab accounts, imported customer PDFs, chat databases or self-edited skills wholesale.

## Work sequence after feature confirmation

1. Compare allowlisted Spot code/skills with source. Review each learned skill change; retain generic guidance,
   discard environment-specific facts and unsupported conclusions. Record hashes and merge decisions privately.
2. Complete standard setup/recovery and the failure cases that the feature matrix identifies.
3. Exercise representative tasks from a clean installation and packaged Spot deployment, including an existing
   Hermes profile installation. Preserve the distinction between lab evidence and fresh-install evidence.
4. Separate private execution evidence from product source; keep reusable tests and sanitized validation public.
   Scan the tracked tree and each release archive for secrets, identifiers and unintended files.
5. Finalize version/changelog and review the exact release artifacts. Publish through the maintainer's workflow.

## Existing Hermes users and future distribution

Today the repository has `tools/install_local_hermes.py`, documented in [LOCAL-HERMES.md](LOCAL-HERMES.md).
It creates a dedicated profile and reuses an existing model configuration. It also installs the desk package,
skills and Knowledge UI wiring; the full product is more than a standalone Python plugin directory.
Local installation runs with the user's credentials and lacks the EC2 container/host isolation boundary.

The repository is not currently a verified one-command catalog package. The installer has not received the
new MCP feature set's clean-install validation. A root-repository `hermes plugins install` command must not be
advertised as installing the complete CE desk without that work.

Recommended distribution ladder:

1. Release a tested, version-pinned repository/profile installation with a short quickstart and doctor check.
2. Package a discoverable Hermes extension with explicit desk dependency/setup, bundled routing skills,
   capability declarations, uninstall/update behavior and clear optional AWS permissions.
3. Submit a Community catalog entry pinned to the reviewed commit. Use real screenshots and a short demo;
   do not claim Official or Verified status. Keep a single source for skills and product code.

Current official references (checked 2026-11-02):
- [Hermes plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)
- [Hermes plugin catalog](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugin-catalog)

The catalog supports repository subdirectories and reviewed commit pins, so a separate public plugin repository
is not automatically necessary. Its latest documentation may describe APIs newer than CE's pinned Hermes;
validate against the supported version before choosing the package format.
