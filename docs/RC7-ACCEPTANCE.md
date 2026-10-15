# rc7: durable workspace and deployable compute

This candidate closes the SQLite-only persistence gap. Optional S3 mode persists records and uploaded originals before reporting success, reconstructs a local index, and preserves reviewed knowledge across compute replacement. The default no-AWS mode keeps a named Docker volume. Neither mode is a multi-user hosted service.

## Evidence

| Check | Result |
|---|---|
| CE regression | 112 tests passed on the frozen runtime source |
| Additional regression | 38 rule cases, result views and 30 existing kiosk tests passed |
| Docker UI | Edge file-export, knowledge/variation and source-onboarding journeys passed; mobile checks included |
| Browser export download | Investigation ZIP delivered to the workstation; altered export rejected |
| Local container replacement | Assessments remained in the named volume |
| Fresh Windows wheel | Installed outside the checkout; document intake, reviewed knowledge, export and reassessment passed; 32 installed package files matched the wheel |
| Real source to durable storage | Selected AWS S3 fixture collected through the read role and retained through storage recovery |
| Fresh container recovery | New tmpfs workspace recovered records, original document, baseline/variation and reproduced investigation at the same evaluation time |
| Migration | Local records/originals copied and verified; retry succeeded; source retained |
| Storage IAM negative checks | AWS denied delete, out-of-prefix read and unconditional write |
| AWS console | Separate EC2 host booted the Docker image, used S3 mode, and recovered after losing container tmpfs; no inbound rules |
| Host Parameter Store access | Explicit deny verified through the actual host role; SSM command access still worked |
| Terraform | Storage and host roots validated; test storage role and host deployed separately from existing product infrastructure |

The host acceptance script stops its exact tagged instance in a finally block. The replacement-host test recovered the prior S3 workspace after the old instance was destroyed; its final stopped receipt is retained privately. S3 data and EBS remain retained; stopped compute does not mean zero storage cost. The optional Lambda reader remains paused from rc6.

## What these tests do and do not establish

The storage tests use actual AWS services and restricted IAM roles. Synthetic content makes the checks reproducible without disclosing customer data. Unit stubs exercise failure conditions separately and are not presented as live adapter proof. The recovery container has no old SQLite database, original-document folder or host AWS configuration mounted into it; it receives only the temporary restricted storage session.

S3 mode requires one active writer per prefix. It has no distributed review transaction service, background replication or automatic source refresh. The cache is recovered at startup. Record hashes are integrity checks, not signatures. Bucket administrators remain capable of deletion or tampering. Versioning/retention is an operator concern; the customer storage root enables versioning and protects against accidental Terraform destruction.

The Docker image runs as a non-root user with a read-only root filesystem and loopback-only published port. Its application data remains writable. The AWS console deliberately has access to its restricted instance role through IMDSv2; no untrusted agent or builder should share that host. Model-provider calls remain outside the console. The rc6 model test and its factual-quality limitations still apply; this release does not claim universal AI correctness.

Pi/DeepSeek produced the initial Dockerfile/Compose draft from a synthetic specification with tools disabled. Maintainers integrated and tested it. The later, explicitly authorized four-file source review and resulting fixes are recorded separately in [rc8 review and acceptance](RC8-REVIEW.md). The rc7 artifact results above remain unchanged.

## Reproduce and inspect

- `tests/live_storage.py --run`: real source/storage, restricted IAM, migration and clean-container recovery.
- `tests/live_host.py --run`: SSM health/save/restart checks and final stop. `--expect-existing` also requires a previous workspace to survive replacement of the host.
- `scripts/test.ps1` / `scripts/test.sh`: deterministic and offline regression.
- `tests/browser_files.py`, `tests/browser_simple_knowledge.py`, `tests/browser_onboarding.py`: actual UI journeys.
- `tools/package_runtime.py`: reviewed local image archive and SHA256; no automatic upload.
- [Docker and persistence](DURABLE-WORKSPACE.md), [AWS console](AWS-WORKSPACE.md), [hosted-core handoff](CORE-HANDOFF.md).

Private plans, transcripts, identities and raw evidence stay under `.rgce`. Sanitized results are in `docs/acceptance/rc7-results.json`. The exact image identity and wheel/archive hashes should accompany the candidate. Nothing in this report means a public repository, CI release or GA tag has been published.
