# Native Hermes: live AWS investigation

The single-compute deployment uses one profile, `ce-desk`, and a local,
deterministic collector. See [setup](../START-HERE.md) and
[deployment boundaries](SINGLE-HOST-MIGRATION.md). The previous Lambda deployment
is archived in v2; its deployment instructions do not apply to this path.

## From a question to evidence

1. Hermes frames the request, loads the CE skill and checks available capabilities.
2. CE checks the target, region, workflow stage, admitted operation and budget.
3. The tool sends a bounded request over a private Unix socket to the collector.
4. The collector uses the Spot instance role, or the workstation operator's
   temporary credentials. Hermes receives neither credential source.
5. The pinned AWS SDK collects records and writes responses, deterministic
   projections and receipts to S3. Pagination limits and failures remain visible.
6. Hermes reads the returned evidence paths, selects relevant published knowledge,
   and separates observed facts from interpretation and proposed fixes.
7. After the operator applies a change, CE collects fresh evidence and compares
   the same scope. A proposal or a closed case does not change AWS by itself.

Try: "Read current ACTIVE Security Hub findings. Preserve AWS severity, cite the
receipts and explain the missing coverage." For CloudTrail, specify a time window
and page budget. A page limit can cover only part of the requested window.

## Source and boundaries

- `deploy/collector/operations.json`: admitted service operations and IAM mapping.
- `deploy/collector/executor.py`: request validation, SDK pagination and S3 receipts.
- `deploy/collector/server.py`: private socket, stored evidence access and scheduling.
- `profiles/ce/desk/skills/ce-aws-read/`: instructions and the thin socket client.
- `profiles/ce/desk/plugins/ce-runtime/`: workflow, review and execution budgets.

A listed operation means CE can request it, not that the source is enabled,
accessible or tested in every account. Current deployment inputs configure the
single deployment account in `us-east-1`. Config recording, aggregators, Cloud
Control resource support, delegated administration and resource policies can all
affect coverage. Report the tested scope rather than claiming complete inventory.

The collector defaults to one page per request, accepts at most ten, and stops at
its response/time budget (4 MB and approximately 55 seconds). AWS call timeout can
extend wall-clock completion. SDK retries are disabled. Continuation state remains
available for a subsequent admitted request; an incomplete read is not an absence
claim. CloudTrail LookupEvents requires a timezone-aware window of at most 90 days.

The model-facing reader accepts evidence prefixes, not recovery-state archives or
arbitrary S3 objects. Collector code does not execute model-generated shell or
Python. A separate Linux validator checks remediation drafts without applying them.
See [IAM](IAM.md) for the host's operational writes and metadata read permissions.

AWS evidence sent to the configured model follows the operator's provider choice.
Knowledge is operator-supplied context; it does not replace a current AWS observation.
