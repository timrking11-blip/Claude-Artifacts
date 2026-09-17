variable "project_id" {
  description = "Google Cloud project that runs the agent and owns the dataset."
  type        = string
}

variable "dataset_id" {
  description = "BigQuery dataset to create for the logs."
  type        = string
  default     = "crm"
}

variable "dataset_location" {
  description = "Dataset location (US, EU, or a region). Cannot be changed after creation."
  type        = string
  default     = "US"
}

variable "retention_days" {
  description = <<-EOT
    Days to retain logged prompts and completions; 0 keeps them forever.
    This is a deliberate choice: the rows hold contact data the agent read
    and the briefs it wrote about them.
  EOT
  type        = number
  default     = 0

  validation {
    condition     = var.retention_days >= 0
    error_message = "retention_days must be 0 (keep forever) or a positive number of days."
  }
}

variable "vertex_service_agent" {
  description = <<-EOT
    Override for the service account Vertex writes logs as. Leave null to use
    service-<PROJECT_NUMBER>@gcp-sa-aiplatform.iam.gserviceaccount.com.
  EOT
  type        = string
  default     = null
}

variable "labels" {
  description = "Labels applied to the dataset."
  type        = map(string)
  default     = { managed-by = "terraform", component = "claude-request-logging" }
}
