---
name: s3-public-access
description: "Finds S3 buckets anyone on the internet can read or write (bucket policy, access point policy, ACLs, Block Public Access) from collected configuration, with fixed rule severities. Use for S3 public access, bucket exposure, BPA checks, mission A3."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  mission: A3
  upstream: jhkchan/aws-agent-skills@eeace51bd5dd1db2030729d83eeab988861553aa skills/s3-public-access-auditor
---

# s3-public-access (mission A3, also A1)

Read-only. You never call AWS: the collector (no LLM, on the host) already gathered the
configuration. You run the rules, then explain the findings. Severity comes from the rules table
below, never from you.

## Steps

1. Find the newest facts file (tenant `self` unless the user names another):
   ```bash
   ls -d /opt/data/facts/self/*/ | tail -1      # e.g. /opt/data/facts/self/2026-10-11/
   ```
   Use `<that dir>/s3.json`. If no facts exist, stop and reply with status NOT_RUN,
   reason "no facts collected yet (run the collector)". Never try to collect them yourself.
2. Run the rules:
   ```bash
   python3 /opt/data/profiles/analyst/skills/remedigenius/s3-public-access/scripts/check.py      --facts /opt/data/facts/self/<date>/s3.json      --out /opt/data/results/self/<date>/s3-public-access.json
   ```
   It prints a one-line summary (status, count by severity).
3. Read the result file. For the findings, write annotations exactly as the `skillresult` skill
   says (explanation, impact, next_step; nothing else) and merge them with its `merge` command.
   For wording and remediation detail, read `references/upstream/UPSTREAM-SKILL.md` (condition strength, access points, website hosting, remediation wording) and `references/upstream/references/*.md`. Upstream's own verdict and severity
   words are background only; the rule table here wins.
4. Reply in plain words: what was checked (counts from `facts`), findings by severity with the
   resource and rule, the top next steps, the result file path, and any `handoff.open_questions`.
   If `status.reason` mentions collection errors, say which checks are incomplete.

## Rules (fixed)

| Rule | Severity | When |
|---|---|---|
| `BKTPUB-001` | critical | Rule 2: policy lets anyone write or change the bucket |
| `BKTPUB-002` | high | Rule 2: policy lets anyone read |
| `BKTPUB-003` | critical | Rule 3: ACL grants write to AllUsers/AuthenticatedUsers |
| `BKTPUB-004` | high | Rule 3: ACL grants read to AllUsers/AuthenticatedUsers |
| `BKTPUB-005` | medium | Rule 4: wildcard principal held back only by a strong condition (fragile) |
| `BKTPUB-006` | low | Rule 5: not public, but Block Public Access not fully on |

Rule 1 (Block Public Access fully on, bucket OR account per setting) means SAFE: no finding. An effective RestrictPublicBuckets stops Rule 2 and an effective IgnorePublicAcls (or BucketOwnerEnforced) stops Rule 3; the evidence says so in `note`.

## Never

- Never call AWS, run fix commands, or edit `findings`, `severity`, `rule_id` or `evidence`.
- Never report a finding the rules did not produce; mention suspicions as open questions instead.
- Status words only: OK, ERROR, NOT_RUN, SKIPPED (with a reason).

Provenance and changes from upstream: `PROVENANCE.md`.
