# GitHub integration: verification evidence (v0.4.0, after the PR #19 review)

**State: READY_FOR_HUMAN_SETUP.** All ten review findings are fixed and verified locally and on a real Spot. The live GitHub checks need
things only a person can supply (GitHub consent, a protection-capable test repository, a human reviewer) and are marked **PENDING**:
nothing marked pending was run, and nothing here claims the integration is fully ready until they pass.

Evidence layers, kept apart: **Mock** = automated tests against an in-memory fake of the GitHub API that records every request, so they can
prove what was *not* sent (`tests/test_github.py`, `tests/test_validation_isolation.py`). **Local** = other automated tests on a workstation.
**Spot** = checks on a real, freshly built Spot instance running this build (`tools/spot_release_test.py`). **Real GitHub** = an actual
repository. **Human** = needs a person's own GitHub session.

## Review findings: disposition

| # | Finding | Disposition | Code | Evidence |
|---|---|---|---|---|
| 1 | P1: host validation could copy the App key | **Fixed** | `validate` takes proposals only from the proposals folder, modules only from approved IaC folders, destinations only inside the scratch copy (`validators.safe_join`, no absolute paths, traversal or links); Terraform, tflint and cfn-lint run in a separate validation service (`validators.serve`, `host.py`) under its own OS user for both `validate` and `publish`; `fix` is never pointed at the key folder | Reproduced first (key copied to the desk folder), then refused: Mock/Local `tests/test_validation_isolation.py` (34 cases, 31 run on a Windows workstation and 3 need symlinks or Unix sockets; incl. the exact exploit, 11 destination variants, symlinks, hostile archives, fail-closed). **Spot:** see "Spot results" |
| 2 | P1: verification token lacked Administration read | **Fixed** | `VERIFY_PERMISSIONS`, `token_kind()`: only protection and ruleset reads use a token with Administration: **read**; no token has Administration write; a 403 is reported as "Permissions, not protection" | Mock: a permission-aware fake rejects the old token and passes the corrected one; missing protection is distinct from missing permission. **Real GitHub: PENDING** |
| 3 | P2: existing PR base not rechecked | **Fixed** | `_task_branch`, `_require_workflow_pr`: the existing PR (repository, head, base, state) is resolved and checked before any mutation | Mock: retargeting to `main` stops the next publish with zero writes (refs, commits and requests unchanged); fork head, two open PRs refused; a matching PR is still updated |
| 4 | P2: validated tree differed from committed tree | **Fixed** | `publish` resolves the parent (branch head, or the development branch) first, validates parent + proposal, commits on that parent; the result names the parent that was validated | Mock: two successive publishes validated together; a conflicting combination is rejected though each file passes against the development branch |
| 5 | P2: partial failure left no PR | **Fixed** | An unchanged tree only skips the commit and ref update; the PR, reviewer request and fix record are reconciled; partial success is reported as `published: false, partial: true` | Mock: failure injected after branch creation, identical retry yields one PR, no second commit, correct fix-record link |
| 6 | P2: unstable branch/PR identity | **Fixed** | Branch is `feature/remedigenius/fix-<finding ref>`; title and topic are presentation only; closed-unmerged PR replaced, merged PR starts `-r2`, `-r3`... from the development branch | Mock: title and topic changes never create another PR; closed and merged cases |
| 7 | P2: team reviewers rejected after PR creation | **Fixed** | `split_reviewers`: separate user and team-slug allowlists; the team's org must equal the repository owner; a reviewer-request failure never hides the PR or loses its link | Mock: user and team through the whole flow; unauthorized and wrong-org requests refused; failure keeps the PR, and the retry asks only for the missing reviewers |
| 8 | P2: refresh overwrote human knowledge | **Fixed** | `merge_repository_page`: only the generated block and the `remedigenius` facts change; owner, notes, other fields and review history are kept; a page without markers keeps all its text; a changed repository, base or IaC kind sets `stale_after` for re-confirmation | Mock/Local: owner, notes and review survive a refresh; stale marking only for material changes |
| 9 | P2: callback failure waited out the timeout | **Fixed** | Callback handler catches network, parsing and persistence failures, ends the command within seconds with a sanitized reason, removes partial files | Mock/Local: network error, bad answers, disk failure; all under 8 s, no secrets in messages, setup recoverable |
| 10 | P3: revoked-credential recovery did not work | **Fixed** | `connect` first asks GitHub what became of the App (`probe_connection`): healthy, uninstalled (resume with the same App), reinstalled (adopt), deleted or key rejected (replacement App), unreachable (changes nothing); status, docs and behavior now name the same command | Mock: the displayed recovery leads to a working reconnection in each case |

