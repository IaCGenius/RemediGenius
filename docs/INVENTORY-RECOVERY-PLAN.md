# Inventory recovery — implementation and acceptance plan

Status: work in progress; not release acceptance. No new release tag.

## Product behavior

An existing connected account must support a useful inventory investigation without
requiring a new collector for each question. Hermes chooses evidence within the
fixed process. The Lambda executes admitted SDK reads, handles pagination, and
saves source responses and receipts to S3. Credentials stay in the executor.

## Discovery procedure

1. Discover accessible Config aggregators. Query the relevant account, region and
   resource types. Report denied, absent, stale and empty separately.
2. If aggregation is absent or does not cover the target, use account-local Config
   discovery/query APIs. Check recording coverage; no records is not no resources.
3. Use Cloud Control list/read for AWS resource types when Config lacks coverage.
   Discover schemas through CloudFormation. This works without a customer-created
   CloudFormation stack. Handler permissions and supported operations still apply.
4. Use existing admitted service APIs for details, Resource Explorer for indexed
   discovery, and tagging as supplementary evidence. CloudTrail establishes history
   and identity; it is not the current inventory.
5. Return discovered resources, source coverage, specific failures and unresolved
   questions. Do not hide collected records when a later model step fails.

This follows the established separation used by inventory/security collectors:
read-only identity, reusable service collectors, retained data, then assessment.
See [Prowler](https://prowler.com/cloud-security-solutions/aws-security-audit),
[CloudQuery](https://www.cloudquery.io/hub/plugins/source/cloudquery/aws/latest/docs),
and [AWS Cloud Control](https://docs.aws.amazon.com/cloudcontrolapi/latest/userguide/resource-operations.html).
Neither Config nor Cloud Control guarantees coverage of every AWS resource type.

## Necessary changes

| Area | Change | Why code is needed |
|---|---|---|
| Capabilities/IAM | Config reads, Cloud Control list/read and schema discovery; audited read-role policies | Skills cannot grant APIs or permissions |
| Collection | SDK pagination, durable continuation information and explicit byte/time/page stops | A model must not parse or count unlimited raw logs |
| Workflow | Multi-page bounded reads; preserved evidence after failure; meaningful exception type | The old gate and one-page rule are enforced in code |
| Skills | Aggregator → local Config → Cloud Control fallback, schema use, history vs inventory | Procedure should be readable and reusable |
| UI delivery | Show partial facts and failures from retained results | A reasoning failure must not erase successful collection |

## Acceptance required before claiming success

- Live native Hermes UI: original Bedrock inventory and creation-history question.
- Independent AWS comparison: identities, timestamps, resource identifiers and
  successful versus failed create events.
- An unrelated resource family through the same discovery path.
- Config aggregator absent → local Config checked → alternative inventory used.
- Multi-page history: no page-one completeness claim; continuation usable when a
  bound is reached. Receipts and source data remain in S3.
- Denial/source unavailable/model failure: specific failed step, retained facts,
  no fabricated absence or infrastructure repair instruction.
- Existing sessions, knowledge and credentials preserved through backup/upgrade.

Unit tests check boundaries and regression behavior only. They do not substitute
for these live functional tests. Test fixtures must be labelled and never presented
as customer inventory. Internal account evidence stays outside public Git.

## Current validation status

The collector changes are deployed to the test installation. Live requests passed
for Config discovery, Cloud Control resource listing and multi-page CloudTrail
continuation; stored evidence hashes matched the receipts. The upgrade preserved
existing sessions, credentials and shared knowledge after backup.

Native UI testing found three additional issues: the outer agent could narrow the
objective to a guessed tool list; a model hop could exceed the fixed 60-second
timeout; an unknown nested schema field terminated the whole investigation.
The candidate corrects inventory framing, uses a configurable bounded model timeout,
and returns valid schema fields for a recoverable lookup error. Retesting found a
real guardrail through Cloud Control after empty Config results. A separate native
UI test returned matching VPC/log-group counts, including four completed log-group
pages. The inventory skill now reserves reads for resources instead of spending
the whole budget on prerequisite discovery. Completed budget-limited runs receive
runtime-owned follow-up instructions; their read budgets cannot reset by resuming.

Local boundary/regression checks: 101 passed. A further native UI creation-history
test completed three CloudTrail pages (101 events), attributed successful guardrail
and version creation to the recorded IAM identity, and separated two denied agent
creation attempts. The answer matched independent AWS reads. These are functional
DeepSeek tests, not just code tests.

The assessment's interpretation, review and final answer use the same evidence
packet. Its procedure context currently includes the four packaged assessment
skills plus writing and inventory references; it does not automatically inherit
every additional skill loaded by the outer Hermes conversation. Do not describe
this as sharing the entire conversation context.

Remaining qualification: inventory of the whole service family was bounded and
partial; a configured Config aggregator and member-account deployment were not
exercised in this account. This candidate is not release-qualified. Existing
release tags remain unchanged while the operator reviews these results.
