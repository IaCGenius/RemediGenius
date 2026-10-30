"""One approved, attested computation: campaign counts (roadmap CE-22).

A model may request a number; it may not invent one. `campaign_verification_summary` is the single computation this
release runs through the scoped data service:

- the contract is a reviewed, versioned constant (typed parameters, an output shape and the reducer name);
- the reducer is a pure function over campaign membership rows read from a pinned table snapshot;
- execution binds the code digest, the contract digest, the parameter values, the input snapshot, the knowledge
  version and the output digest into one receipt;
- `attest()` re-derives the output from the retained rows and compares everything, so changed code, a changed contract,
  another membership version, an incomplete evidence set, an out-of-scope row or a modified output all fail closed;
- a failed attestation is a retained result of its own (`result = failed_attestation`), never a count.

The model can choose only the parameters listed in `PARAMETERS`, and can explain a receipt that attested. Changing the
computation means editing this module, bumping `COMPUTATION_VERSION` and re-pinning `APPROVED_CODE_DIGEST` in review.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

COMPUTATION = "campaign_verification_summary"
COMPUTATION_VERSION = "1"
KNOWLEDGE_VERSION = "ce.attest/1"
# Reviewed pin of the reducer source. `tests/test_attest.py` fails when the source changes without this pin changing.
APPROVED_CODE_DIGEST = "fbd40d325aff59d955fa9d4e0b03d3ae26b8850393961ad89e7a79cde174ae2d"

PARAMETERS = {
    "campaign_id": "string",
    "version": "integer",
    "installation_id": "string",
    "as_of": "timestamp",
    "evidence_set": "sha256",
}
REQUIRED_PARAMETERS = ("campaign_id", "version", "installation_id")
OUTPUT_FIELDS = ("campaign_id", "version", "installation_id", "membership_digest", "member_count", "verified",
                 "applied_pending_verification", "open", "verified_not_applied", "evidence_complete", "as_of",
                 "evidence_set", "unsupported")
RESULT_AUTHORITATIVE = "authoritative"
RESULT_FAILED = "failed_attestation"
MAX_UNSUPPORTED = 50

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class AttestationError(ValueError):
    """A parameter or a contract is not one the desk approved."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Contract:
    """The reviewed shape of one computation. Changing any field is a new version, never an edit."""

    computation: str
    version: str
    parameters: dict
    required: tuple
    output: tuple
    reducer: str

    def digest(self) -> str:
        return _sha(canonical([self.computation, self.version, self.parameters, list(self.required),
                               list(self.output), self.reducer]))


APPROVED = Contract(COMPUTATION, COMPUTATION_VERSION, dict(PARAMETERS), REQUIRED_PARAMETERS, OUTPUT_FIELDS, "_reduce")


def code_digest() -> str:
    """The identity of the code that computes the number: the reducer source, normalised for line endings."""
    source = inspect.getsource(_reduce).replace("\r\n", "\n")
    return _sha(canonical([COMPUTATION, COMPUTATION_VERSION, list(OUTPUT_FIELDS), source]))


def _check_params(params: dict) -> dict:
    if not isinstance(params, dict):
        raise AttestationError("parameters must be an object")
    unknown = set(params) - set(PARAMETERS)
    if unknown:
        raise AttestationError(f"this computation does not accept {', '.join(sorted(unknown))}")
    for name in REQUIRED_PARAMETERS:
        if params.get(name) in (None, ""):
            raise AttestationError(f"{name} is required")
    if not isinstance(params.get("version"), int) or isinstance(params.get("version"), bool):
        raise AttestationError("version must be an integer")
    if params["version"] < 1:
        raise AttestationError("version starts at 1")
    evidence = str(params.get("evidence_set") or "")
    if evidence and not _HEX64.match(evidence):
        raise AttestationError("evidence_set must be a sha256 hex digest")
    return {"campaign_id": str(params["campaign_id"]), "version": int(params["version"]),
            "installation_id": str(params["installation_id"]), "as_of": str(params.get("as_of") or ""),
            "evidence_set": evidence}


def _at(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AttestationError("as_of must be an ISO date or timestamp") from exc
    return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)).isoformat()


