# AWS operation discovery and bounded collection

The reader uses a pinned AWS Service Authorization Reference catalog and the
installed botocore schemas. The original operations list remains a set of
recommended starting points; it is not the broad reader's service ceiling.

## Operator flow

Ask the same ce-desk questions. For an unfamiliar service Hermes discovers
catalog capabilities, inspects input schemas, and selects bounded reads inside
ce_assessment. The collector executes SDK calls, stores source responses and
receipts in S3, and returns selected evidence. It does not execute generated code.

AWS IAM still decides access. A catalog entry proves classification and SDK
availability, not permission, successful collection or live acceptance. Missing
classification is a tooling gap, not proof that a resource does not exist.
A denied detail read does not invalidate discovery from another source.

## Credentials

Spot provisions a separate audit role trusted by the RemediGenius CE host. The collector
assumes that role for investigation. Its original host identity writes RemediGenius CE
artifacts and supports recovery. Hermes receives neither identity's credentials.
SecurityAudit and ViewOnlyAccess form the audit baseline. Explicit exclusions
block known credential retrieval and application-body access. This is not a
universal sensitive-data detector: configuration and findings can contain
sensitive text, and the model receives the selected evidence.

Each audit role must belong to its configured target account. The host assumes
it directly; RemediGenius CE does not chain an audit session into a second role. The session
policy limits the requested IAM actions. Cloud Control also needs downstream
metadata reads, intersected with the audit role's policies.

Workstation users can supply `audit_role_arn` in their launcher JSON. The storage
Terraform accepts `audit_principal_arn` (the existing operator IAM role/user ARN)
to create this role and returns its ARN. The operator needs permission to assume
it; an administrator must supply that grant if absent. Without an audit role,
legacy configured reads remain available but newly classified reads are blocked
with READ_ROLE_REQUIRED. Do not use an administrator role as the audit role.

## Fixed boundaries

- Configured account and region remain frozen per investigation.
- Write, permission-management and tagging mutations are not admitted.
- Unclassified operations are blocked; method names are not a security rule.
- Page, byte, time and action limits remain enforced. Continuation is explicit.
- AWS denial, catalog gaps and empty results remain different outcomes.
- Existing knowledge, sessions, Kanban and S3 receipts retain their formats.
- Catalog updates are explicit build/package changes, never background expansion.

The catalog is based on [AWS's machine-readable reference](https://docs.aws.amazon.com/service-authorization/latest/reference/service-reference.html).
AWS states that operation/action mappings are incomplete and may lag updates.
Existing reviewed compatibility operations are identified separately in catalog
provenance; they must not be described as automatically classified by AWS.

## Source selection

Use an existing Config aggregator when appropriate, then account Config or a
relevant native API. Do not enable Config or other services automatically.
Resource Explorer and Cloud Control supplement discovery; neither guarantees
universal coverage. Prefer a current direct read for a specific resource when
that avoids unnecessary calls. Stop on a material access gap, preserve evidence,
and offer a task or bounded continuation rather than retrying indefinitely.

## Rollout status

Live acceptance exercised Security Hub, IAM metadata and Bedrock discovery through
Hermes with DeepSeek. See the [validation record](RELEASE-VALIDATION.md) for exact
results and package hashes. This is not evidence that every catalog operation has
been exercised against a live account.

The pinned snapshot contains 8,076 admitted operations across 407 services with
at least one admitted read. These are classification counts, not functional-test
coverage. Regeneration uses `tools/build_read_catalog.py` with the collector's
pinned SDK. Review the resulting changes before packaging; the runtime does not
download or expand its catalog.

## IAM questions

The catalog includes IAM users, roles, access-key metadata, last-use metadata,
group membership, attached policies, inline policies and policy versions. An
attached AdministratorAccess policy is an attachment fact, not a proof of
effective access: permission boundaries, SCPs, session and resource policies can
change the result.

`GetCredentialReport` reads an existing lifecycle report. RemediGenius CE decodes its CSV into
a normalized artifact and preserves `GeneratedTime` separately from collection
time. The report contains audit metadata, not secret access keys. If no report
exists or it is stale, report that limitation and use relevant admitted metadata
reads where useful. RemediGenius CE does not call `GenerateCredentialReport` as a hidden write.
See [AWS credential report fields](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_getting-report.html).

AWS read classifications can include report or export generation. RemediGenius CE separately
excludes known report-generation and Config snapshot-delivery operations. A read
classification is not a guarantee of no side effects, no charges or no sensitive
metadata; scoped IAM and these documented exclusions remain necessary.
