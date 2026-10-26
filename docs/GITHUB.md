# GitHub: fixes as pull requests into your development branch

RemediGenius-CE can turn a validated IaC fix into a **pull request**. It never merges, approves or touches your production
branch: a person reviews and merges. This page covers setup, daily use, how it stays safe, and recovery.

Available on the **Spot** deployment (the App key lives where the agent container cannot see it). On the Docker workstation and with
an existing Hermes the desk's state folder is readable by the agent, so GitHub shows `Blocked` and explains why; proposals and Kanban
cards still work there.

## Set it up: one command

From your computer (needs the AWS CLI with the Session Manager plugin and your AWS credentials for the stack):

```
python tools/github_connect_spot.py --stack <your stack name>
```

It opens a secure session to the instance and runs the guided `sudo rgdesk github setup` there. Setup:

1. **Checks prerequisites** and tells you what to fix: the key folder is isolated from the agent, the validation service is running,
   `openssl` is present, `api.github.com` is reachable, and which checking tools (`terraform`, `tflint`, `cfn-lint`) are installed.
2. **Connects GitHub.** It prints an address (`http://localhost:8743/`, forwarded to your computer). In your own browser click
   **Create GitHub App** on github.com, then **Install**, and choose **Only select repositories**: pick just the repository RemediGenius
   may use. These two clicks are your consent; nothing secret passes through the helper, and GitHub returns the App key straight to the
   desk. Add `--org YOUR-ORG` to create the App under an organization you own.
3. **Asks for the repository** (only the ones you selected), the **development branch** (never `main`, `master`, release or your default
   branch) and the **human reviewers** (people by login, or `org/team`; bots are refused).
4. **Shows which protections are present or missing** on the development and production branches, and the exact next step.

It is safe to run again at any point: an interrupted setup resumes where it stopped, a finished one just re-checks. Without a terminal
use flags: `sudo rgdesk github setup --repo OWNER/NAME --base dev --reviewer LOGIN --yes`.

**Setup finishing is not proof that it works.** The last lines say whether pull requests can be created; the first real PR is the real test.

If the repository has no development branch yet, setup prints the one command an administrator runs with their own login to create it.
If it has no protections, apply [`deploy/github`](../deploy/github/README.md) as a repository administrator, then `sudo rgdesk github verify`.

### The four states

| State | Meaning |
|---|---|
| **Disconnected** | No GitHub App yet. Run the setup command above. |
| **Connected: read/proposal access** | Installed, but writes are off: protection is not verified (or not readable), or no reviewer is set. The desk can still read the repository and keeps a read-only copy for `fix`. |
| **Ready to create development PRs** | Repository, development branch and human reviewer are set, and GitHub shows a required reviewed PR with no force push or deletion on both branches. |
| **Blocked** | Something specific is wrong; `sudo rgdesk github status` prints the remedy. |

`sudo rgdesk github status` shows the connected identity (`<app>[bot]`), repository, branches, reviewers, each protection check and whether
writes are enabled. `verify` re-reads the protections and updates that decision; every `publish` re-verifies too.

## Using it

Ask for a fix as before. When GitHub is ready the agent offers a PR and you approve the single `github publish` prompt. The desk then:

1. Re-checks the repository and protections (a failed or unreadable check denies the write) and resolves any **existing PR and branch for
   this finding first**: if that PR was retargeted away from the development branch, comes from another repository, or its branch holds
   someone else's commits, it stops before changing anything.
2. Validates **exactly the tree it will commit** (the branch head, or the development branch for a new task, with the proposal applied) in
   an isolated validation service: `terraform init/validate/fmt`, `tflint`, `cfn-lint`, YAML and JSON checks. A failed check pushes
   nothing. A tool that is missing is shown as **skipped (not validated)**.
3. Commits through the GitHub API (no `git push`, no repository hooks), to `feature/remedigenius/fix-<finding ref>`, and opens or updates
   **one** PR into your development branch, asks your reviewers, and links the PR to the fix record.

Every step can be repeated: a retry after a partial failure finishes the missing steps (for example creating the PR) without a second
commit, and the result says what happened. The branch and PR belong to the finding, not the title, so rewording never creates another PR.
If an earlier PR for the finding was **closed without merging**, a new PR is opened from the same branch; if it was **merged**, the next
fix starts a numbered follow-up branch (`...-r2`) from the development branch.

The desk also mirrors the development branch read-only (secrets, state files and `.tfvars` are left out) and keeps a **Repository** page in
the Knowledge tab. Run `sudo rgdesk github refresh` (or tell the agent "I updated the repo") after you change the repository. Refresh only
rewrites the generated block of that page: the owner, notes and review history a person added are kept, and if the repository, branch or
kind of IaC changed the page is marked stale so someone re-confirms it.

