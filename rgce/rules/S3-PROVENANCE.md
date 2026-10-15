# Provenance: s3-public-access

| | |
|---|---|
| Upstream | [jhkchan/aws-agent-skills](https://github.com/jhkchan/aws-agent-skills) `skills/s3-public-access-auditor` |
| Pinned commit | `eeace51bd5dd1db2030729d83eeab988861553aa` (see `skills.lock.json`, verified by `tools/vendor.py verify`) |
| License | Apache-2.0 (copy in `references/upstream/LICENSE`) |
| Vetting | 2026-10-10: SkillSpector static scan (no LLM) CAUTION; pi review: ready, read-only, fit strong; deep dive pick |
| Verbatim copy | `references/upstream/` (upstream `SKILL.md` renamed `UPSTREAM-SKILL.md` so Hermes never loads it as a skill) |
| Adapted by | RemediGenius, 2026-10-11, version 0.1.0 |

## Changes from upstream

- Rules 1-5 turned into `scripts/check.py` (deterministic); severities fixed in its RULES table.
- Effective Block Public Access = bucket OR account per setting (upstream truth table).
- Refinement: effective RestrictPublicBuckets stops Rule 2, IgnorePublicAcls stops Rule 3 (AWS evaluation).
- Condition strength: upstream STRONG keys + aws:PrincipalAccount/PrincipalArn/SourceArn/OrgPaths; aws:SourceIp is strong when private or /8 and narrower.
- Access point policies not collected in v0 (reported as an open question, NOT_RUN).
- Removed: live remediation CLI (upstream pre-flight + remediation sections). The agent only writes next steps for a human.
- Output: SkillResult v0 instead of BUCKET/VERDICT/REASON/REMEDIATION text blocks.

## Rebuild

`python tools/vendor.py fetch` restores the upstream copy from the pinned commit; our files
(`SKILL.md`, `scripts/`, this file) are the adaptation and live only in this repo.
