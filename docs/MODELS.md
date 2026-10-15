# Bring your own model

Use a capable reasoning model with reliable tool calling. Qwen 3.8 Max is the tested release baseline, not a requirement to use that provider. No subscription, API key or model credits are included.

The native profile uses Hermes's custom provider with a model ID, OpenAI-compatible base URL and MODEL_API_KEY. Configure the workstation launcher or AWS Terraform inputs in the [setup guide](../START-HERE.md). Cloud keys come from your Secrets Manager secret; workstation mode supports a local environment variable or your Secrets Manager secret. Never commit keys.

Selected AWS evidence, resource identifiers, knowledge and drafts can reach the reasoning/critic model. Choose a provider, endpoint, region and retention policy your organization permits. Self-hosting does not imply local inference.

What your model provider receives and retains depends on your provider, endpoint
and settings; review its terms before connecting AWS data. CE works with models
Hermes supports; Qwen 3.8 Max is the tested configuration. A compatible endpoint
alone does not establish authentication or reliable tool calling. Keep model
selection in Hermes; no automatic provider fallback is implied.

CE's daily collection does not call a model. Use a provider plan that permits your
workload. Review [your responsibility](LIMITS.md#your-responsibility).
