# AWS preview: useful outcomes and actual coverage

The v0.1 preview baseline is **AWS us-east-1 with Qwen 3.8 Max** in native
Hermes, using the single `ce-desk` profile. Other regions and models remain
configurable, but are outside this preview's acceptance baseline. Customers
provide their own model credentials and explicitly configure their AWS targets.

Start with three questions:

1. “Triage our Security Hub findings in us-east-1. Give me the top three next
   actions, the evidence and what you still need to know.”
2. “Investigate EC2 management activity for the last five days. Show the actual
   time coverage and any incomplete pages.”
3. “Use our selected policy to explain this finding, prepare a CLI proposal,
   and help me save it for reassessment after our change process.”

The third journey prepares a draft. CE does not apply a customer-cloud fix.
Terraform or CloudFormation can be requested instead; not every AWS setting is
supported by every format. A model critique is not provider validation.

## Available operations versus demonstrated behavior

The [operation manifest](../modules/aws-read-executor/operations.json) is the
authoritative source for the SDK reads the executor can admit. The deployed
`ce_aws capabilities` response is authoritative for that installation: an older
deployment may expose less. IAM permissions, service enrollment and populated
records are separate checks. “Available” does not mean every operation was tested
against a populated account, or that CE discovers all organization accounts.

| Source | Available reads | Useful outcome | Recorded live acceptance and limits |
|---|---|---|---|
| Security Hub | Findings; hub; finding aggregators; members; enabled standards | Rank existing findings; retain severity, control IDs and standard references; prepare scoped next actions | Qwen triage and fresh comparison used real findings with independently checked counts. Interpretation/proposal defects and later corrections remain documented; not a compliance attestation. |
| CloudTrail | LookupEvents; trail definitions; trail status | Recent regional management-event investigation with actors, errors and deterministic timeline | Five-day EC2 request tested with real records; bounded pages returned only part of the requested window. Not S3 object-event, historical S3-log, CloudWatch-log or lake querying. |
| EC2 | Instances; security groups; interfaces; route tables; VPCs; subnets; regions | Inventory and scoped configuration context | Two-account instance inventory tested, with separate receipts and empty-result handling. This does not certify network reachability or every listed EC2 read. |
| S3 | Bucket list; public-access block; policy status; default encryption; versioning; logging | Inspect specific bucket settings; prepare and reassess a proposal | Real default-encryption and versioning reads exercised. Default encryption is not proof of all existing objects' encryption. No arbitrary object-body collection. |
| AWS Config | Recorder definitions **and recorder status**; aggregators; source status; aggregate select/get | Separate configured coverage from observed recording state; inspect existing aggregate configuration | Earlier live definition read returned empty. Recorder-status read was added after that test; see the current release acceptance for its deployment/retest result. Aggregator-query support does not mean populated-aggregator acceptance. |
| GuardDuty | Detectors; detector settings; finding IDs/details; members | Enrich selected threat findings and identify readable coverage | Source-call/receipt checks recorded; no claim of a complete populated GuardDuty investigation suite. Prefer existing Security Hub findings first. |
| Inspector | Findings; coverage; account status | Enrich vulnerability findings and inspect reported coverage | Source-call/receipt checks recorded; all coverage types and populated findings are not certified. |
| IAM Access Analyzer | Analyzers; finding list/detail | Inspect source-reported access findings | Source-call/receipt checks recorded; not arbitrary IAM policy analysis or automatic permissions repair. |
| Macie | Session; finding list/detail | Report accessibility and enrich selected findings when permitted | Tested session call returned AccessDenied; CE retained an error receipt and did not retry indefinitely. No successful populated Macie acceptance claimed. |
| Security Lake | Lakes; log sources; subscribers | Discover existing lake metadata and identify an available source | Tested local lake list was empty. This is **discovery, not lake analytics**; no Athena/Lake Formation query integration is shipped. |

An empty response, a denied request, a missing capability and a healthy control
are different outcomes. CE records query scope, time, errors and pagination.
Neither an empty account nor an enabled service establishes that the account is
secure. No paid AWS security service is enabled automatically.

## From evidence to a useful decision

| Step | What the operator receives | What CE preserves |
|---|---|---|
| Collect | Scoped native source reads, deterministic counts/projections and limitations | Raw responses and hashed receipts in the configured S3 prefix |
| Understand | Hermes interpretation of the actual observations and relevant selected knowledge | AWS facts stay separate from organizational assertions and AI judgment |
| Prioritize | Up to three next decisions, with reason and uncertainty | Native finding IDs/severity and source framework mappings remain unchanged |
| Prepare | CLI-first draft or requested IaC/source edit, prerequisites, impact, verification and rollback limits | Explicit distinction between a draft, validation actually performed and an executed change |
| Follow up | Optional native Kanban case, notes and delayed reassessment | Conversations/cases on the runtime volume; S3 is not a backup of that volume |
| Reassess | A fresh scoped read and comparison, with a reasoned conclusion | Historical receipts and case history; no silent finding suppression or automatic closure |

Daily checks collect configured evidence without requiring the reasoning agent to
stay alive. They do not autonomously investigate every change or execute proposals.
The operator can change the interval or disable checks. Scope and limits remain
explicit; see the [workstation walkthrough](WORKSTATION-HERMES.md) or
[native AWS quickstart](NATIVE-CE-QUICKSTART.md) for the deployment settings.

## See how your knowledge changes the answer

Bring readable policies, service ownership, resource purpose, runbooks, change
constraints or scoped exceptions. Start with a few relevant documents, not your
entire document estate. [Knowledge onboarding](NATIVE-KNOWLEDGE-QUICKSTART.md)
explains file intake, selected views, publication and activation.

Ask: “Which knowledge did you use, where does it apply, what did it change, and
what is still unknown?” The knowledge skill guides Hermes to give a short
**Knowledge used** explanation with the source path/version, scope match,
recommendation affected and unresolved context. It must read the source before
claiming to use it. This explanation is in the conversation, not a separate
automatic knowledge-use ledger.

A scoped organization exception can change a recommendation without changing the
observed AWS setting or suppressing an AWS finding. Unknown resource purpose
stays unknown; names alone do not establish exception applicability. Conflicting
documents are surfaced when they affect the decision. Import time is not policy
precedence or an effective date. The operator remains responsible for supplied
context; CE adds provenance and review assistance, not another approval committee.

## Read the test evidence

- [Current MVP acceptance](MVP-ACCEPTANCE.md): fresh-source Windows/Linux checks,
  live Qwen knowledge use, independently checked Config definition/status empty
  responses, workstation runtime and Spot update.

- [Native runtime acceptance](CE-RUNTIME-ACCEPTANCE.md): real-source checks and
  execution boundaries.
- [Native preview acceptance](NATIVE-PREVIEW-ACCEPTANCE.md): deployment,
  proposals, saved cases and corrections.
- [Layered assessment acceptance](LAYERED-ASSESSMENT-ACCEPTANCE.md): framework
  grouping and knowledge use, including preserved partial results.
- [Organization exception acceptance](ORG-EXCEPTION-ACCEPTANCE.md): real
  operator policy, conditional applicability and explicit unknowns.
- [Critic context acceptance](CRITIC-CONTEXT-ACCEPTANCE.md): shared captured
  skill results and bounded evidence; not an infallible review gate.

SDK boundary unit tests use constructed responses to check error handling and
receipt preservation. They are never labelled live AWS or Qwen acceptance.
