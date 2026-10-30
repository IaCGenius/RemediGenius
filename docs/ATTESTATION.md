# Attested computation: campaign counts

A model can be asked for a number, and the honest answer must come from a computation someone reviewed — not from the
model's reading of a page. `campaign_verification_summary` is the one computation this release runs through the scoped
data service (CE-22). It is deliberately not a general query engine and not an arbitrary-code runner.

## The contract

| Field | Value |
| --- | --- |
| Computation | `campaign_verification_summary` |
| Version | `1` |
| Parameters | `campaign_id` (string), `version` (integer ≥ 1), `installation_id` (string), `as_of` (timestamp, optional), `evidence_set` (sha256, optional) |
| Output | campaign/version/installation, membership digest, member count, `verified`, `applied_pending_verification`, `open`, `verified_not_applied`, `evidence_complete`, `as_of`, `evidence_set`, `unsupported` |
| Reducer | `_reduce`, a pure function over campaign membership rows |

Parameters are an allow-list: an unknown key is refused, not ignored. The model may choose the campaign, the version, an
`as_of` and the approved accounts; it cannot pass SQL, a script or a different reducer.

`APPROVED_CODE_DIGEST` is a reviewed pin of the reducer source and `tests/test_attest.py` fails when the source changes
without the pin changing. Changing the computation is therefore a review event: edit, bump `COMPUTATION_VERSION`, re-pin,
and record it — never a runtime choice.

## Execution

`execute()` runs the reducer over membership rows read from **one pinned table snapshot** and binds:

- the contract digest (parameters, required keys, output shape, reducer name);
- the code digest (the reducer source);
- the typed parameter values;
- the input snapshot id;
- the knowledge version;
- the output and its digest.

Those bindings produce a deterministic `receipt_id`, so the same inputs and version produce the same receipt, however
often the computation runs.

## Attestation

`attest()` re-derives the answer from the retained rows and compares everything. It fails closed when:

| Condition | Reason |
| --- | --- |
| the reducer source or the contract changed | `the computation code/contract changed since the receipt was produced` |
| a row belongs to another campaign or membership version | `a row belongs to another campaign or membership version` |
| a row's account is outside the approved scope | `account … is not in the approved scope` |
| a verified row has no retained evidence | `the evidence set is incomplete` |
| verified members exist but no evidence set was pinned | `the evidence set is not pinned` |
| the recomputed output differs from the recorded one | `the output does not match the retained inputs` |
| the recorded digest does not match the output | `the recorded output digest does not match the output` |
| the caller supplies a different snapshot | `the input snapshot is not the pinned one` |
| no retained inputs were supplied | `no retained inputs were supplied` |

A verified row without evidence is **not** verified for the computation: it counts as awaiting verification, appears in
`unsupported`, and makes `evidence_complete` false. The number can therefore never quietly include an unevidenced claim.

## Receipts

`receipt_row()` writes one row per run to `computation_receipts` — including a failed attestation, with
`result = failed_attestation`. Receipts are operational evidence, kept apart from the curated OKF knowledge bundle.
`campaign --summary --record` appends the receipt once; the deterministic id makes a replay a no-op.

Only an attested receipt may be quoted as a computed count (`authoritative(receipt)`), and `explain(receipt)` is the
sentence a model may say: an attested receipt becomes a sentence with the snapshot and the three counts, and a failed or
missing one becomes "No attested receipt supports a count: …". A page-derived number is labelled as such in the view
(CE-23).

## What this does not do

It does not give the model SQL authority, does not run arbitrary code, does not compute anything other than campaign
counts, and does not turn a receipt into a remediation decision. It also does not make a campaign's counts a proof for any
individual target: the per-target proofs (CE-18) remain the only thing that closes one.

## Example

```
rgtriage campaign camp-1 --summary --record --account 111122223333
Campaign camp-1 v1 · Attested campaign_verification_summary v1 over snapshot 1234567: 930 verified, 20 awaiting verification, 50 open.
Result: {'verified': 930, 'applied_pending_verification': 20, 'open': 50, 'verified_not_applied': 0, 'member_count': 1000} · attested True · receipt 4c1f… · snapshot 1234567 · recorded
```