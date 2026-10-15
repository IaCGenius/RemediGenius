# Provenance: debugging-lambda-timeouts

| | |
|---|---|
| Upstream | [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws) `skills/specialized-skills/serverless-skills/debugging-lambda-timeouts` |
| Pinned commit | `2cb0fa1c2e668e1bb075028800b6b27efb95779e` (see `skills.lock.json`, verified by `tools/vendor.py verify`) |
| License | Apache-2.0 (copy in `references/upstream/LICENSE`) |
| Vetting | 2026-10-10: SkillSpector static scan (no LLM) CAUTION; reviewed for the kiosk builder 2026-10-12 |
| Injected | text only: upstream `SKILL.md` (renamed `UPSTREAM-SKILL.md`) and `references/`; no scripts or assets |
| Adapted by | RemediGenius, 2026-10-12, version 0.1.0, for the `builder` profile |

## Changes from upstream

- Our `SKILL.md` maps the guidance onto the lambda kiosk: the gate deploys (no SAM/CDK/CLI deploys), rights come
  from kiosk classes, evidence comes from `kiosk show|logs|receipt`, AWS APIs are looked up with `kiosk sdk`.
- Features the kiosk does not offer are listed as "does not apply"; the agent reports them instead of working around.

## Rebuild

`python tools/vendor.py fetch` restores the upstream copy from the pinned commit.
