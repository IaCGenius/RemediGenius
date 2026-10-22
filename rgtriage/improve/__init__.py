"""Continuous improvement for RemediGenius-CE, without a second agent runtime.

Deterministic parts live here and run in the desk: evaluation fixtures and grading, the security gate for skill
candidates, trace analysis (failures, lessons, knowledge gaps), consolidation and context hints. The parts that need
the model (replaying tasks, proposing skill edits) run offline in the Hermes container through Hermes's own plugin
model access and call back into these functions; nothing here calls a model or AWS.

Ideas borrowed, not runtimes: SkillOpt (bounded skill edits accepted only when a held-out validation score strictly
improves) and Harness² (Propose–Probe–Compose on one task, and a library of evidence-supported lessons).
"""
