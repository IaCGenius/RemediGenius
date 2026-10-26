# GitHub: fixes as pull requests into your development branch

RemediGenius-CE can turn a validated IaC fix into a **pull request**. It never merges, approves or touches your production
branch: a person reviews and merges. This page covers setup, how it stays safe, and how to disconnect.

Available on the **Spot** deployment (the App key lives in a folder the agent container cannot see). On the Docker workstation and
with an existing Hermes the desk's state folder is readable by the agent, so GitHub shows `Blocked` and explains why.

## What you get

| State | Meaning |
|---|---|
| **Disconnected** | No GitHub App yet. Run `sudo rgdesk github connect --no-browser`. |
| **Connected: read/proposal access** | The App is installed. The desk can read the repository (and keeps a read-only copy for `fix`), but cannot write: protection is not verified, or no reviewer is set. |
| **Ready to create development PRs** | The repository, development branch and human reviewer are set, and GitHub shows the protections below. |
| **Blocked** | Something specific is wrong (consent pending, installation removed, key invalid, protection missing). `sudo rgdesk github status` prints the remedy. |

## Connect (once, about two minutes)

Run these in an SSM session on the instance (`aws ssm start-session --target <instance>`), as `sudo rgdesk github ...`: `rgdesk` runs
the desk CLI as the desk user, the only user that can read the App key. For the browser step, forward the callback port from your
computer first (a second terminal):
`aws ssm start-session --target <instance> --document-name AWS-StartPortForwardingSession --parameters portNumber=8743,localPortNumber=8743`.

1. `sudo rgdesk github connect --no-browser` (add `--org YOUR-ORG` to create the App under an organization you own).
2. Open `http://localhost:8743/`. GitHub shows **Create GitHub App** with the definition pre-filled: click it once. GitHub hands the App
   key straight back to the desk; you never copy a secret.
3. Click **Install**, choose **Only select repositories** and pick the one repository RemediGenius may use.
4. `sudo rgdesk github configure --repo OWNER/REPO --base dev --reviewer YOUR-GITHUB-LOGIN` (repeat `--reviewer`, or use `ORG/team-slug`).
5. If the development branch or the protections do not exist yet, apply [`deploy/github`](../deploy/github/README.md) as a repository
   administrator, then `sudo rgdesk github verify`.
6. `sudo rgdesk github status` shows the connected identity (`<app>[bot]`), repository, branches, reviewers and whether writes are enabled.

The desk also mirrors the development branch read-only (secrets, state files and `.tfvars` are left out) and writes a **Repository**
page in the Knowledge tab (draft, for you to confirm). Run `sudo rgdesk github refresh` (or ask the agent: "I updated the repo, refresh it")
after you change the repository.

## Using it

Ask for a fix as before. When GitHub is ready the agent offers a PR; you approve the single `github publish` prompt. The desk then:

1. Re-checks the repository and the protections (a failed check denies the write).
2. Validates the change on a copy of the repository with **no credentials**: `terraform init/validate/fmt`, `tflint`, `cfn-lint`, and
   YAML/JSON checks. A failed check pushes nothing. A tool that is missing is shown as **skipped (not validated)**.
3. Creates or reuses `feature/remedigenius/<task>-<id>`, commits through the GitHub API (no `git push`, no repository hooks run),
   and opens or updates **one** PR into your development branch, asks your reviewers, and links the PR to the fix record.

Retrying never duplicates a PR. If the branch already has someone else's commits, or moved while publishing, the desk stops and does not
overwrite or force-push.

## What enforces what

GitHub App permissions cannot separate "open a PR" from "approve or merge a PR", so two layers cooperate:

| Rule | Enforced by |
|---|---|
| Only the configured repository | The desk (every request is checked before it is sent) |
| Writes only to `feature/remedigenius/*`; PR base is the configured development branch; never `main`, `master`, release or production | The desk (before sending) **and** GitHub rulesets on `dev` and `main` |
| No force push, no delete | The desk **and** GitHub rulesets |
| Never approve, merge, enable auto-merge or change protections | The desk (those requests do not exist in its code); GitHub's App permissions would otherwise allow some of them |
| A human review is required to merge | GitHub (`pull_request` rule, CODEOWNERS). The PR is authored by the App's bot identity, so **any** human, including you, can approve it |
| Workflows, CODEOWNERS, `.git`, state files and keys cannot be changed | The desk refuses those paths in a proposal |
| The agent never holds a token | The App key is in `/data/rggithub` on the host (mode 0700, not mounted into any container); installation tokens last one hour, are narrowed to the one repository and the needed permission, and are never stored |
| Instructions inside repository files, issues or PR comments | Treated as data. Repository, branch and reviewers come only from the operator's policy file |

The App is granted: Contents write, Pull requests write, Checks read, Commit statuses read, Administration read (only to read the
effective protections), Metadata read. It has no Workflows permission, and no webhook or event subscription.

## Reconnect, disconnect, troubleshoot

- **Reconnect** (expired or removed credentials, App deleted): `sudo rgdesk github connect --no-browser`, then `configure` again.
- **Disconnect**: `sudo rgdesk github disconnect` removes the installation on GitHub and deletes the local key and policy
  (`--keep-installation` only deletes the local files). It prints the link to delete the App itself. You can also revoke at any time on
  GitHub: Settings, Applications, Installed GitHub Apps, **Uninstall** (or suspend).
- **Blocked: credentials rejected / cannot see the repository**: the installation was removed or the repository deselected. Reconnect.
- **Blocked: organization approval**: an organization owner must approve the App. Ask them, then run `status`.
- **requires a reviewed PR: fail**: protection is missing or not visible. Apply `deploy/github`, or your plan does not support it (rulesets
  need a public repository or GitHub Pro/Team/Enterprise). The desk stays in read/proposal mode.
- **App could not be created / state mismatch**: run `connect` again; the page is only valid for the command that started it and for one hour.
- Backups: the App key and policy are in the desk's private durable checkpoint (S3 bucket of the stack), so a rebuilt Spot keeps the
  connection. Destroying the stack with its data deletes them; disconnect first if you want the installation removed on GitHub.

## Limits of this release

- One repository and one development branch per installation (one operator, one organization).
- Spot only (see above). The Docker workstation and existing Hermes can still use proposals and Kanban cards.
- The desk cannot prove who your designated reviewers are beyond GitHub's own rules; keep CODEOWNERS and the rulesets under human control.
- Checks on the PR are read from GitHub; the desk does not run your CI.
