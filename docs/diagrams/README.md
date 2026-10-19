# Current CE architecture

Static SVGs display directly in GitHub. Editable Archify JSON and standalone HTML
viewers are included. Download an HTML file to use the interactive viewer.

| View | Image | Source | Viewer |
|---|---|---|---|
| Setup | [SVG](ce-current-setup.svg) | [JSON](ce-current-setup.json) | [HTML](ce-current-setup.html) |
| Recovery | [SVG](ce-current-recovery.svg) | [JSON](ce-current-recovery.json) | [HTML](ce-current-recovery.html) |

Arrows show requests or saved data. Responses return through the requesting
connection; return arrows are omitted. The model provider is outside the host.
Collector and validator run in separate containers on the same compute.
The local scheduler runs deterministic checks without a model.

| Component | Implementation |
|---|---|
| Profile and skills | [ce-desk](../../profiles/ce/desk) |
| Workflow, scope, budgets and critic | [Runtime](../../profiles/ce/desk/plugins/ce-runtime) |
| SDK collection and daily checks | [Collector](../../deploy/collector) |
| Spot host, IAM and storage | [AWS stack](../../deploy/aws-single) |
| Workstation | [Setup guide](../LOCAL-COMPUTE-WORKSTATION.md) |
| Tool validation | [Validation guide](../REMEDIATION-VALIDATION.md) |
| State recovery | [Recovery boundaries](../SINGLE-HOST-MIGRATION.md#storage-and-interruption) |

The instance role combines metadata/security reads with limited operational writes
for CE storage and recovery. Hermes receives no AWS credentials. Workstation
collection uses the operator's configured AWS credentials instead.

Published notes, sessions and cases live on retained storage and are checkpointed.
File import/export remains operator-led. A chat attachment is not automatically
shared knowledge. Existing state takes priority over recovery to an empty home.
State archives may contain credentials; evidence-read tools cannot access them.

Historical Lambda diagrams and the obsolete multi-cloud concept page are archived
in the separate v2 project. Earlier release tags retain their original history.
