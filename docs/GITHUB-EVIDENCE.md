# GitHub integration: verification evidence (v0.4.0)

Final state: **READY_FOR_HUMAN_SETUP**. Everything that can be proven without GitHub consent and without a protection-capable
repository is proven below. The remaining checks need two things only a person can provide (see "Pending").

How to read the columns: **Mock** = automated tests against an in-memory fake of the GitHub API that records every request, so the
tests can show what was *not* sent (`tests/test_github.py`). **Spot** = checked on a real, freshly replaced Spot instance running this
build (`tools/spot_release_test.py`, 23 checks). **Real GitHub** = an actual repository. **Human** = needs a person's session.
Nothing marked pending was run.

## Environment

- Implementation branch `feat/github-integration`, release v0.4.0, on top of v0.3.3 (`main` at `9d9d8ef`).
- Hermes: the pinned `nousresearch/hermes-agent:stable@sha256:444b4259…` (0.21.7). No Hermes GitHub feature is used at runtime (see below).
- Local suite: 345 passed, 2 skipped (186 existing tests plus 159 new). Spot: all 23 release checks passed on an instance that was
  replaced from the same data bucket (the first replacement failed to boot and led to defect 2 below; state survived the later ones).

## Reuse decision

| Hermes provides | Used? | Why |
|---|---|---|
| `github` skill (`gh` CLI, PAT or SSH, includes merge and auto-merge) | Only its read-only text (PR template ideas) | Needs a terminal toolset and a token; RemediGenius has neither, and its workflows merge. |
| `mcp_servers` with the GitHub MCP server and `tools.include` allowlist | No | Token and server sit inside the agent container and Hermes cannot restrict repository, branch or PR base, so it cannot be the enforcement layer. |
| Community plugins (`githermes`, `my-github`) | No | Desktop panes that run the user's own `gh` login. |
| Hermes approval prompt (`pre_tool_call` hook) | **Yes** | Each `github publish` needs the user's approval, like `decide`. |
| Hermes Kanban, knowledge, skills, plugin and socket pattern of the desk | **Yes** | Unchanged; GitHub is one more desk subcommand behind the existing plugin tool. |

Custom code added because nothing upstream enforces the policy: `rgtriage/github.py` (gate, App auth, operations), `rgtriage/validators.py`
(deterministic checks), one plugin action, a socket allowlist, and Spot packaging. It is not an agent runtime.

## Evidence matrix

