"""Typed, time-aware relationship assertions (roadmap CE-19).

The OKF graph links knowledge concepts. This is the operational graph: entities that exist in AWS and in the
installation (an image digest, a package, a workload revision, a finding, a plan, a deployment, an owner), and
assertions about them that carry their evidence, their validity interval and how they came to be known.

Three rules make it usable for root cause instead of decoration:

- An authoritative edge is either `observed` with retained evidence, or `derived` by an approved deterministic
  derivation with a version. Anything else is a `hypothesis`, is stored, and can never authorize closure or execution.
- Identity is scoped. Two workloads called `api` in different accounts, or two image tags that now point at different
  digests, are different entities; only digests, ARNs and scoped ids are identities.
- History is append-only. A retraction or a correction is a new row that supersedes an old one, so what was believed
  before stays readable, and an interrupted rebuild leaves the previous complete graph in place.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

ENTITY_KINDS = ("image", "package", "workload", "finding", "plan", "deployment", "owner", "resource")
STATUSES = ("observed", "derived", "hypothesis", "retracted")
AUTHORITATIVE = ("observed", "derived")


class RelationshipError(ValueError):
    """An assertion cannot be stored as given."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha(*parts) -> str:
    return hashlib.sha256(canonical(list(parts)).encode()).hexdigest()


@dataclass(frozen=True)
class Entity:
    """A scoped identity. `scope` is canonicalised into the key, so equal names in different scopes never merge."""

    kind: str
    identity: str
    scope: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.kind not in ENTITY_KINDS:
            raise RelationshipError(f"entity kind must be one of {', '.join(ENTITY_KINDS)}")
        if not self.identity:
            raise RelationshipError("an entity needs an identity")

    @property
    def key(self) -> str:
        return _sha(self.kind, self.identity, self.scope)

    def as_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "identity": self.identity, "scope": self.scope}


def image_entity(digest: str, *, platform: str = "", registry: str = "") -> Entity:
    """An image is its digest. A tag is not an identity: the same tag can point somewhere else tomorrow."""
    if not digest.startswith("sha256:") or len(digest) != 71:
        raise RelationshipError("an image entity needs an immutable sha256: digest, not a tag")
    return Entity("image", digest, {"platform": platform, "registry": registry})


def package_entity(purl: str) -> Entity:
    if not purl.startswith(("pkg:", "cpe:")):
        raise RelationshipError("a package entity needs a purl or cpe identity")
    return Entity("package", purl, {})


def scoped_entity(kind: str, identity: str, *, account_id: str = "", region: str = "", resource_type: str = "") -> Entity:
    return Entity(kind, identity, {"account_id": account_id, "region": region, "resource_type": resource_type})


@dataclass(frozen=True)
class Assertion:
    subject: Entity
    predicate: str
    object: Entity
    status: str = "observed"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    recorded_at: datetime = field(default_factory=_now)
    evidence: tuple = ()
    derivation: str = ""
    supersedes: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise RelationshipError(f"status must be one of {', '.join(STATUSES)}")
        if not self.predicate:
            raise RelationshipError("an assertion needs a predicate")
        if self.status == "observed" and not self.evidence:
            raise RelationshipError("an observed relationship needs retained evidence")
        if self.status == "derived" and not self.derivation:
            raise RelationshipError("a derived relationship needs a derivation version")
        if self.status == "retracted" and not self.supersedes:
            raise RelationshipError("a retraction must name the assertion it supersedes")

    @property
    def id(self) -> str:
        """Deterministic: the same fact from the same derivation is the same row, however often it is delivered."""
        return _sha(self.subject.key, self.predicate, self.object.key, _iso(self.valid_from), self.derivation,
                    self.supersedes)

    @property
    def authoritative(self) -> bool:
        return self.status in AUTHORITATIVE

    def may_authorize(self) -> bool:
        """Only authoritative edges can close a finding or permit execution. Hypotheses never can."""
        return self.authoritative

    def current_at(self, when: datetime | None = None) -> bool:
        when = when or _now()
        if self.valid_from and when < self.valid_from:
            return False
        if self.valid_to and when >= self.valid_to:
            return False
        return True

    def as_dict(self) -> dict:
        return {"subject": self.subject.as_dict(), "predicate": self.predicate, "object": self.object.as_dict(),
                "status": self.status, "valid_from": _iso(self.valid_from), "valid_to": _iso(self.valid_to),
                "recorded_at": _iso(self.recorded_at), "evidence": list(self.evidence),
                "derivation": self.derivation, "authoritative": self.authoritative}