## What enforces what

GitHub App permissions cannot separate "open a PR" from "approve or merge a PR", so two layers cooperate:

| Rule | Enforced by |
|---|---|
| Only the configured repository | The desk (every request is checked before it is sent) |
| Writes only to `feature/remedigenius/*`; PR base is the configured development branch; never `main`, `master`, release or production | The desk (before sending) **and** GitHub rulesets on `dev` and `main` |
| No force push, no delete; canonical paths only | The desk **and** GitHub rulesets |
| Never approve, merge, enable auto-merge or change protections | The desk (those requests do not exist in its code); GitHub's App permissions would otherwise allow some of them |
| A human review is required to merge | GitHub (`pull_request` rule, CODEOWNERS). The PR is authored by the App's bot identity, so **any** human, including you, can approve it |
| Workflows, CODEOWNERS, `.git`, state files and keys cannot be changed | The desk refuses those paths in a proposal |
| Reviewers | Users by login and teams by slug within the repository's organization, as separate allowlists |
| The agent never holds a token | The App key is in `/data/rggithub` (mode 0700, desk user only, not mounted into any container); installation tokens last one hour, are narrowed to the one repository and the needed permission, and are never stored |
| Untrusted checking tools never run next to the key | A separate validation service with its own OS user cannot read or modify the key or policy, and cannot reach the instance credentials. The agent-facing `validate` command also only accepts proposals from the proposals folder, modules from approved IaC folders, and destinations inside its scratch copy |
| Instructions inside repository files, issues or PR comments | Treated as data. Repository, branch and reviewers come only from the operator's policy file |

The App is granted: Contents write, Pull requests write, Checks read, Commit statuses read, **Administration read** (only so verification
can read branch protection and rulesets: that token has no write access, and publishing uses a different, narrower token), Metadata read.
It has no Workflows permission and no webhook or event subscription.

## Recovery, reconnecting and revoking

You can revoke at any time: `sudo rgdesk github disconnect` removes the installation on GitHub and deletes the local key and policy
(`--keep-installation` only deletes the local files), and prints the link to delete the App itself. Or on GitHub: Settings, Applications,
Installed GitHub Apps, **Uninstall** (or suspend). After revoking, writes stop immediately.

**The recovery command is always the same:** `sudo rgdesk github connect --no-browser` (or run the setup command again). It first asks GitHub
what became of the App, then does the right thing:

| What happened | What `connect` does |
|---|---|
| Nothing wrong (App and installation are fine) | Refuses: "already connected". Use `disconnect` first, or `--reconnect` to create a *new* App on purpose (the old App and its installation stay on GitHub until you remove them). |
| The App is installed nowhere (you uninstalled it) | Resumes at the install step with the **same App**; nothing new is created. |
| You reinstalled it | Adopts the new installation. |
| The App was deleted on GitHub (or its key was rejected) | Creates a **replacement App** (its old installation went away with it). Writes stay off until `verify` passes for the new App. |
| GitHub cannot be reached | Says so and changes nothing. |

Other messages: **organization approval** pending, or the App suspended: an organization owner approves or unsuspends it, then run `status`.
**"Permissions, not protection"**: the installation has not accepted the App's Administration-read permission; approve the updated permissions
(Settings, Installed GitHub Apps, Configure) and run `verify`. **requires a reviewed PR: fail**: the protection is missing, or your plan cannot
have it (rulesets need a public repository or GitHub Pro/Team/Enterprise); the desk stays in read/proposal mode.
If creating the App fails midway (network, disk) the command ends within seconds with the reason, saves nothing, and tells you which App
to delete if one was created; just run it again.

The App key and policy are in the desk's private durable checkpoint (the stack's bucket), so a rebuilt Spot keeps the connection. Destroying
the stack with its data deletes them; disconnect first if you want the installation removed on GitHub.

## Limits of this release

- One repository and one development branch per installation (one operator, one organization).
- Spot only (see above). The Docker workstation and existing Hermes can still use proposals and Kanban cards.
- The desk cannot prove who your designated reviewers are beyond GitHub's own rules; keep CODEOWNERS and the rulesets under human control.
- Checks on the PR are read from GitHub; the desk does not run your CI.
- Validation sees the repository's files except secrets, state, `.tfvars`, symbolic links and files over 5 MB; it never plans or applies.
- The validation user can use the internet (to download Terraform providers) but not the instance metadata service or private networks.