def _reduce(rows, params):
    """The reviewed reducer: pure, deterministic and total over the membership rows it is given.

    A verified row without retained evidence is not verified: it lands in `unsupported`, counts as applied-pending-proof
    and makes `evidence_complete` false, so the number can never quietly include an unevidenced claim.
    """
    wanted_campaign, wanted_version = params["campaign_id"], int(params["version"])
    members = [row for row in rows or []
               if str(row.get("campaign_id")) == wanted_campaign and int(row.get("version") or 0) == wanted_version]
    verified, applied, open_targets, not_applied, unsupported = [], [], [], [], []
    for row in sorted(members, key=lambda item: int(item.get("ordinal") or 0)):
        target = str(row.get("target_id") or "")
        state = str(row.get("state") or "open")
        evidence = str(row.get("evidence_sha256") or "")
        if state == "verified" and evidence:
            verified.append(target)
        elif state == "verified":
            applied.append(target)
            unsupported.append({"target_id": target, "reason": "verified without retained evidence"})
        elif state == "applied":
            applied.append(target)
        elif state == "verified_not_applied":
            not_applied.append(target)
        elif state == "open":
            open_targets.append(target)
        else:
            unsupported.append({"target_id": target, "reason": f"state {state!r} is not a reconciliation state"})
            open_targets.append(target)
    identities = sorted(({"target_id": str(row.get("target_id") or ""),
                          "finding_key": str(row.get("finding_key") or ""),
                          "target_kind": str(row.get("target_kind") or "finding"),
                          "account_id": str(row.get("account_id") or ""),
                          "region": str(row.get("region") or ""),
                          "resource_id": str(row.get("resource_id") or ""),
                          "resource_generation": str(row.get("resource_generation") or "")} for row in members),
                        key=lambda item: item["target_id"])
    return {
        "campaign_id": wanted_campaign, "version": wanted_version,
        "installation_id": params["installation_id"],
        "membership_digest": _sha(canonical(identities)), "member_count": len(members),
        "verified": len(verified), "applied_pending_verification": len(applied), "open": len(set(open_targets)),
        "verified_not_applied": len(not_applied), "evidence_complete": not unsupported,
        "as_of": params.get("as_of") or "", "evidence_set": params.get("evidence_set") or "",
        "unsupported": unsupported[:MAX_UNSUPPORTED],
    }


@dataclass(frozen=True)
class Execution:
    """One run of the approved computation over one pinned input snapshot."""

    params: dict
    snapshot_id: int
    output: dict
    contract_digest: str = field(default_factory=lambda: APPROVED.digest())
    code_digest: str = field(default_factory=code_digest)
    computation: str = COMPUTATION
    computation_version: str = COMPUTATION_VERSION
    knowledge_version: str = KNOWLEDGE_VERSION
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def output_digest(self) -> str:
        return _sha(canonical(self.output))

    @property
    def receipt_id(self) -> str:
        return _sha(canonical([self.computation, self.computation_version, self.contract_digest, self.code_digest,
                               self.params, self.snapshot_id, self.output_digest]))

    def as_dict(self) -> dict:
        return {"computation": self.computation, "computation_version": self.computation_version,
                "contract_digest": self.contract_digest, "code_digest": self.code_digest,
                "params": dict(self.params), "snapshot_id": self.snapshot_id,
                "knowledge_version": self.knowledge_version, "output": dict(self.output),
                "output_digest": self.output_digest, "receipt_id": self.receipt_id}


def params(**kwargs) -> dict:
    """Validate what a caller (a person or the model) may pass. Unknown keys are refused, not ignored."""
    checked = _check_params(dict(kwargs))
    checked["as_of"] = _at(checked["as_of"])
    return checked


def execute(rows, *, params, snapshot_id, contract: Contract = APPROVED,
            knowledge_version: str = KNOWLEDGE_VERSION) -> Execution:
    """Run the pinned reducer. The caller supplies the rows from one snapshot; nothing is read here."""
    if contract.digest() != APPROVED.digest():
        raise AttestationError("only the approved contract can be executed; version it instead")
    if snapshot_id is None:
        raise AttestationError("a computation needs a pinned input snapshot")
    output = _reduce(rows, params)
    return Execution(params=dict(params), snapshot_id=int(snapshot_id), output=output,
                     knowledge_version=knowledge_version)


def _scopes(rows, params, accounts=None) -> list[str]:
    problems = []
    for row in rows:
        if str(row.get("campaign_id")) != params["campaign_id"] or int(row.get("version") or 0) != params["version"]:
            problems.append("a row belongs to another campaign or membership version")
            break
    if accounts is not None:
        allowed = set(accounts)
        for row in rows:
            if row.get("account_id") and str(row["account_id"]) not in allowed:
                problems.append(f"account {str(row['account_id'])[:12]} is not in the approved scope")
                break
    return problems


