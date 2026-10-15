# Provenance: sg-exposure

| | |
|---|---|
| Upstream | [jhkchan/aws-agent-skills](https://github.com/jhkchan/aws-agent-skills) `skills/ec2-security-group-auditor` |
| Pinned commit | `eeace51bd5dd1db2030729d83eeab988861553aa` (see `skills.lock.json`, verified by `tools/vendor.py verify`) |
| License | Apache-2.0 (copy in `references/upstream/LICENSE`) |
| Vetting | 2026-10-10: SkillSpector static scan (no LLM) CAUTION; pi review: ready, read-only, fit strong; deep dive pick |
| Verbatim copy | `references/upstream/` (upstream `SKILL.md` renamed `UPSTREAM-SKILL.md` so Hermes never loads it as a skill) |
| Adapted by | RemediGenius, 2026-10-11, version 0.1.0 |

## Changes from upstream

- Decision procedure, source classification, prefix-list procedure and high-risk port registry turned into `scripts/check.py`.
- Severity table (upstream CVSS-style, chosen by the model) replaced by fixed rules SGNET-001..006.
- 'Behind ALB/WAF' is not knowable from SG data; replaced by attached vs not attached to network interfaces.
- Our parameter: a non-private CIDR of /16 or broader (IPv6 /32) counts as the internet; narrower public ranges are restricted (upstream: /32 restricted, broader-than-RFC1918 public).
- Upstream slip corrected: its example says range `440-450` holds only 443; it also holds 445 (SMB, in upstream's own registry), so our rules rate it high (SGNET-004).
- Removed: live remediation CLI. Output: SkillResult v0.

## Rebuild

`python tools/vendor.py fetch` restores the upstream copy from the pinned commit; our files
(`SKILL.md`, `scripts/`, this file) are the adaptation and live only in this repo.
