# Contributing to RemediGenius Community Edition (RemediGenius-CE)

Prefer a small improvement to an existing skill, playbook, collector or scoring rule over a parallel framework.
RemediGenius-CE deliberately reuses Hermes for chat, the UI, schedules and messaging.

## Report a useful issue

Use the issue templates. Include the version or commit, the deployment path (workstation, Spot, existing Hermes),
what you expected and what happened, and a minimal redacted reproduction. Say whether the problem is an AWS
observation, the model's interpretation, or a runtime error.

Never post model or API keys, AWS credentials, account or resource identifiers, Terraform state, dashboard logins,
checkpoint archives or unredacted transcripts. Report suspected credential exposure or security issues privately; see
[SECURITY.md](SECURITY.md).

## Make a focused change

Contributions require a [Developer Certificate of Origin 1.1](https://developercertificate.org/) sign-off
(`git commit -s`). Contributions are licensed under Apache-2.0.

1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Keep deterministic work (collection, scoring, storage) in
   `rgtriage/` and judgment in the profile's skills.
2. Keep every AWS call read-only (the botocore guard must stay the single path), and never give the agent container
   AWS credentials.
3. Add or update tests and run them:

```sh
python -m pip install -e ".[test]"
python -m pytest tests
python tools/demo.py
```

4. In the pull request, state what you verified live (AWS, model) and what only offline. Synthetic fixtures are not
   proof of live behaviour.
5. Do not commit `.rgce/`, `dist/`, keys, state or checkpoints.
