---
name: results
description: Read the assessment results the analyst wrote (which AWS accounts were assessed, when, findings by severity, what changed between days). Use for any question about accounts, assessments, findings, severity, the Morning Brief or "what changed".
license: proprietary
metadata:
  owner: remedigenius
  version: 0.1.0
---

# Assessment results (read-only)

Results live on the shared data volume. Never answer from memory; always run the script.

```
/opt/data/results/<tenant>/<YYYY-MM-DD>/<skill>.json     SkillResult v0, one per skill
/opt/data/facts/<tenant>/<YYYY-MM-DD>/{s3,sg,iam}.json   raw facts the collector read (no LLM)
```

A tenant is one AWS account (`self` is our own account). Folders whose name is not a plain date are not runs; ignore them.

## Commands

The script is `scripts/results.py` in this skill's folder.

```bash
python3 scripts/results.py overview                    # every tenant: latest run, status per skill, findings by severity
python3 scripts/results.py show --tenant prod        # latest run's findings with the analyst's explanation
python3 scripts/results.py show --tenant self --severity critical,high
python3 scripts/results.py diff --tenant self          # latest run vs the run before: new and resolved findings
```

## How to answer
- Quote counts and severities exactly as the script prints them. Severity comes from rules; never change it.
- Refer to accounts by tenant name. Do not store account IDs, ARNs or user names in memory. In chat, give them
  only when the owner asks for the detail.
- If a skill's status is not OK, say so with its reason. If a tenant has no run, say NOT_RUN.
- With only one run, `diff` has nothing to compare; say that plainly.