## Easy setup (acceptance criteria)

One starting command: `python tools/github_connect_spot.py --stack <name>` runs `sudo rgdesk github setup`: prerequisites with remedies,
connect or resume, repository (only those selected at install), development branch (production and default branches refused; if none exists
the administrator command is printed), human reviewers (bots refused), protection report and the next step; safe to re-run; `status`,
`verify`, `refresh`, `disconnect` and `connect` (self-healing) cover the rest. Mock/Local: 12 tests (`tests/test_github.py`: "the guided setup command").
Finishing setup prints that it is **not** proof of a working flow.

## The GitHub tab in the web console (added after the review)

You asked to connect GitHub from the console, not a terminal. The **GitHub** tab does the whole flow: Connect GitHub (two clicks on github.com, then back
to the page), install wait, repository, development branch and reviewer choice, protection report, Check, Refresh, Change, Reconnect, Disconnect.

- **How it stays safe:** the key never reaches the browser, the dashboard process or the agent. The page asks its backend, which asks the desk over the
  socket. The setup operations are accepted only with an operator token regenerated at every boot that only the dashboard backend reads; the agent's tool
  cannot name those operations, its file tool is blocked from the token, and it now sends people to the tab. GitHub's one-time code can only come back to a
  loopback address (or an origin the operator lists); the pending state is stored hashed, single-use, one hour.
- **Mock/Local** (`tests/test_github_console.py`, 70+ tests): begin (manifest, hashed state, return-address checks, healthy / deleted / uninstalled cases),
  finish (wrong, replayed and expired state, malformed code, GitHub failures, network failure), install polling, repositories and branches limited to the
  selected ones, the operator-token gate (exact comparison, fail-closed, only the console operations and flags), the backend through FastAPI's test client
  (every field validated before the desk is asked, JSON bodies only, clean one-line errors with secrets redacted, the token sent to the socket), the plugin
  files and the page (talks only to its backend, no token or key handling), and the boot wiring.
- **Spot (deployed), 37 of 37 host checks** on a fresh instance, including: the setup token files are 0600 and identical; the tab's API refuses requests
  without the dashboard login (401) and answers after login; **Connect GitHub** returns the github.com address and tells GitHub to return to this console;
  a forged callback is refused and the page is shown with the reason; invalid input gets a 400; setup operations over the real socket work **only** with the
  token (`0 2 2`); the agent's file tool is blocked from the token. A bug found only here (the status command printed a text line after its JSON, so the tab
  could not read it) was fixed, and tests now run the actual commands the console calls.
