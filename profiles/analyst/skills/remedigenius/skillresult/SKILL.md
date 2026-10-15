---
name: skillresult
description: The SkillResult v0 output contract shared by every RemediGenius skill, and the only allowed way to add explanations to findings (merge). Use when finishing any remedigenius skill, writing annotations, or validating a result file.
license: proprietary
metadata:
  owner: remedigenius
  version: 0.1.0
---

# SkillResult v0

Every RemediGenius skill ends with one JSON file in this shape:

```json
{
  "skill": "s3-public-access@0.1.0",
  "mission": "A3",
  "role": "analyst",
  "status": {"status": "OK | ERROR | NOT_RUN | SKIPPED", "reason": "..."},
  "scope": {"tenant": "self", "account": "...", "regions": ["us-east-1"]},
  "calls": [{"api": "s3:GetBucketPolicy", "count": 12, "status": "OK"}],
  "facts": {"buckets": 12},
  "findings": [ Finding rows, from rules ],
  "annotations": [ {"row_id", "explanation", "impact", "next_step"} ],
  "handoff": {"next_roles": ["desk"], "open_questions": ["..."]}
}
```

## Who writes what

| Part | Written by | You may change it? |
|---|---|---|
| `findings` (rule_id, severity, evidence) | the skill's `scripts/check.py` (fixed rules) | **Never** |
| `status`, `calls`, `facts`, `scope` | `check.py` | Never |
| `annotations` | **you**, one per finding you explain | Yes, through `merge` only |
| `handoff.open_questions` | `check.py`, and you may suggest more in your reply | In your reply |

## Writing annotations

For each finding (all of them if 20 or fewer, otherwise every critical and high plus a sample of the rest):

- `explanation`: what the configuration is, in plain words, citing the evidence fields.
- `impact`: what an attacker or mistake could do because of it. No new severity words.
- `next_step`: one concrete, reversible action for a human (console path or CLI). You never run it.

Write them to a file, then merge (the merge refuses anything except those four fields):

```bash
python3 /opt/data/profiles/analyst/skills/remedigenius/skillresult/scripts/skillresult.py \
  merge --result <result.json> --annotations <annotations.json>
```

`annotations.json` is `{"annotations": [{"row_id": "...", "explanation": "...", "impact": "...", "next_step": "..."}]}`.

## Rules

- Status words only: OK, ERROR, NOT_RUN, SKIPPED (always with a reason).
- Never invent a finding the rules did not produce. If you notice something the rules miss, put it in your reply as an open question.
- No secrets or stored data in any field.
