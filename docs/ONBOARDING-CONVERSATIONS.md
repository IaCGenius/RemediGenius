# Two onboarding conversations

Use the existing native Hermes dashboard and select **ce-desk**. No new model,
profile or credentials are needed.

## 1. Account discovery

The Spot collector performs four bounded checks on first boot and every 24 hours:
Config recorded-resource counts, Config recorder configuration, EC2 instances and
active Security Hub findings across integrated products. It uses the configured
instance/audit role. These are metadata reads, not log-content scans.

Results and receipts are retained in S3. The prepared status is
`scheduled/account-status.json` under the configured evidence prefix. A readable
page is generated in the Hermes workspace as `ACCOUNT-STATUS.md`
(`/opt/data/work/ACCOUNT-STATUS.md` inside Hermes).

In the native **Files** page, open **work** and use the download icon beside
**ACCOUNT-STATUS.md**. This Hermes version lists/downloads the document; it does
not render an inline Markdown preview. No model call is needed to read the file.
For an in-chat explanation, ask:

> Show the saved account status. Do not start a fresh investigation.

Then:

> Onboard this account using the saved status. Ask one question at a time.

Hermes should show scope, time, counts and gaps, then ask about account purpose
and priorities. Confirming that interpretation saves knowledge; it does not grant
AWS access. Config only knows recorded resources. Partial pagination, denied reads,
an empty response and an absent service are distinct outcomes.

`schedule_interval_hours` in the Spot Terraform stack controls refresh (1–168 hours,
default 24). Apply a reviewed configuration change and update the running host as
documented for an upgrade. The collector checks whether a refresh is due every minute;
this is not a new AWS scan every minute. Stopping compute stops refreshes. Check the
observed time and next expected refresh before using a saved page.

The baseline runs without an LLM. It does not continuously prioritize findings,
publish organizational knowledge, create cases or apply fixes. Ask for deeper
analysis when needed; fresh investigation remains available.

## 2. Knowledge Q&A

> Help me onboard our knowledge. Ask one question at a time.

Hermes should first read existing context, then ask what the workload does and what
matters. It can clarify resource scope, owners, sensitivity, change constraints and
exceptions. You can skip unknown details. Do not supply credentials.

> Draft and stage what I told you as our workload brief.

Review the actual Markdown and scope. Send the exact `publish knowledge <id>`
phrase returned by the tool as a separate message. Then ask:

> Read the brief we published and explain how it will affect your priorities.

In a new conversation:

> What confirmed context do you have for this account?

Chat context is usable immediately; publication makes it reusable across sessions.
Files and exports still use the documented intake process. A URL or attachment is
not automatically shared knowledge. Confirmed context is separate from refreshing
AWS facts; scans do not overwrite your policies or exceptions.

## Quick manual acceptance

- The status document is already available before asking for an investigation.
- Chat explains freshness and incomplete coverage without running new AWS reads.
- The Q&A asks one useful question at a time and does not invent business facts.
- Staging shows text for review; publication waits for your confirmation message.
- A new session can read the published brief and identify its scope.
- An analysis explains which knowledge changed priority, while retaining AWS severity.

This is a conversational wizard plus a prepared document in Hermes Files, not a
separate graphical onboarding application.

## Initial live check

The first deployed baseline successfully read recorder configuration, EC2 instances
and active Security Hub findings. Config resource counts returned
`ThrottlingException`; the saved page reports the run as PARTIAL rather than claiming
full inventory. Failed reads must not be interpreted as zero resources. Python
syntax and Terraform configuration validation passed. The conversational steps
above are the operator UI acceptance checklist; no new broad model test campaign
was run for this change.
