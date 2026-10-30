# Shared-cause campaigns and partial rollout

A vulnerable base image affects many workloads at once. Patching it is one change; proving every dependent workload is
fixed is one proof per workload. This module derives a *candidate* campaign from proven lineage (CE-20), states the plan
a person approves (CE-21), and reconciles what actually happened afterwards. It never deploys anything: the plan targets
the CI/CD and operator workflows you already run.

## Who is a member

A workload joins the candidate campaign only when all of these hold:

| Check | Evidence | Otherwise |
| --- | --- | --- |
| The campaign image has a `sha256:` digest | the digest was observed | `image is not an immutable digest` |
| A runtime inventory receipt says what the workload runs | CE-20 inventory | `runtime inventory missing` |
| That image **is** the campaign image digest | digest equality | `runs a different image digest` |
| The account was inspected | the scan scope | `account was not inspected` |
| The package came from the base layer | CE-20 origin | `package came from the application layer` |
| An open finding on that workload needs this package | findings | `no finding on this workload needs this fix` |
| The installed package is this purl/CPE | CE-20 package identity | `package matched by name only` |

Every exclusion carries the target and a detail string, so a person can read why a workload that *looks* related was left
out. The same package name on another digest is the common false cause; it is excluded, not merged.

The membership is a `Membership` (CE-16): planned once, versioned, digested. A workload discovered after approval needs a
new version and a new approval. Membership never comes from the bounded board preview.

## The plan

`plan_for()` returns the thing a person approves:

- **one immutable artifact** — the image `sha256:` digest, never a tag;
- **the exact membership** — its version, digest and count;
- **the steps** — rebuild, test, deploy, verify, each with the receipt kind that satisfies it (`build`, `build`,
  `deploy`, `verify` from CE-17);
- **the required per-target proof** — predicate id, version and rule, bound to target, resource generation and artifact
  digest, with retained evidence required;
- **stop conditions** — an unexpected artifact digest, any failed proof, a target outside the membership, or an error rate
  above the pre-rollout baseline.

`closes_all_members_on_patch` is `false` in the machine-readable plan, because it is not true: a campaign-level patch or a
tag update closes nothing.

## Reconciliation

`reconcile()` folds per-target events into exactly four disjoint buckets:

| State | Meaning |
| --- | --- |
| `verified` | deployed the approved artifact **and** a passing proof with retained evidence |
| `applied` | deployed the approved artifact, waiting for its proof |
| `open` | no approved deployment (or one was rolled back, or the finding recurred) |
| `verified_not_applied` | a proof for something that was never deployed; counted separately, never as verified |

Events are evidence, not instructions:

- a deployment of a different artifact digest is **rejected** — autoscaling onto an old image does not count as progress;
- a passing proof on a target that was not deployed does not reduce the open work;
- a **rollback** or a new occurrence reopens the target and is recorded as a recurrence, while the earlier success stays
  in the target's history;
- an event for a target outside the frozen membership is **ignored** with the reason that a new member needs a new
  version.

The 1,000-target fixture (950 deployments, 930 valid proofs) reconciles to 930 verified, 20 awaiting verification and 50
open. `state_rows()` turns that into the `campaigns` / `campaign_members` rows, including the proof's evidence id.

## What this does not do

It does not deploy, open pull requests, or resubmit anything; it does not decide that a shared cause is the *only* cause;
and it does not treat a merged PR, a green build or a campaign-level image patch as proof for any member. Reading SBOMs
and runtime inventories from AWS is the collector's job (CE-20); this normalises and reconciles what it supplies.