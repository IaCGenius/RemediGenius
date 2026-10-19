# Start with RemediGenius CE

CE runs Hermes with one `ce-desk` profile, bounded AWS read tools, organization
knowledge and fix validation. The operator applies fixes. Collection runs on the
same Docker workstation or Spot host; evidence and private recovery checkpoints
are stored in S3.

**The local-compute migration is being acceptance-tested.** The published v0.1.3
release is unchanged. Current deployment guides refer to the working source.

| Choose | What you need | Guide |
| --- | --- | --- |
| Docker workstation | Docker, AWS profile, private S3 bucket, your model | [Local setup](docs/LOCAL-COMPUTE-WORKSTATION.md) |
| AWS Spot | Provisioning identity, existing subnet in us-east-1, your model | [Spot setup](deploy/aws-single/README.md) |

Both offer the native Hermes dashboard and optional hermes-ui. Select **ce-desk**.
Ask what target is configured, request a bounded inventory/findings investigation,
and inspect its source receipts and coverage gaps. To add organization context,
ask CE to stage a scoped policy, review the draft, then confirm publication.

Read [architecture and recovery](docs/SINGLE-HOST-MIGRATION.md), [permissions](docs/IAM.md)
and [reused tools](docs/AWS-TOOLING.md). Scheduled checks stop when compute stops.
The S3 checkpoint interval is two minutes, not zero-data-loss replication.
