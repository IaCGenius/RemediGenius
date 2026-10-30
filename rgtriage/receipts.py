"""Deployment receipts from existing CI/CD (roadmap CE-17).

This is receipt ingestion, not a deployment engine. A receipt says what a trusted producer observed - a pull request, a
merge, a build, a deployment, an independent verification - and each of those stays a separate fact. A merged PR or a
green build never marks a target deployed, and nothing here ever resubmits a change.

The checks are pure. The caller supplies what is already stored (`existing`: identity -> payload digest) so the same
rules run in tests and in the desk: an identical replay is a duplicate, a changed payload under the same identity is
quarantined, and a receipt that does not match the approved plan is rejected with the reason.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

KINDS = ("pr", "merge", "build", "deploy", "verify")

# Which receipt kind may satisfy which plan step. Everything else is a separate fact on purpose: a merge is not a
# build, a build is not a deployment, and a deployment is not a verification.
STEP_RECEIPTS = {"merged": ("merge",), "built": ("build",), "deployed": ("deploy",), "verified": ("verify",)}

REQUIRED = {
    "pr": ("pr_number", "url"),
    "merge": ("pr_number", "merge_commit"),
    "build": ("commit", "build_invocation", "artifact_digest"),
    "deploy": ("artifact_digest", "deployment_revision", "target_id", "target_generation"),
    "verify": ("passed",),
}

STATUS_ACCEPTED = "accepted"
STATUS_DUPLICATE = "duplicate"
STATUS_QUARANTINED = "quarantined"
STATUS_REJECTED = "rejected"


class ReceiptError(ValueError):
    """A receipt cannot be represented or a caller asked for something receipts never do."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def digest(payload: dict) -> str:
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


@dataclass(frozen=True)
class Plan:
    """What a person approved: one target, one commit, one proposal identity."""

    plan_digest: str
    repo: str
    commit: str
    target_id: str
    target_generation: str = ""
    account_id: str = ""
    campaign_id: str = ""
    campaign_version: int = 0
    proposal: str = ""

    def as_dict(self) -> dict:
        return {"plan_digest": self.plan_digest, "repo": self.repo, "commit": self.commit,
                "target_id": self.target_id, "target_generation": self.target_generation,
                "account_id": self.account_id, "campaign_id": self.campaign_id,
                "campaign_version": self.campaign_version, "proposal": self.proposal}


@dataclass(frozen=True)
class Receipt:
    """One observation from a trusted producer, addressed by that producer's own id."""

    kind: str
    producer: str
    external_id: str
    payload: dict = field(default_factory=dict)
    actor: str = ""
    observed_at: datetime = field(default_factory=_now)
    received_at: datetime = field(default_factory=_now)
    evidence_sha256: str = ""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ReceiptError(f"kind must be one of {', '.join(KINDS)}")
        if not self.producer or not self.external_id:
            raise ReceiptError("a receipt needs a producer and that producer's id")

    @property
    def identity(self) -> str:
        return f"{self.producer}:{self.kind}:{self.external_id}"

    @property
    def payload_digest(self) -> str:
        return digest(self.payload)

    def get(self, key: str):
        return self.payload.get(key)


def check(plan: Plan, receipt: Receipt, *, expected_artifact: str = "") -> list[str]:
    """Every way this receipt fails to describe the approved plan. Empty means it is evidence for that plan."""
    problems = []
    for key in REQUIRED[receipt.kind]:
        if receipt.get(key) in (None, ""):
            problems.append(f"missing {key}")
    if not plan.plan_digest:
        problems.append("the plan has no digest")
    if not plan.proposal:
        problems.append("the plan has no proposal identity")
    if plan.repo and receipt.get("repo") and receipt.get("repo") != plan.repo:
        problems.append("repository does not match the approved repository")
    if receipt.kind == "build" and receipt.get("commit") and receipt.get("commit") != plan.commit:
        problems.append("commit does not match the approved commit")
    if receipt.kind == "merge" and plan.commit:
        merged = str(receipt.get("merge_commit") or "")
        # A squash or merge commit legitimately starts with the approved commit; anything else is a different change.
        if merged and merged != plan.commit and not merged.startswith(plan.commit[:12]):
            problems.append("merged commit is not the approved commit")
    if receipt.kind in ("deploy", "verify"):
        if receipt.get("target_id") and receipt.get("target_id") != plan.target_id:
            problems.append("target does not match the approved target")
        if plan.target_generation and receipt.get("target_generation") not in (None, "", plan.target_generation):
            problems.append("target generation changed since approval")
        if plan.account_id and receipt.get("account_id") not in (None, "", plan.account_id):
            problems.append("account does not match the approved account")
    if receipt.kind == "deploy":
        wanted = expected_artifact or receipt.get("approved_artifact") or ""
        if wanted and receipt.get("artifact_digest") != wanted:
            problems.append("artifact does not match the built artifact")
    return problems


