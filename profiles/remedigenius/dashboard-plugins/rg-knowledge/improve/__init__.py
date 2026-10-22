"""Offline skill improvement for RemediGenius-CE (runs in the Hermes container, never in production chat).

- `llm`: the model, through Hermes's plugin model access (the configured provider), an OpenAI-compatible endpoint for
  local development, or a scripted mock for tests.
- `runner`: replays evaluation tasks with a candidate skill (read-only tools against the desk's fixture), SkillOpt-style
  optimization (bounded edits, learning-rate cap, strict held-out gate), Harness²-style Propose–Probe–Compose on one
  failed task, a lesson library, candidate staging, approval, activation and rollback.

Scoring and the security gate are deterministic and run in the desk (`rgtriage improve ...`); this package only asks
the desk for them, so a model can never grade or approve its own work.
"""
