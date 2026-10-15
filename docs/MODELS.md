# Models: bring your own key

The agents use one OpenAI-compatible endpoint: `model_base_url` + `model_name` in `terraform.tfvars`, and the key in
Secrets Manager (`set_model_key` output). Nothing else in the stack depends on the provider.

## Choose a plan that allows what you run

| Use | Interactive? |
|---|---|
| You chat with the desk agent in Hermes Desktop | Yes |
| `schedule_enabled = true` (collector + daily agent jobs) | **No.** Scheduled, unattended |
| Scripts that drive an agent (`hermes chat -q` from cron or CI) | **No** |

Some subscription plans allow **interactive use only**. Alibaba's Token Plan, for example: "Not permitted for
automated scripts or application backends"
([Personal](https://www.alibabacloud.com/help/en/model-studio/token-plan-personal-overview),
[Team](https://www.alibabacloud.com/help/en/model-studio/token-plan-team-overview)). Use such a plan only with the
schedule off, and switch to pay-as-you-go before turning it on.

## Options

| Provider | `model_base_url` | Notes |
|---|---|---|
| Alibaba Model Studio, pay-as-you-go (international) | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Qwen models. Alibaba's international terms say member content is not used to train models without consent. Data is processed in the Singapore region (cross-border for most users) |
| Amazon Bedrock (OpenAI-compatible endpoint, or a gateway) | your Bedrock endpoint | Qwen3 and DeepSeek in several regions. Prompts stay in AWS; model providers have no access to them ([Bedrock data protection](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html)) |
| Self-hosted open weights (vLLM, Ollama, ...) | your server, e.g. `http://10.0.0.5:8000/v1` | Qwen3 is Apache-2.0, DeepSeek-R1 is MIT; check each model's licence. The host security group allows outbound 443/80 only: add a rule for your port |
| Any other OpenAI-compatible provider | its `/v1` URL | Check that its terms allow automated use if you schedule jobs |

Agents work best with a strong tool-using model. The checks themselves do not depend on the model: rules decide
findings and severities.

## What the model sees

Configuration facts from your account: resource names, policy documents, security group rules, counts. It never sees
stored data (the read-only role denies reading it) and never sees your keys. Choose a provider whose data terms fit
your rules.

## Changing the model

Edit `model_base_url` / `model_name`, `terraform apply`, then reconcile the profiles: `./refresh.sh`. To rotate the key, put a new value with `set_model_key`, then on the host
run `sudo systemctl start rg-hermes-secrets` (restarts the agents with the new key).
