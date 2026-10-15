# Bring your own model

Use a capable reasoning model with reliable tool calling. Qwen 3.8 Max is the tested preview baseline, not a requirement to use that provider. No subscription, API key or model credits are included.

The native profile uses Hermes's custom provider with a model ID, OpenAI-compatible base URL and MODEL_API_KEY. Configure the workstation launcher or AWS Terraform inputs in the [setup guide](../START-HERE.md). Cloud keys come from your Secrets Manager secret; workstation mode supports a local environment variable or your Secrets Manager secret. Never commit keys.

Selected AWS evidence, resource identifiers, knowledge and drafts can reach the reasoning/critic model. Choose a provider, endpoint, region and retention policy your organization permits. Self-hosting does not imply local inference.

## Bedrock qualification

Bedrock is the proposed AWS-native model path, **not yet a validated CE default**. Changing a URL alone does not establish authentication, model/API support, tool calling, auxiliary critique, retention or regional routing. Test these through pinned Hermes before promoting a concrete configuration. Never silently switch providers or fall back outside the operator's policy.

Bedrock supports specific [API/endpoint combinations](https://docs.aws.amazon.com/bedrock/latest/userguide/apis.html). AWS describes inference in AWS-operated model deployment accounts, not solely inside the customer's account. Do not promise “data never leaves your AWS account.” Check [data protection](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html) and [retention](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html) for the selected model and routing configuration.

CE's daily deterministic collection does not call a model. Interactive reasoning and automated evaluation are separate workloads; use a model plan that permits the workload. Historical console model/scheduling instructions do not describe native CE.
