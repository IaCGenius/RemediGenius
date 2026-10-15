# Native Hermes AWS sketch — live review, 2026-10-13

This is a working architecture sketch for owner review, not a CE release sign-off.
It uses real AWS observations and real model calls, not seeded demo findings.
The v2 engine and earlier CE console deployment were not changed.

## Open it

The private review tunnel is `http://127.0.0.1:9121/chat?profile=ce-desk` while the
local SSM tunnel process is running. Select **ce-desk** or **ce-analyst**, not the
unconfigured upstream default profile. This is the native Hermes web interface.
It exposes upstream Skills, Models, Profiles, Channels and MCP configuration;
no messaging channel or MCP server has been connected for this sketch.

To retrieve only the dashboard username/password locally:

```powershell
C:\work\remedigenius-community\tools\open-native-hermes.ps1 -ShowLogin
```

Keep that output private. This retrieves the dedicated dashboard login, not the
model key. To reopen a disconnected tunnel, run the same script without
`-ShowLogin`. Do not start a second tunnel on an occupied local port.

Try:

> Use shared-evidence to read the current Security Hub sample. What did AWS
> report, what is your interpretation, and what evidence is still missing?

## What was exercised

| Journey | Observed result |
|---|---|
| Independent Terraform deployment | Separate Spot ASG, retained encrypted session volume, private gateway, dedicated login secret and scoped discovery Lambda |
| Native runtime | Official digest-pinned Hermes v0.21.5; native ce-desk and ce-analyst install and run |
| Model key | Existing approved Secrets Manager key fetched by host into tmpfs; passed to native Hermes; no key committed or printed |
| Deterministic discovery | Real single-account, us-east-1 API responses saved in S3 with normalized status and receipts |
| Available sources | Security Hub, GuardDuty, Inspector and CloudTrail discovered; local Security Lake and Config not enabled as observed |
| Bounded findings | One page of 20 ACTIVE Security Hub findings, ordered by update time; `has_more=true` |
| Deterministic sample counts | CRITICAL 2, HIGH 2, MEDIUM 1, LOW 15; these are AWS labels and sample counts, not model-assigned severity or account totals |
| Native desk model turn | Loaded shared-evidence skill, inspected files/receipt, returned cited source-availability answer |
| Native analyst model turn | Eight tool calls, cited the real findings sample and receipt; preserved the exact severity counts and partial scope |
| Compute replacement | Updated launch configuration replaced Spot; retained volume reattached, previous native session database/trace survived, gateway and hydration resumed |
| Evidence write boundary | Native container write probe failed with read-only filesystem error |
| Post-model integrity | All 10 current S3 records matched recorded SHA256 and length; ASG replacement reported Successful |
| Credential/network boundary | No AWS credential environment variables in Hermes; metadata and host-service probes failed; model key available as intended |
| Native web interface | Dedicated login, ce-desk selection and a complete browser chat turn verified; four tool calls, correct sample counts, `has_more` warning and cited evidence path |
| Focused offline checks | Five file-inspection checks and two collector scope/status checks passed; Terraform validation and Python compilation passed |

Private test outputs, screenshots, cloud command receipts and tfvars remain under
`.rgce/native-sketch/`, excluded from Git. Real AWS resource names/findings and
credentials are not part of the public documentation. The deployed source bundle
SHA256 was `8b65987bcaa9c88454e9b47be4e694888d8dce8a58ec473866a67566b4bc67b7`;
Lambda has its separately recorded collector hash in each receipt.

## Problems found rather than hidden

The initial boot's all-zero check rejected a newly created encrypted EBS volume.
Device identity, blank filesystem signatures and AWS creation metadata were
inspected before correcting initialization. The fresh-volume path now requires
the exact configured volume, no snapshot, expected size and a short creation-age
window; older unrecognized volumes fail closed. Replacement successfully used
the existing filesystem. This sketch does not yet exercise every failure mode of
volume recovery or a natural AWS Spot interruption.

The first desk answer overreached from an empty local Security Lake result to
absence of shared lake access. Profile guidance was tightened; the subsequent
analyst explicitly said that local absence does not rule out cross-account access.

The analyst correctly reproduced the severity totals but incorrectly described
all 15 LOW findings as missing metric filters: the sample actually contains 14
such findings and one LOW GuardDuty finding. It also suggested `ListSubscriptions`
as a Security Lake API name; that proposal was not validated or executed. New
collector/API proposals need validation against the provider SDK before use.
The local botocore Security Lake service model confirms `ListSubscribers` as the
subscriber-list operation; that operation was not added to this collector.
Its explanations of why a service rates something CRITICAL are interpretation,
not a recorded provider rationale. These errors demonstrate why generated prose
is labelled as a draft and cannot overwrite evidence or directly run cloud code.

## Deliberately unfinished

- Agent-triggered collection/approval is not connected. The operator invokes the
  fixed collector; no general AWS credentials are given to Hermes.
- Custom-code Lambda kiosk and builder remain off. Reuse the existing v2 kiosk
  design when adding a reviewed execution path; do not equate this fixed reader
  with an already working arbitrary-code kiosk.
- Organization knowledge ingestion/review from the preserved CE workspace is not
  yet attached to this native sketch. An empty knowledge layer is reported honestly.
- Native conversations/scratch use retained EBS, not S3 snapshots. S3 is already
  authoritative for raw records, deterministic summaries, receipts and catalogue.
- Security Lake subscription/query access was not tested because no local lake
  was discovered. Do not enable a lake just to satisfy this demo.
- GuardDuty detail, CloudTrail/S3/CloudWatch event collection, other regions,
  cross-account roles, Azure and GCP are not claimed as implemented here.

Next useful step: agree on this native experience, then connect one bounded
collection-request skill and the shared-knowledge files, preserving these boundaries.
The earlier CE features and code remain available for selective reuse.
