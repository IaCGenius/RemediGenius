# Target-bound verification

A proof is only a proof of one thing: this installation, account, region, resource generation and artifact digest, under
one approved predicate version, from one named verifier, with retained evidence that is fresh, complete and not observed
under a clock skew the policy rejects.

## The binding

`evaluate(observation, approved=target)` checks, and reports every failure rather than the first:

| Check | Why it fails closed |
| --- | --- |
| target id, account, region, generation, artifact digest | a proof for another target cannot verify this one |
| observation account | no fallback to another configured account (a CE-02 regression) |
| truncated / partial read | a capped read is not evidence of absence |
| evidence sha256 | an authoritative predicate requires retained evidence |
| clock skew and freshness | a proof observed outside the accepted window is not a pass |
| predicate version | the verdict names the rule version that produced it |

`verified` is true only when nothing failed **and** the outcome is `pass`.

## Two separate facts

- **Technical proof** — what the verifier saw on the target (`pass`, `fail`, `error`, `inconclusive`).
- **Provider acknowledgement** — AWS later resolving the finding.

They are recorded separately: `provider_resolution()` returns its own event with `affects_technical_proof: false`, and
`evaluate()` reports `provider_acknowledged` without folding it into `verified`. A resolution cannot upgrade a failed
proof, and a passing check does not claim the provider forgot the finding.

## Policy decides what may close

`may_close(verdict, policy)`:

| Policy | Closes when |
| --- | --- |
| `targeted` (default) | the target-bound proof passed |
| `provider` | the proof passed **and** the provider resolved it |

The verdict only reports; the policy in force decides. Unknown policies raise rather than defaulting to something safe.

## Every attempt is persisted

`attempt_row()` writes one row to `target_verifications` for every attempt, including `fail`, `error`, `inconclusive`,
truncated and stale ones, with the verifier, the predicate id/version/digest, the rule, the target generation, the
artifact digest, the evidence id, the clock skew and the reason. `attempt_id` is deterministic, so a replayed attempt is
the same row rather than a second fact.

`verifications(target_id)` returns the attempts newest first with `latest` and `verified`, so "what did we try, with
which rule, and what did it say" is answerable without reading logs.

## Not in this layer

Choosing which predicate to run, and running it. This module decides whether a given observation verifies a given
target; the existing collectors and proof path produce the observation, and campaign derivation (CE-21) consumes the
verdict.