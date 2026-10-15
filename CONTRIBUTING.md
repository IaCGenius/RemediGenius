# Contributing to RemediGenius CE

The preview baseline is AWS `us-east-1`, Qwen 3.8 Max and one native `ce-desk`
profile. Prefer a small improvement to an existing skill or Hermes integration
over a parallel agent framework or custom UI. Other providers/regions are welcome
experiments, but are not required to qualify this MVP.

## Report a useful issue

Use the repository issue templates. Include the commit/version, deployment path,
what you expected, what actually happened and a minimal redacted reproduction.
Distinguish an AWS API observation, model interpretation and an execution error.
Do not post model/API keys, account/resource identifiers, Terraform state, cookies,
private policy content, raw receipts or unredacted transcripts. A screenshot should
show only the relevant UI after removing private values.

A denied or disabled AWS source is not automatically a software defect. Include
which operation failed and the redacted error; do not broaden IAM permissions just
to make a test pass. For a suspected credential exposure, stop public disclosure
and notify a maintainer privately through GitHub's available private reporting
channel; do not paste the credential into an issue.

## Make a focused change

Contributions require a [Developer Certificate of Origin 1.1](https://developercertificate.org/)
sign-off. Use `git commit -s` with your own identity after reading the certificate.
Maintainers check sign-offs during review; no automated DCO check is claimed.
Do not sign on behalf of someone else. Contributions remain under Apache-2.0;
the DCO does not transfer copyright or grant blanket relicensing rights.

1. Read `START-HERE.md` and the relevant skill/module before editing.
2. Keep changes scoped; explain user impact and why native Hermes functionality
   or an existing dependency was insufficient if adding code.
3. Keep deterministic collection separate from AI interpretation. Preserve
   provenance, scope, timestamps, explicit partial results and read-only boundaries.
4. Run checks appropriate to your change. Do not use a fake fixture as proof of
   live AWS/model acceptance. Mark constructed cases and untested paths explicitly.
5. Include verification and known limitations with the pull request. Do not commit
   `.rgce`, model keys, credentials, private inputs, state, or volume backups.

For the existing Python checks, in a virtual environment:

```sh
python -m pip install -e ".[aws,documents,test]"
python -m pytest tests
```

Read platform-specific skips rather than describing skipped cases as passed.
AWS and live-model tests require the operator's own permission, configuration and
budget. The public CI execution status is tracked separately in
`docs/V0.1-RELEASE-PLAN.md`; a billing-blocked job is not a test result.

For documentation, verify local links and copyable commands against the current
source. Use genuine redacted screenshots. Archive older acceptance results rather
than rewriting a failure into a pass. Model critique supports review; it does not
replace technical validation.
