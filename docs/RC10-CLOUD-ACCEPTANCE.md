# rc10 cloud Hermes acceptance — 2026-10-13

This is a **tested private preview for practitioner review**, not general availability. The cloud console and Hermes runtime are part of CE. The workstation preview and RemediGenius v2 were left unchanged.

## Verified

| Check | Actual result |
|---|---|
| CE regression | 157 passed; 4 Windows symlink checks skipped |
| Broker tests in Linux | All 23 passed, including the symlink cases |
| Native Hermes initialization | Real pinned AIAgent initialized with exactly `ce_read_file` and `ce_search_files`; no model network call in this test |
| Live model investigation | A real consented Bailian investigation of the previously approved synthetic AWS fixture completed; citations matched and result was saved in S3. This ran before the final runner progress/prompt refinements. |
| Final-image live follow-up | Real Bailian call completed with 13 native CE file-tool calls; used actual prior answer and historical collected AWS evidence. No invented environment note was added. Answer matched its durable S3 record exactly. Citation status remained `needs_review`; see limitations below. |
| Live cancellation | A second real call performed three file-tool calls, then operator cancellation stopped it and produced a durable cancelled receipt. Already-incurred provider usage may be charged. |
| Failure handling | An earlier real run timed out when worker DNS was blocked. Its failed receipt remained visible; it was not reported as success. DNS was corrected and a new run succeeded. |
| Final cloud images | Actual replacement host runs the console pin below; broker advertises the final Hermes pin |
| Spot replacement | Previous writer terminated; new instance recovered all 12 baseline records and the completed investigation from S3. No model replay. |
| Network on final replacement | Model hostname resolves; unauthenticated HTTPS responds 401. Metadata HTTP, host console and tested private-network TCP destinations denied. |
| Queue cancellation | Real broker stopped temporarily; request queued and cancelled before restart. Durable cancelled receipt, no model call. This tests queued cancellation, not mid-provider cancellation. |
| Browser on final replacement | Edge: S3 status, ready Hermes, selection, exact disclosure review, invalidation after question edit, prior-answer follow-up disclosure, mobile width, no JavaScript errors |
| Image/source match | All 34 installed CE package files, Hermes runner and host broker match current source after newline normalization |

## Pins

- Console: `sha256:4fd1577d6094c256e804abc5b725fa59c1e7ab96d71d009e9f8da1796de4513f`
- Hermes: `sha256:2ee7e3caf7996ee47b2b2576cf348ce193c6fec21e472e001ca295d3675f8924`
- Hermes upstream: `f97608f178d1ffeca59860195ab7da295f7c8e5f`
- Console archive SHA256: `49befb12f550f5d8e5f7b80c43450570a61b5be8b081509b357d9e0167b48b34`
- Hermes archive SHA256: `9bb348a8223d370b7cfc89f5dfe1b74e0d2d90fd16a617209cd16b58aa3c71bf`

## Review findings and limits

The user authorized real model calls on 2026-10-13. The final-image follow-up and live cancellation completed. No fabricated environment value or new synthetic knowledge note was supplied. Missing environment context remained `NEEDS_CONTEXT`. The final runner's progress callback reported 13 real tool calls.

Manual review found both useful reasoning and errors. The answer correctly rejected a reachability inference from zero attached interfaces, preserved deterministic CRITICAL severity, ignored the injected instruction inside source evidence, and retained missing context. However, it incorrectly treated an older export timestamp as invalid merely because the current export had a different timestamp, and continued to describe imported draft metadata versus local approval as a conflict. These are model interpretation errors, not changes to the records. Its `needs_review` citation status came from a quoted rule-engine SHA256 being treated as an unknown record citation. The conservative checker does not distinguish every non-record hash. None of these checks certify model correctness; the answer remains visibly unreviewed.

The tested investigation used explicitly selected synthetic fixture records collected in earlier AWS acceptance, then imported into this isolated workspace. It was not a new scan of unrelated resources. The scoped host role cannot scan the whole account. The initial model answer still required human review: matching citations do not establish factual correctness. The final prompt adds explicit cautions about inferring reachability from interface counts and confusing imported metadata with local approval.

DeepSeek is configurable but untested and has no supplied key. Abrupt in-flight Spot interruption and additional provider failures are not claimed as live acceptance. Recovery of completed records and queued cancellation were tested separately. No public GitHub push or hosted CI run is claimed. The cloud host remains running for operator review; the private SSM tunnel is session-dependent.

Raw receipts, resource identifiers and model output remain in the maintainer's ignored private acceptance directory. They are excluded from the sharing bundle. Read [cloud architecture and limits](HERMES-CLOUD.md) before deployment.
