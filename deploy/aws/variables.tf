variable "account_id" {
  description = "The AWS account to deploy into (Terraform refuses any other account)"
  type        = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for every resource name; change it to run two engines in one account"
  type        = string
  default     = "rgce"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,9}$", var.name_prefix))
    error_message = "2-10 lowercase letters or digits, starting with a letter."
  }
}

variable "az" {
  description = "Availability zone for the host and its data volume; empty = the region's first zone"
  type        = string
  default     = ""
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/24"
}

# ---------------------------------------------------------------- model (bring your own key)
variable "model_base_url" {
  description = "OpenAI-compatible endpoint of your model provider, e.g. Alibaba Model Studio pay-as-you-go (docs/MODELS.md)"
  type        = string
}

variable "model_name" {
  description = "Model id at that endpoint; the same model serves all agents"
  type        = string
}

# ---------------------------------------------------------------- engine
variable "running" {
  description = "false = scale the instance to zero (stop paying for compute, keep all data)"
  type        = bool
  default     = true
}

variable "instance_types" {
  description = "Spot pools, first is preferred. 8 GB RAM is enough for the three agents."
  type        = list(string)
  default     = ["t3.large", "t3a.large"]
}

variable "hermes_image" {
  description = "Hermes Agent image (MIT, Nous Research), pinned by digest"
  type        = string
  default     = "nousresearch/hermes-agent:v2026.9.24@sha256:fca358f12efd65bfaaca05884166f15c0e2788375ca30d77061ac1ebc96452b7"
}

variable "dashboard_port" {
  description = "Dashboard port on the host loopback; connect.sh forwards the same port to your laptop"
  type        = number
  default     = 9120
}

variable "root_volume_gb" {
  type    = number
  default = 30
}

variable "data_volume_gb" {
  description = "Agent state: sessions, memories, facts, results"
  type        = number
  default     = 20
}

variable "snapshot_keep" {
  description = "Daily snapshots of the data volume to keep"
  type        = number
  default     = 7
}

variable "secret_recovery_days" {
  description = "Days a deleted secret can be restored; 0 = delete at once (lets a rebuild reuse the names)"
  type        = number
  default     = 7
}

variable "destroy_data_on_teardown" {
  description = "true = terraform destroy also empties and deletes the results bucket. false keeps it (destroy then fails on the bucket)."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------- schedule (off until you choose)
variable "schedule_enabled" {
  description = <<-EOT
    true = run the collector daily and resume the agents' daily jobs (checks at +30 min, Morning Brief at +2 h).
    Needs a model plan that allows automated use: interactive-only plans (e.g. Alibaba Token Plan) forbid it.
  EOT
  type        = bool
  default     = false
}

variable "collect_on_calendar" {
  description = "systemd OnCalendar for the collector; the agents' jobs run at 05:30 and 07:00 UTC"
  type        = string
  default     = "*-*-* 05:00:00 UTC"
}

# ---------------------------------------------------------------- accounts to assess
variable "self_regions" {
  description = "Regions the collector reads in this account"
  type        = list(string)
  default     = ["us-east-1"]
}

variable "accounts" {
  description = <<-EOT
    Other AWS accounts to assess. After apply, deploy onboarding/aws/readonly-role.yaml in each one with the
    parameters from the `onboarding` output. Example: { prod = { account_id = "111122223333", regions = ["eu-west-1"] } }
  EOT
  type = map(object({
    account_id = string
    regions    = list(string)
  }))
  default = {}
  validation {
    condition     = alltrue([for k in keys(var.accounts) : can(regex("^[a-z][a-z0-9-]{0,30}$", k)) && k != "self"])
    error_message = "Account keys: lowercase, digits, dashes; 'self' is reserved for this account."
  }
}

variable "readonly_role_name" {
  description = "Name of the read-only role in every assessed account (the template's RoleName)"
  type        = string
  default     = "RemediGeniusCommunityReadOnly"
}

# ---------------------------------------------------------------- lambda kiosk (optional)
variable "enable_kiosk" {
  description = "true = deploy the lambda kiosk and the builder agent (run `python modules/lambda-kiosk/build.py` before plan)"
  type        = bool
  default     = false
}

variable "kiosk_sandbox_cidr" {
  description = "Secondary VPC range for the kiosk's sandbox subnet (no route out)"
  type        = string
  default     = "10.42.1.0/28"
}

variable "alert_email" {
  description = "Email for kiosk platform alerts (SNS asks to confirm once); empty = no subscription"
  type        = string
  default     = ""
}