- **Not shown:** the page rendering in a browser and the GitHub consent round trip. They need a person (and the workstation ran out of memory for an
  automated browser run). Unverified until that happens: GitHub accepting a loopback return address in the App definition (its documentation only says "a
  full URL"). If it refuses, the page shows GitHub's message and the command-line setup remains available.

## Original evidence matrix

| Area | Mock / Local | Spot | Real GitHub | Human |
|---|---|---|---|---|
| Fresh setup, correct actor and repository | PASS: manifest flow, setup, status identity | see Spot results | **PENDING** | Create and install the App |
| Allowed workflow | PASS: one PR, base dev, reviewers, sanitized body, fix link, idempotent retries | real terraform, tflint, cfn-lint run through the service | **PENDING** (needs protections) | |
| Protected refs: update, force-push, delete, `HEAD:main`, API ref mutations, PR to main | PASS: gate refuses all before sending (36 + 10 disguised forms) | n/a | **PENDING**: run `sudo rgdesk github probe --confirm-disposable OWNER/REPO` | |
| Repository boundaries | PASS: other repos, forks, `/user`, `/orgs`, GraphQL; no git remotes exist (REST only) | n/a | PENDING | |
| PR approval | PASS: no approve operation exists; refused by the gate and absent from the agent tool; bot reviews are not counted | operator operations refused over the socket | **PENDING** | |
| Merge, auto-merge, merge queue | PASS: refused by the gate, never sent by the workflow | n/a | **PENDING** (probe merges only a blocked PR) | A person merges |
| Human path, renewed review after new commits | n/a | n/a | **PENDING** | Required |
| Alternate access | PASS: agent tool ops fixed; `repo` and `base` are not model inputs; no terminal toolset; `setup`, `probe`, `connect`, `configure` operator-only | key folder 0700, not mounted, agent cannot see it | n/a | |
| Credential handling | PASS: tokens never stored, errors redacted, files hold no secrets, PR text cleaned, validators run with credentials stripped **and now in another OS user** | see Spot results | PENDING: scan a real run's logs and transcripts | |
| Failure behavior | PASS: revoked, removed, missing or unreadable protection, enforcement unavailable, validation service down: all safe | n/a | PENDING | |
| Recovery | PASS: expiry, restart, timeout, retry, partial failure, replacement App | state carried over instance replacements | PENDING: connection carried over | |
| Regression | PASS: 186 existing tests unchanged | release checks, Kanban, dashboard | n/a | |

## Spot results

A fresh Spot stack was built from this branch's v0.4.0 archive (`tools/package_release.py --release 0.4.0`, checksums verified). Deployed, not mocked.

- **27 of 27 host-side checks passed** (the host half of `tools/spot_release_test.py`, run over SSM): boot, services, version, plugins, skills,
  first scan, Kanban dispatcher off, GitHub starts Disconnected, tools installed (terraform, tflint, cfn-lint), key folder 0700 and not
  mounted into any container, the agent container cannot see it, operator-only operations refused over the agent socket, and the new isolation
  checks below.
- **Finding 1 on a real host.** The validation service runs as its own user (uid 10002). As that user: reading the synthetic GitHub key is
  `Permission denied`; appending to the policy file is `Permission denied` (content unchanged); even listing the key folder is
  `Permission denied`; the instance metadata service is unreachable (`http 000`); the firewall has the 5 blocking rules. The exploit and its
  variants through `validate` (key as source, key folder as module, absolute destination) are all refused and no file appears in the
  agent-readable desk folder. A normal proposal still validates through the service with real Terraform.
- **A hostile module.** A proposal whose Terraform module `source` points at the key folder (so that `terraform init` itself would try to copy the
  key) fails with `Unreadable module directory`, because `init` ran as the validation user; the synthetic key text appears nowhere under the
  desk, Hermes, IaC or validator folders. (Added as a permanent check in `tools/spot_release_test.py`.)

Not shown by this run, stated plainly:
- The **browser checks** (dashboard Knowledge tab) were **not run on this build**: the workstation ran out of memory during the run and
  the tool was stopped. They passed on the previous build of this branch.
- Three small fixes were made **after** this Spot run and are covered by unit tests only, not yet re-verified on a Spot: `setup` flushes its output as
  it prints (it printed nothing when stopped while piped), the Disconnected status now points to the guided setup, and the hostile-module Spot
  check above (the hostile-module result itself came from a one-off run of the same commands).
- `rgdesk github setup` was not exercised past the prerequisites on the host (the next step needs the browser consent).

## Pending: exact next steps

1. **GitHub consent (human):** `python tools/github_connect_spot.py --stack <stack>`, open the printed address, **Create GitHub App**, **Install** on
   only the test repository, then answer the prompts.
2. **A protection-capable repository (human decision):** the test organization is on GitHub's Free plan, where a private repository cannot have
   rulesets or branch protection. The desk correctly stays in read/proposal mode there, but the allowed workflow, protection verification and
   GitHub-side rejection need a public disposable repository or a paid plan. Then, as administrator, apply `deploy/github`.
3. **Run the live sequence** (each step recorded by the command shown): `status` and `verify` (protection verification with the corrected token);
   an agent publish (initial PR into the development branch); a second publish (updates the same PR); an identical publish (no change); a publish
   for another repository or base (refused before sending: Mock-proven, repeat live); `probe` (GitHub rejects direct updates, force-push, delete
   and a blocked merge); revoke (uninstall the App on GitHub) then `connect` (recovery); **a person** approves and merges in their own session,
   then pushes a change and confirms the renewed review is required.
4. Re-run the PENDING rows and update this page. A check that cannot run stays PENDING, never PASS.

Not exercised live, and why: a retry after a *real* partial failure (it cannot be produced without changing product code; the Mock test injects
it and a live identical republish shows the no-op path), and a bot approval of someone else's PR (GitHub's App permissions would allow the call;
only the code-owner requirement stops it counting, and the adapter has no such operation, so it is not attempted).
