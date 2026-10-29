account_id = "123456789012"
subnet_id  = "subnet-REPLACE"
name       = "remedigenius-ce"
source_zip = "../../dist/v0.5.0/remedigenius-ce-0.5.0-spot.zip"
running    = true

# Existing Secrets Manager secret holding only your model API key (never put the key itself here).
# A customer-managed KMS key on the secret is detected and granted automatically.
# model_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:YOUR_SECRET"
# model_name       = "deepseek-v4.1-flash"          # validated model
# model_base_url   = "https://YOUR_PROVIDER/v1"     # OpenAI-compatible endpoint serving that model

# regions          = ["us-east-1", "eu-west-1"]     # default: us-east-1
# member_role_arns = ["arn:aws:iam::111122223333:role/RemediGeniusReadOnly"]
# watch_deliver    = "local"                        # or a messaging target configured in Hermes
