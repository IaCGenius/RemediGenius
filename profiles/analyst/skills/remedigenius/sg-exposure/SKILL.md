---
name: sg-exposure
description: "Finds EC2 security groups that expose ports to the internet (IPv4, IPv6, prefix lists, port-range overlap with a high-risk port registry) from collected configuration, with fixed rule severities. Use for security group audits, open ports, 0.0.0.0/0, mission A6."
license: Apache-2.0
metadata:
  owner: remedigenius
  version: 0.1.0
  mission: A6
  upstream: jhkchan/aws-agent-skills@eeace51bd5dd1db2030729d83eeab988861553aa skills/ec2-security-group-auditor
---

# sg-exposure (mission A6, also A1)

Read-only. You never call AWS: the collector (no LLM, on the host) already gathered the
configuration. You run the rules, then explain the findings. Severity comes from the rules table
below, never from you.

## Steps

1. Find the newest facts file (tenant `self` unless the user names another):
   ```bash
   ls -d /opt/data/facts/self/*/ | tail -1      # e.g. /opt/data/facts/self/2026-10-11/
   ```
   Use `<that dir>/sg.json`. If no facts exist, stop and reply with status NOT_RUN,
   reason "no facts collected yet (run the collector)". Never try to collect them yourself.
2. Run the rules:
   ```bash
   python3 /opt/data/profiles/analyst/skills/remedigenius/sg-exposure/scripts/check.py      --facts /opt/data/facts/self/<date>/sg.json      --out /opt/data/results/self/<date>/sg-exposure.json
   ```
   It prints a one-line summary (status, count by severity).
3. Read the result file. For the findings, write annotations exactly as the `skillresult` skill
   says (explanation, impact, next_step; nothing else) and merge them with its `merge` command.
   For wording and remediation detail, read `references/upstream/UPSTREAM-SKILL.md` (port registry, compliance mapping CIS 5.1/5.2, remediation wording) and `references/upstream/references/*.md`. Upstream's own verdict and severity
   words are background only; the rule table here wins.
4. Reply in plain words: what was checked (counts from `facts`), findings by severity with the
   resource and rule, the top next steps, the result file path, and any `handoff.open_questions`.
   If `status.reason` mentions collection errors, say which checks are incomplete.

## Rules (fixed)

| Rule | Severity | When |
|---|---|---|
| `SGNET-001` | critical | All ports or all protocols open to the internet |
| `SGNET-002` | critical | Admin or cluster-control port open (SSH, RDP, VNC, Docker, Kubernetes, etcd) |
| `SGNET-003` | critical | Database or cache port open (MySQL, Postgres, MSSQL, Oracle, Mongo, Redis, Elasticsearch...) |
| `SGNET-004` | high | Other high-risk port open (queues, SMB/RPC, LDAP, SMTP, UDP amplification) |
| `SGNET-005` | medium | Non-critical port open on a group attached to network interfaces |
| `SGNET-006` | low | Non-critical port open on a group with no network interfaces |

A source counts as the internet when it is 0.0.0.0/0, ::/0, a non-private CIDR of /16 or broader (/32 for IPv6), or an AWS-managed / public prefix list. Security-group references and private ranges are restricted. One finding per group: its worst rule.

## Never

- Never call AWS, run fix commands, or edit `findings`, `severity`, `rule_id` or `evidence`.
- Never report a finding the rules did not produce; mention suspicions as open questions instead.
- Status words only: OK, ERROR, NOT_RUN, SKIPPED (with a reason).

Provenance and changes from upstream: `PROVENANCE.md`.
