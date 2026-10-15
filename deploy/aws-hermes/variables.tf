variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Provide the intended twelve-digit account ID."
  }
}
variable "region" {
  type = string
  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.region))
    error_message = "Use a plain AWS region identifier."
  }
}
variable "subnet_id" {
  type = string
}
variable "name" {
  type    = string
  default = "rgce-hermes"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,48}$", var.name))
    error_message = "Use a simple dedicated resource name (up to 48 characters)."
  }
}
variable "running" {
  type    = bool
  default = false
}
variable "associate_public_ip" {
  type    = bool
  default = true
}
variable "instance_type" {
  type    = string
  default = "t3.medium"
}
variable "bucket_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.bucket_name))
    error_message = "Use a plain existing S3 bucket name."
  }
}
variable "workspace_prefix" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.workspace_prefix))
    error_message = "Use a dedicated slash-separated prefix without a trailing slash."
  }
}
variable "console_image_key" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_./-]+$", var.console_image_key))
    error_message = "Use a plain S3 key."
  }
}
variable "hermes_image_key" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_./-]+$", var.hermes_image_key))
    error_message = "Use a plain S3 key."
  }
}
variable "console_archive_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.console_archive_sha256))
    error_message = "Pin the console archive SHA256."
  }
}
variable "hermes_archive_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.hermes_archive_sha256))
    error_message = "Pin the Hermes archive SHA256."
  }
}
variable "console_image_id" {
  type = string
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.console_image_id))
    error_message = "Pin the loaded console Docker image ID."
  }
}
variable "hermes_image_id" {
  type = string
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.hermes_image_id))
    error_message = "Pin the loaded Hermes Docker image ID."
  }
}
variable "model_secret_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws[a-z-]*:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+$", var.model_secret_arn))
    error_message = "Provide one exact Secrets Manager secret ARN, never its value."
  }
}
variable "secret_kms_key_arn" {
  type        = string
  default     = null
  description = "Optional exact customer-managed KMS key for the model secret."
}
variable "model_provider" {
  type    = string
  default = "custom"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.model_provider))
    error_message = "Use a plain Hermes provider identifier."
  }
}
variable "model_name" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_.:/-]+$", var.model_name))
    error_message = "Use a plain provider model identifier."
  }
}
variable "model_base_url" {
  type = string
  validation {
    condition     = can(regex("^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9_./-]*)?$", var.model_base_url))
    error_message = "Use an HTTPS model API base URL without credentials, query parameters or shell metacharacters."
  }
}
variable "model_key_env" {
  type    = string
  default = "OPENAI_API_KEY"
  validation {
    condition     = can(regex("^[A-Z][A-Z0-9_]*_API_KEY$", var.model_key_env)) && !startswith(var.model_key_env, "AWS_") && !startswith(var.model_key_env, "RGCE_")
    error_message = "Use the provider API key variable, e.g. OPENAI_API_KEY or DEEPSEEK_API_KEY, not an AWS or RGCE variable."
  }
}