def satisfies(step: str, receipt_kind: str) -> bool:
    """A step is satisfied only by its own evidence; this is the guard against 'the PR merged, so it is fixed'."""
    if step not in STEP_RECEIPTS:
        raise ReceiptError(f"unknown plan step {step!r}")
    return receipt_kind in STEP_RECEIPTS[step]


def ingest(plan: Plan, receipt: Receipt, existing: dict | None = None, *, expected_artifact: str = "",
           trusted=None) -> dict:
    """Decide what to do with a receipt: append it, treat it as a replay, quarantine it, or reject it.

    `trusted` is the configured producer allow-list. A receipt from anybody else is rejected before it is compared
    with the plan, so adding a new CI system is a configuration change, not a code change.
    """
    existing = existing or {}
    if trusted is not None and receipt.producer not in set(trusted):
        reason = f"producer {receipt.producer!r} is not configured as trusted"
        return {"action": STATUS_REJECTED, "identity": receipt.identity, "payload_digest": receipt.payload_digest,
                "problems": ["untrusted producer"], "reason": reason}
    problems = check(plan, receipt, expected_artifact=expected_artifact)
    if problems:
        return {"action": STATUS_REJECTED, "identity": receipt.identity, "payload_digest": receipt.payload_digest,
                "problems": problems, "reason": "; ".join(problems)}
    prior = existing.get(receipt.identity)
    if prior is None:
        return {"action": STATUS_ACCEPTED, "identity": receipt.identity, "payload_digest": receipt.payload_digest,
                "problems": [], "reason": ""}
    if prior == receipt.payload_digest:
        return {"action": STATUS_DUPLICATE, "identity": receipt.identity, "payload_digest": receipt.payload_digest,
                "problems": [], "reason": "this receipt was already ingested with the same payload"}
    return {"action": STATUS_QUARANTINED, "identity": receipt.identity, "payload_digest": receipt.payload_digest,
            "problems": [], "reason": "the same identity arrived with a different payload"}


def reconcile(plan: Plan, chain: dict, *, existing: dict | None = None, trusted=None) -> dict:
    """Fold a chain of receipts into facts without resubmitting anything.

    `chain` maps a receipt kind to a Receipt (or None). Anything that fails the plan check, comes from an untrusted
    producer, and any missing approval or proposal identity, stays explicitly unresolved rather than being guessed.
    """
    facts, unresolved = {}, []
    for kind in KINDS:
        receipt = chain.get(kind)
        if receipt is None:
            continue
        problems = check(plan, receipt)
        if problems:
            unresolved.append({"kind": kind, "problems": problems})
            continue
        action = ingest(plan, receipt, existing, trusted=trusted)["action"]
        if action in (STATUS_ACCEPTED, STATUS_DUPLICATE):
            facts[kind] = {"identity": receipt.identity, "payload_digest": receipt.payload_digest,
                           "actor": receipt.actor, "observed_at": receipt.observed_at.isoformat(),
                           "evidence_sha256": receipt.evidence_sha256}
        else:
            unresolved.append({"kind": kind, "problems": [action]})
    steps = {step: any(satisfies(step, kind) for kind in facts) for step in STEP_RECEIPTS}
    if not plan.plan_digest:
        unresolved.append({"kind": "plan", "problems": ["no approved plan digest"]})
    if not plan.proposal:
        unresolved.append({"kind": "plan", "problems": ["no proposal identity"]})
    return {"resubmitted": False, "facts": facts, "steps": steps, "unresolved": unresolved,
            "deployed": steps["deployed"], "verified": steps["verified"]}


def rows(plan: Plan, receipt: Receipt, outcome: dict) -> list[dict]:
    """One row for the `deployment_receipts` table, whatever the outcome (rejections are evidence too)."""
    prefix = "sha256:"
    return [{
        "receipt_id": hashlib.sha256(f"{receipt.identity}\n{receipt.payload_digest}".encode()).hexdigest(),
        "identity": receipt.identity, "kind": receipt.kind, "producer": receipt.producer,
        "external_id": receipt.external_id, "status": outcome["action"], "reason": outcome.get("reason", ""),
        "plan_digest": plan.plan_digest, "proposal": plan.proposal, "campaign_id": plan.campaign_id,
        "campaign_version": plan.campaign_version, "target_id": plan.target_id,
        "target_generation": plan.target_generation, "account_id": plan.account_id,
        "repo": plan.repo, "commit": str(receipt.get("commit") or receipt.get("merge_commit") or plan.commit),
        "artifact_digest": str(receipt.get("artifact_digest") or ""),
        "deployment_revision": str(receipt.get("deployment_revision") or ""),
        "actor": receipt.actor, "payload_digest": receipt.payload_digest,
        "evidence_sha256": receipt.evidence_sha256,
        "observed_at": receipt.observed_at, "received_at": receipt.received_at,
        "payload": canonical(receipt.payload),
    }]


def evidence_ref(sha256: str) -> str:
    """Normalise an evidence id the way the rest of the desk stores it."""
    if not sha256 or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        raise ReceiptError("evidence id must be 64 lowercase hex characters")
    return f"sha256:{sha256}"