# MCP fresh-install follow-up (2026-11-02)

PR #62 was merged at `e1d4e23426451ab845f907db21d98cb86ebe5b59`. At validation time GitHub's latest
published release was still v0.7.0 from October 30. This run tested the exact merge as a local candidate,
not a newly published release. No release tag or asset was created on GitHub.

## Fresh deployment and defects caught

A separate disposable stack was created from zero on plain Amazon Linux 2023, without a baked runtime,
existing warehouse or copied lab configuration. Source, wheel and Spot archives contained the planned
MCP/analytics modules, installers and documentation and no private-state filenames.

The existing 55 host/browser release checks passed, but extended feature checks caught an unavailable
managed AWS MCP runtime. The initial desk install had resolved `cachetools==7.2.8`; the captured MCP
snapshot required `7.2.7`. Freezing the already-installed desk correctly refused the conflict. A service
health check did not detect the missing default capability.

The correction applies the same dependency snapshot to initial desk installation and the later MCP
extension. Baked markers now include the constraint-file digest, so legacy or changed snapshots force
resolution instead of silently reusing an incompatible runtime. The release gate now executes a real
managed AWS read and all four Athena reports; unavailable, malformed or unsuccessful results fail it.

Optional Terraform guidance had a separate recovery gap: its connection is checkpointed, but the binary
under `installs/` is deliberately excluded. Bootstrap now reruns the pinned installer only for the enabled,
shipped connection. Custom connections and disabled connections are preserved.

A subsequent replacement also exposed missing OKF durability: approved concepts and imported References
live in `/data/rgtriage/knowledge`, outside the three checkpointed homes. The correction checkpoints and
restores that directory separately as `knowledge`, without reintroducing checkpoints of the rebuildable
desk cache. Existing live installations must checkpoint this home before replacement. Earlier checkpoints
cannot recreate approved concepts they never contained; original imports/drafts may support manual recovery,
but must not silently be reclassified as human-reviewed.

## Feature evidence

- Four real Athena reports succeeded from the fresh warehouse: trend, coverage, verification and scan
  coverage. Empty verification rows were reported as no matching evidence, not proven remediation.
- A natural-language history question selected `rg-analytics` and deferred `rg_analytics`; the answer
  explained that one observed day cannot establish a trend or continuous seven-day coverage.
- Native public onboarding succeeded for AWS Knowledge, DeepWiki and Terraform Registry. DeepWiki's
  first probe failed transiently and a retry passed. Real retrieval returned Prowler repository structure
  and the AWS IAM skill. A handshake alone is not treated as content certification.
- Synthetic document import preserved canonical source/revision, deduplicated repeated imports and
  remained unverified. AI produced a cited Team draft; approval saved a `human-reviewed` Team with the
  expected contact and named reviewer. A repeated approval refused overwriting the existing concept.
- The corrected dependency setup resolved in an empty Linux virtual environment; `pip check` passed.
  Focused host tests passed: 29 cases, including dependency snapshots, runtime selection and OKF checkpoint wiring.

## Final packaged recovery

The complete corrected Spot archive has SHA-256
`09b656b7d112b4952d3d33176346dbe00448c5cf9ec3788d11e3a5665857bea3`.
Terraform deployed it and a real replacement host confirmed those exact bytes. Four-home checkpoint results
were positively checked as SAVED/UNCHANGED with nonempty file sets before replacement.

After cold boot, the reviewed Team retained its contact and named human reviewer; its linked Reference retained
the canonical source URL and revision. Both appeared in the durable knowledge checkpoint manifest. The enabled
Terraform Registry executable was reinstalled automatically, without an in-place repair. This proves the final
packaged recovery path, rather than only a simulated restore or a healthy service process.

The strengthened gate then passed 54 host checks and six browser checks. These include the actual managed
AWS region read and all four successful Athena reports. The recovered Knowledge graph contained 41 concepts,
including the synthetic Reference and reviewed Team. Public AWS skill, Prowler and Terraform Registry reads
also passed again after automatic recovery. No model credential or authenticated document-source credential
was printed or added to the public artifacts.

Authenticated vendor document connectors still require customer sign-in and representative content;
this run does not certify them. Long-duration credential expiry, scan-cap exhaustion and large-result
pagination remain separate limits. Public vendor endpoints can fail transiently and must report missing
evidence rather than imply successful retrieval.
