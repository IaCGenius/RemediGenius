# Copy to terraform.tfvars (git-ignored) and fill in. Never put keys here: the model key goes into
# Secrets Manager with the set_model_key output after the first apply.

account_id = "111122223333" # the account you deploy into
region     = "us-east-1"

# Your model: any OpenAI-compatible endpoint (docs/MODELS.md). Example: Alibaba Model Studio pay-as-you-go,
# Singapore. Check the exact model id in your provider's console.
model_base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
model_name     = "qwen-max"

self_regions = ["us-east-1"]

# Other accounts to assess (optional). After apply, run the `onboarding` output in each account.
# accounts = {
#   prod = { account_id = "444455556666", regions = ["us-east-1", "eu-west-1"] }
# }

# Daily collector + agent jobs: off until you choose. Needs a model plan that allows automated use.
schedule_enabled = false

# The lambda kiosk and the builder agent (optional): run `python modules/lambda-kiosk/build.py` before plan.
enable_kiosk = false
# alert_email = "you@example.com"
