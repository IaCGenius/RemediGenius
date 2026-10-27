# GitHub-side protection for RemediGenius-CE

These files are for a **repository administrator**. Apply them with your own GitHub login, never with the RemediGenius App
(the App has no permission to change protections, and the desk refuses to try).

1. Create the development branch if it does not exist, from a commit you choose (record it):
   `gh api repos/OWNER/REPO/git/refs -f ref=refs/heads/dev -f sha=$(gh api repos/OWNER/REPO/commits/main --jq .sha)`
2. Edit `REPLACE-WITH-YOUR-CI-CHECK-NAME` in both files (or delete the `required_status_checks` rule if you have no CI yet:
   the desk then warns instead of blocking).
3. Apply both rulesets:
   `gh api -X POST repos/OWNER/REPO/rulesets --input ruleset-dev.json`
   `gh api -X POST repos/OWNER/REPO/rulesets --input ruleset-main.json`
4. Keep `bypass_actors` empty. In particular never add the RemediGenius App, "Repository admin" or "Organization admin".
5. Put a `CODEOWNERS` file on `dev` and `main` that names your human reviewers or team, and covers `CODEOWNERS` and `.github/` itself.
   `require_code_owner_review` makes those people's approval mandatory; bots and the App cannot be code owners.
6. Run `rgtriage github verify` on the desk: it reads the effective rules (including organization rulesets) and enables PR creation
   only when a reviewed PR is required on both branches and force pushes and deletions are blocked.

Rulesets need a public repository, or GitHub Pro/Team/Enterprise for private ones. Without them `verify` reports
"requires a reviewed PR: fail" and the desk stays in read/proposal mode. This is deliberate.
