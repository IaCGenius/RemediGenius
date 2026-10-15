variable "account_id" { type = string }
variable "region" { type = string }
variable "subnet_id" { type = string }
variable "associate_public_ip" {
  type        = bool
  default     = false
  description = "Enable for a public subnet using an Internet gateway. Otherwise supply NAT or equivalent outbound access for AWS APIs, model endpoint and package/image downloads."
}
variable "name" {
  type    = string
  default = "rgce-native"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,40}$", var.name))
    error_message = "Use a dedicated lowercase resource prefix."
  }
}
variable "running" {
  type    = bool
  default = false
}
variable "bucket_name" { type = string }
variable "workspace_prefix" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.workspace_prefix))
    error_message = "Use a new slash-separated prefix with no trailing slash."
  }
}
variable "source_archive_key" { type = string }
variable "source_archive_sha256" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{64}$", var.source_archive_sha256))
    error_message = "Pin the uploaded source ZIP SHA256."
  }
}
variable "hermes_image" {
  type    = string
  default = "nousresearch/hermes-agent:stable@sha256:444b42594e7f467425872fc35e077a227d377f0fe0726bc818706d62175fad8b"
  validation {
    condition     = can(regex("^nousresearch/hermes-agent:[A-Za-z0-9_.-]+@sha256:[a-f0-9]{64}$", var.hermes_image))
    error_message = "Use the official Hermes image pinned by digest."
  }
}
variable "model_secret_arn" { type = string }
variable "model_name" { type = string }
variable "model_base_url" {
  type = string
  validation {
    condition     = can(regex("^https://[A-Za-z0-9.-]+(:[0-9]+)?(/[A-Za-z0-9_./-]*)?$", var.model_base_url))
    error_message = "Use a plain HTTPS compatible API endpoint."
  }
}
variable "profiles_dir" {
  type    = string
  default = "profiles/ce"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.profiles_dir))
    error_message = "Use a relative source directory without traversal."
  }
}
variable "read_role_arns" {
  type        = list(string)
  default     = []
  description = "Exact scoped roles the deterministic host helper can assume; agents receive none."
}
variable "secret_kms_key_arns" {
  type    = list(string)
  default = []
}
variable "instance_type" {
  type    = string
  default = "t3.medium"
}
variable "spot_instance_types" {
  type        = list(string)
  default     = ["t3.medium", "t3a.medium"]
  description = "Compatible x86 Nitro Spot choices in the session volume's Availability Zone. Empty uses instance_type."
}
variable "container_memory_mb" {
  type    = number
  default = 3072
  validation {
    condition     = var.container_memory_mb >= 1024 && floor(var.container_memory_mb) == var.container_memory_mb
    error_message = "Use an integer MiB limit of at least 1024, leaving memory for the host."
  }
}
variable "hermes_toolsets" {
  type        = string
  default     = "skills,clarify,ce_runtime"
  description = "Operator-selected native TUI toolsets; include enabled plugin/delegation toolsets explicitly."
  validation {
    condition     = can(regex("^[A-Za-z0-9_:-]+(,[A-Za-z0-9_:-]+)*$", var.hermes_toolsets))
    error_message = "Use comma-separated Hermes toolset identifiers."
  }
}

variable "aws_read_targets" {
  description = "Named AWS scopes; blank role uses the executor account. Cross-account roles remain operator configured."
  type        = map(object({ account_id = string, regions = list(string), role_arn = optional(string, ""), external_id = optional(string, "") }))
  default     = {}
}

variable "knowledge_view" {
  description = "Optional selected view under workspace_prefix/knowledge/. Empty leaves organizational knowledge disconnected."
  type        = string
  default     = ""
  validation {
    condition     = var.knowledge_view == "" || can(regex("^[A-Za-z0-9_-]+$", var.knowledge_view))
    error_message = "Use one versioned view name without path separators."
  }
}

variable "schedule_enabled" {
  type        = bool
  default     = false
  description = "Daily deterministic AWS snapshots and comparison; no scheduled model calls."
}
variable "schedule_interval_hours" {
  type    = number
  default = 24
  validation {
    condition     = var.schedule_interval_hours >= 1 && var.schedule_interval_hours <= 168 && floor(var.schedule_interval_hours) == var.schedule_interval_hours
    error_message = "Use 1 to 168 whole hours; default is daily."
  }
}
variable "scheduled_checks" {
  type    = any
  default = []
  validation {
    condition     = length(var.scheduled_checks) <= 4 && alltrue([for c in var.scheduled_checks : c.max_pages >= 1 && c.max_pages <= 3])
    error_message = "At most four checks, each capped at one to three pages."
  }
}