def attest(execution: Execution, *, retained_rows, approved_params=None, accounts=None,
           snapshot_id=None, contract: Contract = APPROVED, code=None) -> dict:
    """Re-derive the answer from the retained inputs and report every binding that does not hold."""
    problems = []
    if execution.contract_digest != contract.digest():
        problems.append("the computation contract changed since the receipt was produced")
    expected_code = code if code is not None else APPROVED_CODE_DIGEST
    if execution.code_digest != expected_code:
        problems.append("the computation code changed since the receipt was produced")
    if snapshot_id is not None and int(snapshot_id) != int(execution.snapshot_id):
        problems.append("the input snapshot is not the pinned one")
    try:
        checked = _check_params(execution.params)
    except AttestationError as exc:
        problems.append(f"the recorded parameters are not allowed: {exc}")
        checked = None
    if checked is not None:
        if approved_params is not None and checked != dict(approved_params):
            problems.append("the parameters differ from the approved parameters")
        retained = list(retained_rows or [])
        problems.extend(_scopes(retained, checked, accounts))
        recomputed = _reduce(retained, checked)
        if recomputed != execution.output:
            problems.append("the output does not match the retained inputs")
        if _sha(canonical(recomputed)) != execution.output_digest:
            problems.append("the recorded output digest does not match the output")
        if not recomputed["evidence_complete"]:
            problems.append("the evidence set is incomplete")
        if recomputed["member_count"] and recomputed["verified"] and not checked["evidence_set"]:
            problems.append("the evidence set is not pinned")
        if not retained:
            problems.append("no retained inputs were supplied")
    result = RESULT_AUTHORITATIVE if not problems else RESULT_FAILED
    return {"attested": not problems, "result": result, "problems": problems,
            "reason": "; ".join(problems) if problems else "re-derived from the retained inputs",
            "authoritative": not problems,
            "counts": {key: execution.output.get(key) for key in ("verified", "applied_pending_verification", "open",
                                                                  "verified_not_applied", "member_count")},
            "receipt_id": execution.receipt_id}


def receipt_row(execution: Execution, verdict: dict, *, installation_id: str = "", recorded_at=None) -> dict:
    """The operational receipt row. Failures are retained here too, so a refusal is never mistaken for a missing run."""
    return {
        "receipt_id": execution.receipt_id, "computation": execution.computation,
        "computation_version": execution.computation_version, "contract_digest": execution.contract_digest,
        "code_digest": execution.code_digest, "knowledge_version": execution.knowledge_version,
        "installation_id": installation_id or str(execution.params.get("installation_id") or ""),
        "campaign_id": str(execution.params.get("campaign_id") or ""),
        "campaign_version": int(execution.params.get("version") or 0),
        "params": canonical(execution.params), "snapshot_id": int(execution.snapshot_id),
        "output": canonical(execution.output), "output_digest": execution.output_digest,
        "attested": bool(verdict["attested"]), "result": verdict["result"],
        "problems": canonical(list(verdict["problems"])), "counts": canonical(dict(verdict["counts"])),
        "executed_at": execution.executed_at, "recorded_at": recorded_at or datetime.now(timezone.utc),
    }


def authoritative(receipt) -> bool:
    """Only an attested receipt may be presented as a computed count; a missing receipt is not one either."""
    if not isinstance(receipt, dict):
        return False
    return bool(receipt.get("attested")) and receipt.get("result") == RESULT_AUTHORITATIVE


def explain(receipt: dict) -> str:
    """The sentence a model may say about a receipt, and nothing stronger."""
    if not authoritative(receipt):
        return ("No attested receipt supports a count: " + (", ".join(_load(receipt.get("problems")) or
                                                                    ["the receipt is missing"])) + ".")
    counts = _load(receipt.get("counts")) or {}
    return (f"Attested {receipt.get('computation')} v{receipt.get('computation_version')} over snapshot "
            f"{receipt.get('snapshot_id')}: {counts.get('verified', 0)} verified, "
            f"{counts.get('applied_pending_verification', 0)} awaiting verification, {counts.get('open', 0)} open.")


def _load(value):
    if isinstance(value, (list, dict)) or value is None:
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None