| Area | Mock (automated) | Spot (real host) | Real GitHub | Human |
|---|---|---|---|---|
| Fresh setup, correct actor and repository | PASS: manifest connect flow (forged redirect refused, state checked, key written 0600), `configure`, identity `<app>[bot]` in `status` | PASS: boots `Disconnected`, tools installed, key folder 700 | **PENDING** | Create and install the App |
| Allowed workflow: validate, push to feature branch, one PR into dev | PASS: opens one PR, base = dev, reviewers requested, sanitized body, fix record linked | PASS: real terraform, tflint, cfn-lint on the host (good change passes, bad reference and bad property are caught, formatting only warns) | **PENDING** (needs protections) | |
| Protected refs: update, force-push, delete, `HEAD:main`, API ref mutations, PR to main | PASS: 36 parametrized refusals plus 10 forbidden requests in many disguised spellings (encoded, double-encoded, dot segments, case, backslash); refused before anything is sent; every allowed write is inside the policy | n/a | **PENDING** (GitHub-side rejection needs rulesets) | |
| Repository boundaries: other remotes, other repositories, invalid destinations | PASS: other owner or repo, forks, `/user`, `/orgs`, `/graphql` refused; no git remotes exist because writes use the REST API | n/a | PENDING | |
| PR approval | PASS: no approve operation exists; `POST .../reviews` refused by the gate and absent from the agent tool; bot approvals are not counted as human reviews | PASS: agent socket refuses operator operations | **PENDING** | |
| Merge, auto-merge, merge queue, before and after approval | PASS: `PUT .../merge`, auto-merge and GraphQL refused; the whole workflow sends no merge or review request | n/a | **PENDING** | A person merges |
| Human path: review and merge in their own session, renewed review after new commits | n/a | n/a | **PENDING** | Required |
| Alternate access: raw API, extra tools, credential helpers, env, shell | PASS: agent tool offers only `status`, `publish`, `pr_status`, `refresh`; `repo`, `base`, `connect`, `configure` are not model inputs; toolsets still have no terminal | PASS: operator operations refused over the socket (4 of 4); key folder not mounted into any container; agent container cannot see it | n/a | |
| Credential handling | PASS: tokens never written; errors and logs redacted; key and policy files hold no secrets; validators run with `AWS_*`, `GITHUB_*` and token variables removed; PR text cleaned of account ids, tokens and @mentions | PASS: `/data/rggithub` is 0700, owned by the desk user, not mounted | PENDING: scan a real run's transcripts and logs | |
| Failure behavior: revoked credentials, removed access, missing protection, enforcement unavailable | PASS: each gives `Blocked` with a remedy and no write; a failed protection read denies the publish | n/a | PENDING | |
| Recovery: expiry, restart, timeout, retry | PASS: retries with backoff, no duplicate PR or commit, same branch reused, non-fast-forward is never forced, someone else's branch is never overwritten, restart keeps the policy | PASS: state carried over the instance replacements (fix record, owner, PR link, Kanban card, knowledge, plugins, skills) | PENDING: connection carried over | |
| Regression: AWS read-only, proposal validation, remediation tracking | PASS: 186 existing tests unchanged | PASS: first scan, Kanban card, dashboard Knowledge tab, 11 WebUI menus | n/a | |

## Which layer rejects what

| Request | Rejected by |
|---|---|
| Wrong repository, wrong ref, wrong PR base, force update, delete, review, merge, protection change | The adapter, before sending (tested above) |
| Direct push to `dev` or `main`, merge without review or failing checks | GitHub rulesets (templates in `deploy/github`), **not yet exercised against GitHub** |
| Approval by the PR author | GitHub (the author is the bot, so any human can approve) |

GitHub App permissions cannot separate "open a PR" from "approve or merge a PR", so the adapter's refusal is the primary control and
GitHub's rules are the independent second layer.

## Defects found by testing, and fixed in this release

1. The Kanban dispatcher was **not** off in the default profile on a v0.3.3 Spot (the setting did not survive start-up). The boot now sets
   it after the last restart, reads it back and fails the boot if it does not stick.
2. `cfn-lint` conflicted with the pinned PyYAML on the host (found only by booting a real Spot). Pins corrected, and a test now asks pip.
3. `cfn-lint` was installed but not found by the desk service (not on `PATH`). Tools are now looked up next to the interpreter.
4. Branch names with unusual characters inside the feature prefix were accepted. Destination refs now use a strict character set.
5. The gate decoded a path once and sent the original; double-encoded paths are now refused as non-canonical.
6. The first connect run on an existing connection would have silently created a second App. It now refuses, or resumes at the install step.

## Pending: exact next steps

1. **GitHub consent (human):** `python tools/github_connect_spot.py --stack <stack>`, open the printed `http://localhost:8743/` address,
   click **Create GitHub App**, then **Install** on only the test repository.
2. **A protection-capable repository (human decision):** the test organization is on GitHub's Free plan, where a *private* repository cannot
   have rulesets or branch protection at all. That is the "protection unavailable" case and the desk correctly stays read/proposal-only
   there, but the allowed-workflow and GitHub-side-rejection checks need either a public disposable repository or a paid plan. Then apply
   `deploy/github` as an administrator, and run `sudo rgdesk github configure ...` and `verify`.
3. **Human review and merge:** a designated person reviews and merges the test PR in their own session, then pushes a change and confirms the
   renewed review is required.
4. Re-run the matrix rows marked PENDING and update this page. A check that cannot run stays PENDING, never PASS.