def retract(prior: Assertion, *, evidence=(), derivation: str = "", recorded_at: datetime | None = None) -> Assertion:
    """History is preserved: the old row stays, and this one supersedes it."""
    return replace(prior, status="retracted", supersedes=prior.id, evidence=tuple(evidence),
                   recorded_at=recorded_at or _now(), derivation=derivation or prior.derivation)


def superseded(assertions) -> set:
    return {assertion.supersedes for assertion in assertions if assertion.supersedes}


def current(assertions, *, as_of: datetime | None = None) -> list:
    """The latest authoritative, currently valid assertion per (subject, predicate, object)."""
    as_of = as_of or _now()
    gone = superseded(assertions)
    latest = {}
    for assertion in assertions:
        if assertion.id in gone or not assertion.authoritative or not assertion.current_at(as_of):
            continue
        key = (assertion.subject.key, assertion.predicate, assertion.object.key)
        if key not in latest or assertion.recorded_at > latest[key].recorded_at:
            latest[key] = assertion
    return sorted(latest.values(), key=lambda item: (item.subject.key, item.predicate, item.object.key))


def new_rows(assertions, existing_ids=()) -> list:
    """Append-only writes: an assertion already stored with the same id is not written twice."""
    seen = set(existing_ids)
    rows = []
    for assertion in assertions:
        if assertion.id in seen:
            continue
        seen.add(assertion.id)
        rows.append(row(assertion))
    return rows


def row(assertion: Assertion) -> dict:
    return {
        "assertion_id": assertion.id,
        "subject_key": assertion.subject.key, "subject_kind": assertion.subject.kind,
        "subject_scope": canonical(assertion.subject.scope), "subject_identity": assertion.subject.identity,
        "predicate": assertion.predicate,
        "object_key": assertion.object.key, "object_kind": assertion.object.kind,
        "object_scope": canonical(assertion.object.scope), "object_identity": assertion.object.identity,
        "status": assertion.status, "valid_from": assertion.valid_from, "valid_to": assertion.valid_to,
        "recorded_at": assertion.recorded_at, "evidence": canonical(list(assertion.evidence)),
        "derivation": assertion.derivation, "supersedes": assertion.supersedes,
    }


# ---------------------------------------------------------------- deterministic derivations

DERIVATION_IMAGE_PACKAGE = "ce.image-contains-package/v1"
DERIVATION_WORKLOAD_IMAGE = "ce.workload-runs-image/v1"


def derive_image_packages(image: Entity, packages, *, evidence=()) -> list:
    """An approved derivation: this digest contains these packages. Same inputs, same assertion ids."""
    return [Assertion(image, "contains", package, status="derived", derivation=DERIVATION_IMAGE_PACKAGE,
                      evidence=tuple(evidence)) for package in packages]


def derive_workload_image(workload: Entity, image: Entity, *, evidence=()) -> Assertion:
    return Assertion(workload, "runs", image, status="derived", derivation=DERIVATION_WORKLOAD_IMAGE,
                     evidence=tuple(evidence))


@dataclass(frozen=True)
class Rebuild:
    """A local rebuild cursor: which derivation version produced the active graph, and up to which event."""

    version: str
    last_event: str = ""
    complete: bool = True
    built_at: datetime = field(default_factory=_now)


def rebuild(previous: Rebuild | None, derived, *, version: str, last_event: str, complete: bool) -> tuple:
    """Return (active assertions, cursor). An interrupted rebuild never replaces a complete graph."""
    if not complete and previous is not None and previous.complete:
        return [], previous
    return list(derived), Rebuild(version=version, last_event=last_event, complete=complete)


def graph_lag(cursor: Rebuild | None, latest_event: str, latest_at: datetime | None = None,
             *, now: datetime | None = None) -> dict:
    """How far the graph is behind, reported separately from operational state."""
    return {"graph_version": cursor.version if cursor else "", "graph_complete": bool(cursor and cursor.complete),
            "graph_last_event": cursor.last_event if cursor else "",
            "latest_event": latest_event,
            "behind": bool(cursor is None or cursor.last_event != latest_event),
            "lag_seconds": round(((now or _now()) - latest_at).total_seconds(), 3) if latest_at else None}


def explain(assertion: Assertion) -> dict:
    """Why this edge is believed: retained evidence, or the approved derivation that produced it."""
    return {"assertion_id": assertion.id, "status": assertion.status,
            "authoritative": assertion.authoritative, "may_authorize": assertion.may_authorize(),
            "evidence": list(assertion.evidence), "derivation": assertion.derivation,
            "recorded_at": _iso(assertion.recorded_at),
            "reason": ("observed with retained evidence" if assertion.status == "observed"
                       else f"derived by {assertion.derivation}" if assertion.status == "derived"
                       else "hypothesis or retracted: not authoritative")}