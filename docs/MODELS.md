# Models — RemediGenius Community Edition

RemediGenius-CE uses whatever model Hermes is configured with. The validated model is **`deepseek-v4.1-flash`**, served
through an OpenAI-compatible endpoint (`provider: custom`, `base_url`, key in `MODEL_API_KEY`). Use a model with
reliable tool calling and at least 64k context.

| Deployment | How the model is set |
| --- | --- |
| Spot | `model_secret_arn` (key in Secrets Manager; a customer-managed KMS key is granted automatically), `model_name`, `model_base_url`; or leave the secret empty and choose a model in the dashboard |
| Docker workstation | `REMEDIGENIUS_MODEL_KEY` in your shell environment plus `--model-base-url` (and `--model-name`); or configure in the dashboard |
| Existing Hermes | `tools/install_local_hermes.py --clone-from <profile>` reuses that profile's provider |

The key is copied once into the profile's `.env` inside the Hermes home (Hermes profiles do not inherit process
secrets). Later changes made in the dashboard are kept. The model never sees the key, and it is never written to
chat, Terraform variables or logs.

Model usage: deterministic scans and the `security-watch` alert make **no** model calls. Model calls happen when you
chat. A briefing typically takes a few calls; an investigation 5–20. Other models and providers work if Hermes supports
them, but they are not validated.
