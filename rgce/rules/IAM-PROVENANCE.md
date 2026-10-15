# Provenance: iam-least-privilege

| | |
|---|---|
| Upstream | [jhkchan/aws-agent-skills](https://github.com/jhkchan/aws-agent-skills) `skills/iam-least-privilege-advisor` |
| Pinned commit | `eeace51bd5dd1db2030729d83eeab988861553aa` (see `skills.lock.json`, verified by `tools/vendor.py verify`) |
| License | Apache-2.0 (copy in `references/upstream/LICENSE`) |
| Vetting | 2026-10-10: SkillSpector static scan (no LLM) CAUTION; pi review: ready, read-only, fit strong; deep dive pick |
| Verbatim copy | `references/upstream/` (upstream `SKILL.md` renamed `UPSTREAM-SKILL.md` so Hermes never loads it as a skill) |
| Adapted by | RemediGenius, 2026-10-11, version 0.1.0 |

## Changes from upstream

- Steps 1-9 and 11 turned into `scripts/check.py`; RISK words replaced by fixed severities IAMLP-001..007.
- Step 5 (privilege-escalation actions on *) fixed at high; upstream leaves it to the model.
- Describe*/List* wildcards on * accepted (upstream lists ec2:Describe* as a legitimate exception).
- AWS-managed policies judged only on IAMLP-001..003; service-linked roles skipped.
- Not in v0: step 10 size warnings, permission boundaries, SCPs, CloudTrail last-used data, simulate-principal-policy.
- Removed: live CLI (simulate-principal-policy, CloudTrail lookups). Output: SkillResult v0.

## Rebuild

`python tools/vendor.py fetch` restores the upstream copy from the pinned commit; our files
(`SKILL.md`, `scripts/`, this file) are the adaptation and live only in this repo.
