# Deployment receipts

A receipt is what an existing CI/CD system observed, told to the desk as a fact. RemediGenius-CE does not deploy
anything: it records the chain and refuses to let one step stand in for another.

## Five separate facts

| Kind | Says | May satisfy |
| --- | --- | --- |
| `pr` | a pull request exists | nothing |
| `merge` | a pull request merged, and at which commit | `merged` |
| `build` | a build ran for a commit, with an artifact digest | `built` |
| `deploy` | that artifact reached a target generation | `deployed` |
| `verify` | an independent proof ran for that target generation | `verified` |

A merged PR is not a build; a green build is not a deployment; a deployment is not a verification. Those are separate
rows and separate steps, so "the PR merged, so it is fixed" cannot be expressed.

## Identity, replay and quarantine

A receipt's identity is the producer's own id, not a timestamp: `producer:kind:external_id` (for example
`github-actions:build:run-42`). The payload digest is the canonical JSON of what the producer sent.

| Situation | Result |
| --- | --- |
| identity not seen before | `accepted` |
| same identity, same payload | `duplicate` (no second fact) |
| same identity, different payload | `quarantined`, with the reason kept |
| producer not in the configured allow-list | `rejected` |
| payload does not match the approved plan | `rejected`, with every mismatch listed |

Quarantine and rejection are stored rows too: a receipt that was refused is evidence about the producer, not something
to discard silently.

## What a receipt must match

Every receipt is checked against the approved plan before it counts: the plan digest and proposal identity must exist,
and the repository, commit, target, target generation, account and artifact digest must agree with what was approved. A
deployment is additionally compared with the digest the build produced, so a rebuilt or substituted artifact cannot
satisfy the approved plan.

## Reconciling an uncertain operation

`reconcile` folds a chain of receipts into facts without submitting anything. It never resubmits a change, and it keeps
unresolved what it cannot prove:

- a missing approval or proposal identity stays in `unresolved`;
- a receipt from an untrusted producer, or one that fails the plan check, stays in `unresolved` with its reasons;
- `deployed` and `verified` are only true when their own receipts were accepted.

The recovery rule from CE-11 applies unchanged: read the existing CI or GitHub result and record what is there rather
than repeating the action.

## Where it is stored

`deployment_receipts` keeps one row per receipt attempt with the producer, actor, payload digest, evidence reference,
target generation and the outcome. `rgtriage`'s `receipts` query returns the chain for a target or campaign oldest
first, with that provenance.

Not in this step: the HTTP or CLI transport that accepts a receipt from a CI system, and the operation intents that
trigger a build. The deterministic ingestion path above is what those will call.