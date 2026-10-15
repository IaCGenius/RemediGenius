# rc8: reviewed storage and knowledge recovery

The optional external review received exactly `rgce/store.py`, `rgce/object_storage.py`, `rgce/documents.py`, and `rgce/knowledge.py` from rc7 commit `dea5eed`, after explicit operator consent. Pi/DeepSeek ran with tools, MCP, extensions, skills, context discovery, templates and session persistence disabled. No AWS evidence, account identifiers, credentials, private configuration or other repositories were included. The review is input to maintainer validation, not a certification.

## Confirmed changes

- Guidance revision heads now follow `base_version` links. A clock rollback no longer silently selects an older publication after S3 recovery. Forked, incomplete or cyclic revision chains fail explicitly.
- Editing a variation retains its baseline and scope when those fields are omitted. An explicit replacement baseline or scope can still be reviewed.
- Recovery regenerates both `content.md` and `receipt.json` for documents.
- Failed local-to-S3 activation rolls back its binding-table creation, leaving the original local workspace usable. This defect was found during maintainer reproduction; the external reviewer had considered this path correct.
- Context failures propagate through the full prerequisite chain. An excluded variation cannot suppress its baseline. This was independently reproduced by the maintainer.
- A failed/uncertain remote write or local commit blocks subsequent writes on that Store instance until restart and S3 recovery. Tests include remote success followed by local transaction failure.

## Review triage

| External finding | Disposition |
|---|---|
| Wall-clock recovery can regress the current revision | Fixed with revision-chain selection and recovery/next-publication regression tests. |
| Unexpected record keys or safety caps block recovery | Deliberate fail-closed boundary retained. Skipping unknown evidence or removing memory caps is not a safe default. Operational recovery and current capacity limits are documented. These are not admission quotas; large-workspace lifecycle tooling remains a limitation. |
| Missing/corrupt originals block recovery; startup re-downloads originals | Deliberate complete-recovery requirement retained. No degraded workspace is advertised as complete. Startup cost remains proportional to retained records and originals. |
| Variation revision drops its override | Fixed; omitted scope is preserved as well. |
| `at` is not historical database time travel | Clarified here: it supplies the freshness/effective-date evaluation clock against current recorded guidance. It does not reconstruct prior publications, withdrawals or mappings. Use immutable `knowledge_use` receipts for past decisions; `use_history` compares them to current guidance. |
| Recovery omits readable document receipts | Fixed and verified by byte-for-byte local/recovered receipt comparison. |
| Forged ZIP declared size permits unlimited decompression | Not confirmed as stated. A bounded crafted archive with a forged central-directory size was rejected by Python ZIP CRC validation. This does not prove every parser is resource-safe: the conversion worker has a timeout and size checks, but is explicitly not an OS sandbox. |
| Repeated withdrawal events | Multiple explicit operator assertions remain audit events; catalog/export reduce withdrawal membership to a set/existence check. No conflicting active guidance results. |

Additional questions: AWS S3 is the supported object backend; generic S3-compatible servers are not claimed. A nonempty workspace prefix is intentional. Generic OKF without applicability stays a draft. Knowledge-use receipts store full record shapes, matching the comparison code. The uncertain-commit safeguard addresses retries against a stale cache within one Store instance; separate simultaneous writers remain unsupported.

## Acceptance

The rc7 acceptance report and artifact hashes remain historical. This is a separate rc8 candidate. Validated on the rc8 source and Docker image:

- 118 CE tests, 38 deterministic rule cases, result-view checks and 30 existing kiosk tests passed.
- Three Edge browser journeys passed against rc8: files/ZIP download, knowledge editing/review and source onboarding.
- Actual AWS S3 source collection, conditional storage writes, migration/retry, denied delete/out-of-prefix read/unconditional writes, and fresh tmpfs Docker recovery passed. Recovered document receipts were explicitly checked.
- A fresh Windows wheel installation outside the checkout passed intake, variation revision, export and reassessment; all 32 package files matched the wheel.
- The isolated AWS instance was replaced with the rc8 image and recovered its previously retained S3 workspace. Container restart discarded tmpfs while preserving records. No inbound security-group rules and denied Parameter Store reads were verified.

Sanitized results and artifact hashes are in [rc8 results](acceptance/rc8-results.json). These are concrete tests against synthetic selected fixtures, not a claim of exhaustive coverage of every customer account or AI response. The earlier model acceptance remains the rc6 evidence; this source-review run did not send AWS data to a model.

The final stop receipt confirms the isolated AWS host is stopped. Retained S3 data and EBS can still incur storage charges. No public release or hosted multi-tenant service is implied. Existing product infrastructure and source remain separate. Private review transcripts and raw AWS results stay in the ignored local acceptance directory.
