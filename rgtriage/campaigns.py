"""Versioned campaign membership and per-target progress (roadmap CE-16).

A campaign is a set of targets, not a set of finding previews. The board keeps its bounded preview; decisions and
approved actions must use the frozen membership and its digest, and a target discovered after approval can never join
that approval silently: it belongs to a new version that needs a new approval.

Nothing here talks to Iceberg. `plan`, `approve` and `progress` are pure, so the reducer can be tested without storage;
`rows` turns a membership into the rows appended to `campaigns` and `campaign_members`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

PREVIEW_LIMIT = 50
STATUS_CANDIDATE = "candidate"
STATUS_APPROVED = "approved"
TARGET_KINDS = ("finding", "workload", "target")


class CampaignError(ValueError):
    """A campaign operation would break an approval or lose members."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, order=True)
class Member:
    """One target in a campaign.

    `target_id` is the stable identity the deployment and verification evidence is bound to; the remaining identity
    fields make collisions across scopes impossible (same name, different account, both stay).
    """

    target_id: str
    finding_key: str = ""
    target_kind: str = "finding"
    account_id: str = ""
    region: str = ""
    resource_id: str = ""
    resource_generation: str = ""

    def __post_init__(self):
        if self.target_kind not in TARGET_KINDS:
            raise CampaignError(f"target_kind must be one of {', '.join(TARGET_KINDS)}")
        if not self.target_id:
            raise CampaignError("a member needs a target_id")

    def identity(self) -> dict:
        return {"target_id": self.target_id, "finding_key": self.finding_key, "target_kind": self.target_kind,
                "account_id": self.account_id, "region": self.region, "resource_id": self.resource_id,
                "resource_generation": self.resource_generation}

    def as_dict(self) -> dict:
        return dict(self.identity())


def _digest(members) -> str:
    """Order-independent digest over the identity fields only: reordering is not a new scope, a new target is."""
    ordered = sorted((member.identity() for member in members), key=lambda item: item["target_id"])
    body = json.dumps(ordered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class Membership:
    campaign_id: str
    version: int
    members: tuple
    title: str = ""
    derivation_version: str = ""
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self):
        if self.version < 1:
            raise CampaignError("membership version starts at 1")
        seen = {}
        for member in self.members:
            if member.target_id in seen and seen[member.target_id] != member:
                raise CampaignError(f"target {member.target_id} appears twice with different identities")
            seen[member.target_id] = member
        object.__setattr__(self, "members", tuple(sorted(seen.values())))

    @property
    def digest(self) -> str:
        return _digest(self.members)

    @property
    def count(self) -> int:
        return len(self.members)

    def targets(self) -> set:
        return {member.target_id for member in self.members}

    def preview(self, limit: int = PREVIEW_LIMIT) -> dict:
        """Bounded board preview; the counts are authoritative, the list is not."""
        if limit < 1:
            raise CampaignError("preview limit must be at least 1")
        shown = self.members[:limit]
        return {"campaign_id": self.campaign_id, "version": self.version, "member_count": self.count,
                "membership_digest": self.digest, "preview_count": len(shown), "truncated": self.count > len(shown),
                "members": [member.as_dict() for member in shown]}

    def next_version(self, members, title: str | None = None) -> "Membership":
        """A changed scope is a new version; the old one stays readable for anyone holding its digest."""
        return Membership(self.campaign_id, self.version + 1, tuple(members),
                          title=self.title if title is None else title,
                          derivation_version=self.derivation_version)

    def added_since(self, other: "Membership") -> set:
        return self.targets() - other.targets()


@dataclass(frozen=True)
class Approval:
    campaign_id: str
    version: int
    digest: str
    member_count: int
    by: str
    at: datetime = field(default_factory=_now)

    def as_dict(self) -> dict:
        return {"campaign_id": self.campaign_id, "version": self.version, "digest": self.digest,
                "member_count": self.member_count, "by": self.by, "at": self.at.isoformat()}


def plan(campaign_id: str, members, *, title: str = "", derivation_version: str = "") -> Membership:
    return Membership(campaign_id, 1, tuple(members), title=title, derivation_version=derivation_version)


def approve(membership: Membership, by: str, at: datetime | None = None) -> Approval:
    if not by:
        raise CampaignError("an approval needs a person")
    return Approval(membership.campaign_id, membership.version, membership.digest, membership.count, by,
                    at or _now())


def check_approval(approval: Approval, membership: Membership) -> None:
    """Fail closed: a digest, version or count that does not match is not this approval."""
    problems = []
    if approval.campaign_id != membership.campaign_id:
        problems.append("campaign")
    if approval.version != membership.version:
        problems.append("version")
    if approval.digest != membership.digest:
        problems.append("digest")
    if approval.member_count != membership.count:
        problems.append("member count")
    if problems:
        raise CampaignError(f"approval does not match the current membership ({', '.join(problems)}); "
                            "re-approve the new version")


def progress(membership: Membership, applied=(), verified=()) -> dict:
    """Per-target progress from deployment and verification evidence, never from a campaign-level state.

    A target counts as verified only when it was also applied: a proof for something that was never deployed does not
    reduce the open work, and is reported separately instead of being hidden.
    """
    targets = membership.targets()
    applied_ids = {target for target in applied if target in targets}
    verified_ids = {target for target in verified if target in targets}
    verified_and_applied = verified_ids & applied_ids
    return {
        "campaign_id": membership.campaign_id, "version": membership.version, "targets": membership.count,
        "verified": len(verified_and_applied),
        "applied_pending_verification": len(applied_ids - verified_and_applied),
        "open": len(targets - applied_ids),
        "verified_not_applied": len(verified_ids - applied_ids),
        "membership_digest": membership.digest,
    }


def rows(membership: Membership, *, state_by_target: dict | None = None, evidence_by_target: dict | None = None,
         approval: Approval | None = None) -> dict:
    """Rows for `campaigns` (one) and `campaign_members` (one per target, stable ordinal)."""
    states = state_by_target or {}
    evidence = evidence_by_target or {}
    created = membership.created_at.astimezone(timezone.utc)
    campaign = {
        "campaign_id": membership.campaign_id, "version": membership.version, "title": membership.title,
        "status": STATUS_APPROVED if approval else STATUS_CANDIDATE,
        "membership_digest": membership.digest, "member_count": membership.count,
        "derivation_version": membership.derivation_version,
        "approved_by": approval.by if approval else "", "approved_at": approval.at if approval else None,
        "approval_digest": approval.digest if approval else "", "created_at": created, "updated_at": _now(),
    }
    members = []
    for ordinal, member in enumerate(membership.members, start=1):
        entry = member.as_dict()
        entry.update({"campaign_id": membership.campaign_id, "version": membership.version, "ordinal": ordinal,
                      "state": states.get(member.target_id, "open"), "evidence_sha256": evidence.get(member.target_id, ""),
                      "added_at": created})
        members.append(entry)
    return {"campaigns": [campaign], "campaign_members": members}


def page(members, *, after: int = 0, limit: int = 100) -> dict:
    """Stable pagination by ordinal: a cursor is the last ordinal returned, so duplicates and retries cannot drop or
    double-count members."""
    if limit < 1:
        raise CampaignError("limit must be at least 1")
    ordered = sorted(members, key=lambda row: int(row["ordinal"]))
    remaining = [row for row in ordered if int(row["ordinal"]) > int(after)]
    shown = remaining[:limit]
    return {"members": shown, "next_cursor": shown[-1]["ordinal"] if shown else None,
            "has_more": len(remaining) > len(shown), "returned": len(shown),
            "total_members": len(ordered)}