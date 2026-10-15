variable "name" {
  description = "Kiosk name; resources are named kiosk-<name>-*"
  type        = string
}

variable "account_id" { type = string }
variable "region" { type = string }

variable "agents" {
  description = <<-EOT
    Agents that may use this kiosk. Each gets a role kiosk-<name>-agent-<agent> that the listed principals
    may assume, its own function namespace kiosk-<name>-fn-<agent>-*, and one execution role per allowed class.
    promotion_policy: "auto" (live after a successful canary) or "owner" (owner approves live).
  EOT
  type = map(object({
    trusted_principal_arns = list(string)
    classes                = list(string)
    promotion_policy       = string
  }))
}

variable "sandbox_subnet_ids" {
  description = "Subnets with no route out; the sandbox runs tests there"
  type        = list(string)
}

variable "sandbox_security_group_ids" {
  description = "Security groups with no egress"
  type        = list(string)
}

variable "alert_email" {
  description = "Admin email for platform alerts (SNS); empty = topic without subscription"
  type        = string
  default     = ""
}

variable "runtime" {
  description = "Lambda runtime for functions, gate and sandbox; layers are built for it (build.py)"
  type        = string
  default     = "python3.13"
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "force_destroy" {
  description = "true = the bucket (registry, bundles, outputs) is deleted with the kiosk"
  type        = bool
  default     = false
}

variable "limits" {
  description = "Caps the gate enforces; only Terraform changes them"
  type        = map(number)
  default = {
    bundle_bytes                    = 1048576
    memory_mb                       = 1024
    timeout_s                       = 900
    concurrency                     = 5
    submissions_per_version_per_day = 3
    submissions_per_agent_per_day   = 20
    promotions_per_agent_per_day    = 10
    runs_per_agent_per_day          = 200
    items_per_run                   = 100
    item_bytes                      = 65536
  }
}
