"""Versioned, target-bound independent verification (roadmap CE-18).

A pass is only a pass for one target: one installation, account, region, resource generation and artifact digest, under
one approved predicate version, from one named verifier, with retained evidence that is not stale, not truncated and not
observed under a clock skew the policy does not accept.

Technical proof and provider acknowledgement are separate events: AWS resolving a finding later does not make a failed
proof a pass, and a passing targeted check does not claim that the provider forgot the finding.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

OUTCOMES = ("pass", "fail", "error", "inconclusive")
MAX_CLOCK_SKEW_SECONDS = 300
DEFAULT_FRESHNESS = timedelta(hours=6)
POLICY_TARGETED = "targeted"      # a targeted authoritative check may close the finding
POLICY_PROVIDER = "provider"      # only the provider resolving it may close it


class VerificationError(ValueError):
    """A proof cannot be represented or evaluated as given."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Predicate:
    """An approved rule. Changing the rule or its parameters is a new version, never an edit."""

    predicate_id: str
    version: str
    rule: str
    parameters: dict = field(default_factory=dict)
    requires_evidence: bool = True

    def __post_init__(self):
        if not self.predicate_id or not self.version or not self.rule:
            raise VerificationError("a predicate needs an id, a version and a rule")

    def digest(self) -> str:
        return hashlib.sha256(_canonical([self.predicate_id, self.version, self.rule, self.parameters]).encode()).hexdigest()


@dataclass(frozen=True)
class Target:
    """The exact thing a proof is about. Anything else is a different target."""

    target_id: str
    installation_id: str
    account_id: str
    region: str
    resource_generation: str = ""
    artifact_digest: str = ""


@dataclass(frozen=True)
class Observation:
    """What a verifier saw, and what could make it unusable."""

    target: Target
    predicate: Predicate
    outcome: str
    verifier: str
    observed_at: datetime
    evidence_sha256: str = ""
    account_id: str = ""
    region: str = ""
    truncated: bool = False
    partial: bool = False
    provider_acknowledged: bool = False
    clock_skew_seconds: int = 0

    def __post_init__(self):
        if self.outcome not in OUTCOMES:
            raise VerificationError(f"outcome must be one of {', '.join(OUTCOMES)}")
        if not self.verifier:
            raise VerificationError("an observation needs a named verifier")


def evaluate(observation: Observation, *, approved: Target | None = None, now: datetime | None = None,
             max_skew_seconds: int = MAX_CLOCK_SKEW_SECONDS, freshness: timedelta = DEFAULT_FRESHNESS) -> dict:
    """One verdict, fail closed. `verified` is true only when every binding holds and the result is a pass."""
    now = now or _now()
    problems = []
    target, predicate = observation.target, observation.predicate
    if approved is not None:
        for name in ("target_id", "account_id", "region", "resource_generation", "artifact_digest"):
            if getattr(approved, name) != getattr(target, name):
                problems.append(f"{name} does not match the approved target")
    if not target.installation_id:
        problems.append("the target has no installation")
    if not target.account_id:
        problems.append("the target has no account")
    if observation.account_id and observation.account_id != target.account_id:
        # Never fall back to another configured account: that would prove a different target.
        problems.append("the observation is from another account")
    if observation.region and target.region and observation.region != target.region:
        problems.append("the observation is from another region")
    if observation.truncated:
        problems.append("the read was truncated")
    if observation.partial:
        problems.append("the read was partial")
    if predicate.requires_evidence and not observation.evidence_sha256:
        problems.append("the proof has no retained evidence")
    if observation.clock_skew_seconds > max_skew_seconds:
        problems.append(f"clock skew {observation.clock_skew_seconds}s exceeds the accepted {max_skew_seconds}s")
    if observation.observed_at > now + timedelta(seconds=max_skew_seconds):
        problems.append("the observation is in the future")
    elif now - observation.observed_at > freshness:
        problems.append("the proof is stale")
    verified = not problems and observation.outcome == "pass"
    return {"verified": verified, "outcome": observation.outcome, "problems": problems,
            "reason": "; ".join(problems) if problems else ("proof passed" if verified else f"proof {observation.outcome}"),
            "target_id": target.target_id, "target_generation": target.resource_generation,
            "artifact_digest": target.artifact_digest, "predicate_id": predicate.predicate_id,
            "predicate_version": predicate.version, "rule": predicate.rule, "verifier": observation.verifier,
            "evidence_sha256": observation.evidence_sha256,
            # Deliberately not part of `verified`: the provider is a separate event.
            "provider_acknowledged": observation.provider_acknowledged}


def provider_resolution(observation: Observation, *, resolved_at: datetime | None = None, evidence_sha256: str = "") -> dict:
    """AWS later resolving the finding. A separate fact, with no effect on the technical proof."""
    return {"kind": "provider_resolution", "target_id": observation.target.target_id,
            "provider_acknowledged": True, "resolved_at": (resolved_at or _now()).isoformat(),
            "evidence_sha256": evidence_sha256,
            "affects_technical_proof": False,
            "note": "a provider resolution never turns a failed proof into a pass, and a pass never claims it"}


def may_close(verdict: dict, policy: str = POLICY_TARGETED) -> bool:
    """The policy decides whether a targeted authoritative check is enough to close; the verdict only reports."""
    if policy not in (POLICY_TARGETED, POLICY_PROVIDER):
        raise VerificationError(f"unknown verification policy {policy!r}")
    if policy == POLICY_PROVIDER:
        return bool(verdict.get("verified") and verdict.get("provider_acknowledged"))
    return bool(verdict.get("verified"))


def attempt_row(observation: Observation, verdict: dict, *, received_at: datetime | None = None) -> dict:
    """Every attempt is persisted, including failures, errors and inconclusive results."""
    target, predicate = observation.target, observation.predicate
    attempt_id = hashlib.sha256(_canonical([
        predicate.predicate_id, predicate.version, target.target_id, target.resource_generation,
        target.artifact_digest, observation.verifier, observation.observed_at.isoformat(),
        observation.outcome]).encode()).hexdigest()
    return {
        "attempt_id": attempt_id, "predicate_id": predicate.predicate_id, "predicate_version": predicate.version,
        "predicate_digest": predicate.digest(), "rule": predicate.rule,
        "installation_id": target.installation_id, "target_id": target.target_id, "account_id": target.account_id,
        "region": target.region, "resource_generation": target.resource_generation,
        "artifact_digest": target.artifact_digest, "verifier": observation.verifier,
        "outcome": observation.outcome, "verified": verdict["verified"], "reason": verdict["reason"],
        "evidence_sha256": observation.evidence_sha256, "truncated": observation.truncated,
        "partial": observation.partial, "clock_skew_seconds": observation.clock_skew_seconds,
        "provider_acknowledged": observation.provider_acknowledged,
        "observed_at": observation.observed_at, "received_at": received_at or _now(),
    }