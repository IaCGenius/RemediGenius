# Bring your own model

Use a capable reasoning model with reliable tool calling. DeepSeek v4.1 Flash is the tested release baseline, not a requirement to use that provider. No subscription, API key or model credits are included.

The native profile uses Hermes's custom provider with a model ID, OpenAI-compatible base URL and MODEL_API_KEY. Configure the workstation launcher or AWS Terraform inputs in the [setup guide](../START-HERE.md). On Spot, configure the model inside Hermes or supply an existing Secrets Manager secret as an optional initial seed. Workstation mode supports a local environment variable or your Secrets Manager secret. Never commit keys.

Selected AWS evidence, resource identifiers, knowledge and drafts can reach the reasoning/critic model. Choose a provider, endpoint, region and retention policy your organization permits. Self-hosting does not imply local inference.

What your model provider receives and retains depends on your provider, endpoint
and settings; review its terms before connecting AWS data. RemediGenius CE works with models
Hermes supports; DeepSeek v4.1 Flash is the tested configuration. A compatible endpoint
alone does not establish authentication or reliable tool calling. Keep model
selection in Hermes; no automatic provider fallback is implied.

RemediGenius CE's daily collection does not call a model. Use a provider plan that permits your
workload. Review [your responsibility](LIMITS.md#your-responsibility).


## RemediGenius CE startup configuration

Model, endpoint and key routing are owned by Hermes. RemediGenius CE seeds only the first
profile; retained settings survive restart. This release tests DeepSeek v4.1 Flash using
`provider: custom`, an OpenAI-compatible HTTPS endpoint and `key_env: MODEL_API_KEY`.
Use a strong reasoning model with reliable tool calling and 64k+ context. See
[Hermes providers](https://hermes-agent.nousresearch.com/docs/integrations/providers)
and [Hermes FAQ](https://hermes-agent.nousresearch.com/docs/reference/faq).

The workstation `model_key_env` selects which **host** environment variable to read;
RemediGenius CE delivers it inside Hermes as MODEL_API_KEY. Spot retrieves a raw key from the
configured Secrets Manager ARN and delivers the same variable. Stay on this custom
configuration for the release; changing Hermes to a native provider can require
other environment variables that this launcher does not inject. Do not assume a
provider switch alone changes key delivery.

[Startup checks and error codes](TROUBLESHOOTING.md#startup-model-probe) describe
the one-request probe. A context-size error is not a reliable measurement of a
model's maximum capacity; confirm the provider's context configuration.
