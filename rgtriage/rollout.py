"""Evidence-backed shared-cause campaigns and partial-rollout reconciliation (roadmap CE-21).

One base image can carry a vulnerable package into many workloads, but patching that image proves nothing about a
workload. This module turns proven lineage (CE-20) into a *candidate* campaign, states the exact rebuild/test/deploy/
verify plan a person approves, and reconciles per-target evidence afterwards.

Three properties are load-bearing:

- A member is admitted only when its runtime image digest *is* the campaign image. A finding that merely mentions the
  same package name is excluded with a reason a person can read, never silently absorbed.
- Nothing here closes a target. Only a per-target proof does, and a proof for a target that was never deployed is
  reported as `verified_not_applied` instead of reducing the open work.
- Rollback and a new workload occurrence reopen the target without erasing what already passed; a target that is not in
  the approved membership is ignored and needs a new version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import campaigns, lineage

DERIVATION = "ce.shared-cause-campaign/v1"
STEPS = ("rebuild", "test", "deploy", "verify")
STEP_RECEIPT = {"rebuild": "build", "test": "build", "deploy": "deploy", "verify": "verify"}

STATE_OPEN = "open"
STATE_APPLIED = "applied"
STATE_VERIFIED = "verified"

EX_INVENTORY_MISSING = "runtime inventory missing"
EX_IMAGE_UNPROVEN = "image is not an immutable digest"
EX_OTHER_IMAGE = "runs a different image digest"
EX_NO_FINDING = "no finding on this workload needs this fix"
EX_NAME_ONLY = "package matched by name only"
EX_OTHER_LAYER = "package came from the application layer"
EX_ACCOUNT_UNCOVERED = "account was not inspected"

DEFAULT_STOP_CONDITIONS = (
    "a target reports an artifact digest that is not the approved one",
    "any per-target proof fails, errors or is inconclusive",
    "a target appears that is not in the approved membership",
    "the measured error rate exceeds the pre-rollout baseline",
)


class RolloutError(ValueError):
    """A campaign, plan or reconciliation would claim more than the evidence supports."""


def _at(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    raise RolloutError("an event needs a datetime")


@dataclass(frozen=True)
class InventoryEntry:
    """What a runtime inventory says one workload runs, and which findings are open on it."""

    workload_id: str
    revision: str
    account_id: str
    region: str
    image: str
    findings: tuple = ()
    package: str = ""
    package_name: str = ""
    origin: str = ""
    resource_generation: str = ""
    observed: bool = True
    resource_type: str = "ecs-service"

    @property
    def target_id(self) -> str:
        """Scoped identity: the same workload name in two accounts is two targets."""
        return f"{self.account_id or '-'}:{self.workload_id}@{self.revision}"

    def member(self, finding_key: str = "") -> campaigns.Member:
        return campaigns.Member(target_id=self.target_id, finding_key=finding_key, target_kind="workload",
                                account_id=self.account_id, region=self.region, resource_id=self.workload_id,
                                resource_generation=self.resource_generation or self.revision)


@dataclass(frozen=True)
class Candidate:
    """A candidate campaign plus every workload that was considered and why it was left out."""

    campaign_id: str
    membership: campaigns.Membership
    artifact: dict
    exclusions: tuple = ()
    derivation_version: str = DERIVATION

    @property
    def excluded_count(self) -> int:
        return len(self.exclusions)

    def as_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "derivation_version": self.derivation_version,
                "artifact": dict(self.artifact), "membership": self.membership.preview(),
                "exclusions": [dict(item) for item in self.exclusions]}


def _artifact(base_image: str, package: str) -> dict:
    return {"kind": "image", "digest": base_image, "package": package, "immutable": True}


def derive_campaign(campaign_id: str, *, base_image: str, package: str, inventory,
                    covered_accounts=None, known_packages=None) -> Candidate:
    """The candidate campaign for one image/package pair, with an inspectable reason for every exclusion.

    `known_packages` maps a package *name* to the purl that was actually observed, so a finding that matched by name
    cannot become a member; `None` means the caller did not supply name information and the check is skipped.
    """
    if not campaign_id:
        raise RolloutError("a candidate campaign needs an id")
    base = str(base_image or "")
    proven = base.startswith("sha256:") and len(base) == 71
    wanted = lineage.Package(purl=package) if package.startswith(("pkg:", "cpe:")) else None
    if wanted is None:
        raise RolloutError("a campaign is about a package with a purl or cpe identity")
    covered = set(covered_accounts) if covered_accounts is not None else None
    members, exclusions = [], []
    for entry in inventory:
        if not proven:
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_IMAGE_UNPROVEN,
                               "detail": "the campaign image has no sha256: digest, so no shared cause is proven"})
            continue
        if not entry.observed:
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_INVENTORY_MISSING,
                               "detail": "no runtime inventory receipt says what this workload runs"})
            continue
        if not str(entry.image or "").startswith("sha256:"):
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_IMAGE_UNPROVEN,
                               "detail": f"the workload reported {str(entry.image)[:40]!r}, which is a tag"})
            continue
        if entry.image != base:
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_OTHER_IMAGE,
                               "detail": f"runs {entry.image[:24]}…, the campaign rebuilds {base[:24]}…"})
            continue
        if covered is not None and entry.account_id not in covered:
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_ACCOUNT_UNCOVERED, "detail": f"account {entry.account_id} was not read"})
            continue
        if entry.origin == "application":
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_OTHER_LAYER,
                               "detail": "rebuilding the base image does not replace an application-layer package"})
            continue
        if not entry.findings:
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_NO_FINDING, "detail": "the package is present but no open finding needs it"})
            continue
        if known_packages and entry.package_name:
            observed = known_packages.get(entry.package_name)
            if observed and observed != package and entry.package and entry.package != package:
                exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                                   "reason": EX_NAME_ONLY,
                                   "detail": f"{entry.package_name} resolves to {observed}, not {package}"})
                continue
        if entry.package and entry.package != package:
            exclusions.append({"target_id": entry.target_id, "workload_id": entry.workload_id,
                               "reason": EX_NAME_ONLY, "detail": f"the installed package is {entry.package}"})
            continue
        members.append(entry.member(finding_key=str(entry.findings[0])))
    membership = campaigns.plan(campaign_id, members, title=f"Rebuild {base[:19]}… for {package}",
                                derivation_version=DERIVATION)
    return Candidate(campaign_id, membership, _artifact(base, package), tuple(exclusions), DERIVATION)


@dataclass(frozen=True)
class RolloutPlan:
    """What a person approves: one immutable artifact, one frozen membership, explicit stops and per-target proof."""

    campaign_id: str
    version: int
    membership_digest: str
    member_count: int
    artifact: dict
    proof: dict
    steps: tuple = STEPS
    stop_conditions: tuple = DEFAULT_STOP_CONDITIONS
    derivation_version: str = DERIVATION

    def as_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "version": self.version,
                "membership_digest": self.membership_digest, "member_count": self.member_count,
                "artifact": dict(self.artifact), "steps": list(self.steps),
                "required_receipts": [STEP_RECEIPT[step] for step in self.steps],
                "required_per_target_proof": dict(self.proof),
                "stop_conditions": list(self.stop_conditions),
                "derivation_version": self.derivation_version,
                "closes_all_members_on_patch": False}


def plan_for(candidate: Candidate, *, predicate_id: str, predicate_version: str, rule: str,
             stop_conditions=None) -> RolloutPlan:
    """The bounded plan. Nothing in it can close a target: only a per-target proof can."""
    if not predicate_id or not predicate_version or not rule:
        raise RolloutError("a plan needs an approved proof predicate (id, version and rule)")
    if not candidate.membership.count:
        raise RolloutError("a campaign with no proven member cannot be planned")
    digest = str(candidate.artifact.get("digest") or "")
    if not digest.startswith("sha256:"):
        raise RolloutError("the plan's artifact must be an immutable image digest")
    proof = {"predicate_id": predicate_id, "predicate_version": predicate_version, "rule": rule,
             "bound_to": ["target_id", "resource_generation", "artifact_digest"],
             "requires_evidence": True, "closes_all_members": False}
    return RolloutPlan(candidate.campaign_id, candidate.membership.version, candidate.membership.digest,
                       candidate.membership.count, dict(candidate.artifact), proof, STEPS,
                       tuple(stop_conditions or DEFAULT_STOP_CONDITIONS), candidate.derivation_version)


@dataclass(frozen=True)
class TargetEvent:
    """One thing that happened to one target. Events are evidence, not instructions."""

    target_id: str
    kind: str
    at: datetime
    artifact_digest: str = ""
    passed: bool = False
    evidence_sha256: str = ""
    resource_generation: str = ""
    reason: str = ""

    def __post_init__(self):
        if self.kind not in ("deploy", "proof", "rollback", "recurrence"):
            raise RolloutError("event kind must be deploy, proof, rollback or recurrence")
        object.__setattr__(self, "at", _at(self.at))
        if self.kind == "proof" and self.passed and not self.evidence_sha256:
            raise RolloutError("a passing proof needs retained evidence")


def _counts(states: dict, membership: campaigns.Membership) -> dict:
    """Four disjoint buckets: a proof for an undeployed target is its own bucket, not open and not verified."""
    targets = membership.targets()
    verified = sum(1 for target in targets if states.get(target) == STATE_VERIFIED)
    applied = sum(1 for target in targets if states.get(target) == STATE_APPLIED)
    not_applied = sum(1 for target in targets if states.get(target) == "verified_not_applied")
    open_targets = sum(1 for target in targets if states.get(target) == STATE_OPEN)
    return {"members": membership.count, "verified": verified, "applied_pending_verification": applied,
            "open": open_targets, "verified_not_applied": not_applied}


def reconcile(membership: campaigns.Membership, events, *, artifact_digest: str,
              deployed=(), verified=()) -> dict:
    """Fold per-target evidence into states. `deployed` and `verified` are the legacy progress sets, not proof.

    Every event is reported with its outcome, so a rejected deployment or an out-of-scope target stays visible instead
    of being dropped. History per target is appended, never replaced, so a rollback does not erase a past success.
    """
    if not str(artifact_digest or "").startswith("sha256:"):
        raise RolloutError("reconciliation needs the approved immutable artifact digest")
    targets = membership.targets()
    ordered = sorted(events, key=lambda event: (event.at, event.target_id, event.kind))
    states = {target: STATE_OPEN for target in targets}
    history: dict[str, list] = {target: [] for target in targets}
    reported, recurrences = [], []

    def note(event, outcome: str, reason: str = "") -> None:
        reported.append({"target_id": event.target_id, "kind": event.kind, "at": event.at.isoformat(),
                         "artifact_digest": event.artifact_digest, "outcome": outcome, "reason": reason,
                         "evidence_sha256": event.evidence_sha256})
        if event.target_id in history:
            history[event.target_id].append({"kind": event.kind, "at": event.at.isoformat(),
                                             "artifact_digest": event.artifact_digest, "outcome": outcome,
                                             "reason": reason, "evidence_sha256": event.evidence_sha256})

    for event in ordered:
        if event.target_id not in targets:
            note(event, "ignored", "target is not in the approved membership; a new member needs a new version")
            continue
        current = states[event.target_id]
        if event.kind == "deploy":
            if event.artifact_digest != artifact_digest:
                note(event, "rejected", "artifact is not the approved one (autoscaling an old artifact)")
                continue
            if current == STATE_VERIFIED:
                states[event.target_id] = STATE_APPLIED
                note(event, "accepted", "a new deployment supersedes the earlier proof")
            else:
                states[event.target_id] = STATE_APPLIED
                note(event, "accepted")
        elif event.kind == "proof":
            if not event.passed:
                note(event, "rejected", "the proof did not pass")
                continue
            if current == STATE_APPLIED:
                states[event.target_id] = STATE_VERIFIED
                note(event, "accepted", "target-bound proof on a deployed artifact")
            elif current == STATE_VERIFIED:
                note(event, "duplicate", "the target was already verified")
            else:
                states[event.target_id] = "verified_not_applied"
                note(event, "rejected", "verified without an approved deployment; counted separately, never as verified")
        else:
            reason = event.reason or ("rollback" if event.kind == "rollback" else "the finding occurred again")
            states[event.target_id] = STATE_OPEN
            recurrences.append({"target_id": event.target_id, "at": event.at.isoformat(), "kind": event.kind,
                                "reason": reason})
            note(event, "reopened", reason)

    # Legacy progress sets can only raise the floor: they never promote a target past a proof.
    applied_ids = {target for target in deployed if target in targets}
    proof_ids = {target for target in verified if target in targets}
    for target in applied_ids:
        if states[target] == STATE_OPEN:
            states[target] = STATE_APPLIED
    for target in proof_ids - applied_ids:
        if states[target] == STATE_OPEN:
            states[target] = "verified_not_applied"
    return {"campaign_id": membership.campaign_id, "version": membership.version,
            "membership_digest": membership.digest, "artifact_digest": artifact_digest,
            "states": states, "counts": _counts(states, membership), "events": reported,
            "history": history, "recurrences": recurrences,
            "closes_all_members_on_patch": False}


def state_rows(result: dict, membership: campaigns.Membership, *, evidence_by_target=None) -> dict:
    """Rows for `campaigns` and `campaign_members` from one reconciliation, plus the approval the caller holds."""
    evidence = dict(evidence_by_target or {})
    for target, entries in (result.get("history") or {}).items():
        for entry in reversed(entries):
            if entry.get("kind") == "proof" and entry.get("outcome") == "accepted":
                evidence[target] = entry.get("evidence_sha256") or ""
                break
    states = {target: state for target, state in (result.get("states") or {}).items()}
    return campaigns.rows(membership, state_by_target=states, evidence_by_target=evidence)