# Native Hermes CE profile

One operator-facing profile, `ce-desk`, supplies investigation, knowledge use,
fix preparation and delayed reassessment. Hermes supplies the conversation and
model runtime; the CE plugin enforces the bounded tool/evidence contract.

Use the [workstation guide](../../docs/WORKSTATION-HERMES.md) or
[AWS guide](../../docs/NATIVE-CE-QUICKSTART.md). They stage this distribution,
configure your model, install the profile and restrict tools to
`skills,clarify,ce_runtime`. Do not substitute a general terminal toolset.

Secrets are provided at runtime, not in source. Collection is separately scoped
through Lambda; selected evidence is stored in S3. AWS schedules are configured
by the deployment, independently of the profile. One writable profile/session
volume is required; do not run concurrent writers against it.

`aws-security.lock.json` pins the attributed AWS reference content. The packager
creates the integrity manifest used by the runtime. Review source changes and
use the explicit upgrade procedure; do not bypass integrity checks.
