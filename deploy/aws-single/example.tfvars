account_id          = "123456789012"
subnet_id           = "subnet-REPLACE"
name                = "rgce"
source_zip          = "../../.rgce/spot-source.zip"
running             = false
spot_instance_types = ["t3.large", "t3a.large"]
container_memory_mb = 6144
hermes_ui           = true
# Optional: existing secret containing only your model API key.
# model_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:YOUR_SECRET"
# model_name = "YOUR_MODEL_ID"
# model_base_url = "https://YOUR_PROVIDER/v1"
