"""Remove secrets from text before it is stored as evidence or sent to a model.

Defense in depth: the desk never returns secrets, but users paste things and tools echo text. Account ids, resource
names and finding refs are kept because evidence is useless without them. The Hermes plugin carries an identical
copy (it cannot import this package); a test keeps the two in step.
"""
from __future__ import annotations

import re

PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\b(AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b"), "[REDACTED AWS KEY ID]"),
    (re.compile(r"(?i)(aws_secret_access_key|aws_session_token|secret_?access_?key|session_?token)(\s*[=:]\s*|\"\s*:\s*\")[A-Za-z0-9/+=]{16,}"),
     r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)(\s*[=:]\s*)([^\s\"',;]{8,})"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]{16,}"), r"\1[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED API KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED TOKEN]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED TOKEN]"),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED JWT]"),
]


def redact(text, limit: int | None = None) -> str:
    out = "" if text is None else str(text)
    for pattern, replacement in PATTERNS:
        out = pattern.sub(replacement, out)
    if limit and len(out) > limit:
        out = out[:limit] + f" …[{len(out) - limit} more characters]"
    return out


def redact_obj(value, limit: int = 2000):
    """Redact every string in a JSON-like structure."""
    if isinstance(value, str):
        return redact(value, limit)
    if isinstance(value, dict):
        return {k: redact_obj(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_obj(v, limit) for v in value[:50]]
    return value
