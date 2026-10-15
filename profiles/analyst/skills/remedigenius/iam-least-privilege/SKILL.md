---
name: iam-least-privilege
description: "Finds over-permissive IAM policies (admin wildcards, privilege-escalation actions and service wildcards, NotAction/NotResource, broad resources, bypass-prone conditions) from collected configuration, with fixed rule severities. Use for IAM least privilege, wildcard permissions, privilege escalation, mission B6."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  mission: B6
  upstream: jhkchan/aws-agent-skills@eeace51bd5dd1db2030729d83eeab988861553aa skills/iam-least-privilege-advisor
---

# iam-least-privilege (mission B6, also B1, A5)

Read-only. You never call AWS: the collector (no LLM, on the host) already gathered the
configuration. You run the rules, then explain the findings. Severity comes from the rules table
below, never from you.

## Steps

1. Find the newest facts file (tenant `self` unless the user names another):
   ```bash
   ls -d /opt/data/facts/self/*/ | tail -1      # e.g. /opt/data/facts/self/2026-10-11/
   ```
   Use `<that dir>/iam.json`. If no facts exist, stop and reply with status NOT_RUN,
   reason "no facts collected yet (run the collector)". Never try to collect them yourself.
2. Run the rules:
   ```bash
   python3 /opt/data/profiles/analyst/skills/remedigenius/iam-least-privilege/scripts/check.py      --facts /opt/data/facts/self/<date>/iam.json      --out /opt/data/results/self/<date>/iam-least-privilege.json
   ```
   It prints a one-line summary (status, count by severity).
3. Read the result file. For the findings, write annotations exactly as the `skillresult` skill
   says (explanation, impact, next_step; nothing else) and merge them with its `merge` command.
   For wording and remediation detail, read `references/upstream/UPSTREAM-SKILL.md` (escalation catalog, condition bypasses, CloudTrail-derived least-privilege remediation) and `references/upstream/references/*.md`. Upstream's own verdict and severity
   words are background only; the rule table here wins.
4. Reply in plain words: what was checked (counts from `facts`), findings by severity with the
   resource and rule, the top next steps, the result file path, and any `handoff.open_questions`.
   If `status.reason` mentions collection errors, say which checks are incomplete.

## Rules (fixed)

| Rule | Severity | When |
|---|---|---|
| `IAMLP-001` | critical | Action * on Resource * (administrator) |
| `IAMLP-002` | critical | Wildcard on a privilege-escalation service (iam, sts, kms, secretsmanager, ssm, lambda, cloudformation) on * |
| `IAMLP-003` | high | Privilege-escalation action on * (PassRole, AssumeRole, CreatePolicy(Version), Attach/PutRolePolicy, UpdateAssumeRolePolicy, CreateServiceLinkedRole) |
| `IAMLP-004` | high | NotAction or NotResource in an Allow |
| `IAMLP-005` | high | Other service wildcard on * (Describe*/List* excepted) |
| `IAMLP-006` | high | Resource pattern spans every partition or every bucket |
| `IAMLP-007` | medium | Wildcard actions on scoped resources, or a bypass-prone condition |

Customer-managed and inline policies get every rule. AWS-managed policies are judged only on IAMLP-001..003 (their broad read-only grants are by design). Service-linked roles are skipped. Deny statements never produce findings. Effective permissions (boundaries, SCPs, unused access) are not evaluated in v0.

## Never

- Never call AWS, run fix commands, or edit `findings`, `severity`, `rule_id` or `evidence`.
- Never report a finding the rules did not produce; mention suspicions as open questions instead.
- Status words only: OK, ERROR, NOT_RUN, SKIPPED (with a reason).

Provenance and changes from upstream: `PROVENANCE.md`.
