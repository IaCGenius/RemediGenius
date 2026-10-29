# Claude Code notes

@AGENTS.md

The imported file is the source of truth for how to work in this repository: environment, commands, the validation tiers,
and the rules that came out of the v0.5.0 release. Nothing in this file overrides it.

## Local specifics

- `.claude/skills/` contains third-party marketing and copy-editing skills. They are not engineering guidance for this
  product and are not part of the release.
- `.claude/settings.local.json` holds local permission grants only; it is machine-specific and stays out of git.
- The checkout is Windows (`cmd.exe`, `python` on PATH). Prefer `python` and `cmd` syntax in commands you give the user,
  and absolute paths in file tools.
- `.rgce/` is the private scratch area (handoffs, Spot settings, logs, screenshots). Never copy its contents into a
  tracked file, a commit message, a pull request body or an issue.

## Working expectations

- Read `docs/STORAGE.md`, `docs/SCHEMA.md` and `docs/RELEASE-VALIDATION.md` before changing storage, schemas or release
  behaviour.
- When you believe a change is ready, say which validation tier you actually ran and what it cannot prove. Do not
  present a green local suite as evidence of deployability.
- If a cloud defect appears, fix it in a batch and spend the next Spot cycle on several related fixes rather than one.