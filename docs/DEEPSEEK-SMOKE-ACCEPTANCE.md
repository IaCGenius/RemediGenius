# DeepSeek compatibility smoke test

2026-10-15. This is a targeted model compatibility check, not full release-model
qualification or a performance/cost benchmark.

The operator's existing compatible endpoint listed `deepseek-v4.1-flash` through
its models API. Two native Hermes oneshot runs used the supported per-run
`--model deepseek-v4.1-flash` override, the existing CE skills/tools and real selected
knowledge/AWS data. No synthetic organization policy or findings were substituted.
No saved profile configuration or AWS customer-resource setting was changed.
Collected evidence and acceptance sessions were saved normally.

| Test | Result |
|---|---|
| Knowledge, scoped S3 exception, operator publication instructions | PASS for targeted checks: complete source path, exact supplied command paths, no invented preview token, publication distinguished from activation, missing bucket-use classification explicit |
| Real AWS Config read and capability gap | PASS for targeted checks: zero recorder definitions, matching an independent direct AWS API read; exact scope/time/receipts; running-status operation correctly reported as not admitted rather than IAM-denied or healthy |
| Critic receives loaded skill references | PASS in both sessions: native tool-result hashes matched the review audit; no omitted skill context |
| Critic model and review limit | One critique per session; both results reported `deepseek-v4.1-flash`, not a hidden Qwen-only reviewer |
| Default profile preserved | Qwen 3.8 Max remained selected; all 59 runtime integrity entries passed afterward |

The knowledge critic received two loaded skill results and two evidence excerpts.
The AWS critic received one skill result and five evidence excerpts. The knowledge
review identified an imprecise read-time claim; the final answer used the recorded
import time. The AWS review prompted removal of an unsupported recording-state
inference. Critic explanations themselves remain AI interpretation, not independent
proof. The independent API check confirms the returned recorder count, not every
possible claim about AWS Config semantics.

Usability limitation: the AWS answer was more verbose than requested. Its empty
result does not test reasoning over a populated or complex Config estate. Running
status was not collected by Hermes because the operation was absent from the
current capability manifest; this test did not silently broaden that manifest.

Not tested here: CLI/Terraform/CloudFormation proposal correctness with this model,
full UI regression, populated high-volume findings, multi-account cases, failure
recovery suite, comparative latency/cost, or long-running reliability. Keep Qwen
as the qualified baseline while evaluating those. Strong reasoning and reliable
tool use matter more than a provider's model-family or "Flash" label.

Private responses, traces and independent API records remain under
`.rgce/layered-acceptance/deepseek-*`; they are excluded from public source. No
provider key, private endpoint, account ID or raw AWS transcript is published here.
