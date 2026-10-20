"""Focused boundary tests for the exact-hash native dashboard overlay.

The overlay must fail closed: an unreviewed source hash, a missing anchor or a
duplicated anchor raises instead of silently skipping the fix. No Docker or model
calls are made here.
"""
import hashlib
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_session_limits as overlay  # noqa: E402


def _body(anchors=1):
    return b'header\n' + (overlay.OLD + b'\n') * anchors + b'footer\n'


def test_overlay_fails_closed_on_unreviewed_source_hash():
    with pytest.raises(ValueError):
        overlay.overlay(b'anything not from the reviewed pinned image')


def test_overlay_fails_closed_when_anchor_missing(monkeypatch):
    body = b'header\nfooter\n'
    monkeypatch.setattr(overlay, 'SOURCE_SHA256', hashlib.sha256(body).hexdigest())
    with pytest.raises(ValueError):
        overlay.overlay(body)


def test_overlay_fails_closed_when_anchor_duplicated(monkeypatch):
    body = _body(anchors=2)
    monkeypatch.setattr(overlay, 'SOURCE_SHA256', hashlib.sha256(body).hexdigest())
    with pytest.raises(ValueError):
        overlay.overlay(body)


def test_overlay_applies_the_reviewed_replacement(monkeypatch):
    body = _body(anchors=1)
    monkeypatch.setattr(overlay, 'SOURCE_SHA256', hashlib.sha256(body).hexdigest())
    patched = overlay.overlay(body)
    assert overlay.OLD not in patched
    assert patched.count(overlay.NEW) == 1


def test_reviewed_pin_is_the_single_source_of_truth():
    # If a future image changes this constant the overlay must fail closed for review,
    # never silently skip the session bound.
    assert overlay.OLD == b'ttl=30 * 60, max_sessions=16, buffer_cap=1 * 1024 * 1024'
    assert overlay.NEW == b'ttl=10 * 60, max_sessions=2, buffer_cap=1 * 1024 * 1024'