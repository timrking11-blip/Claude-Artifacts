# Destination for Vertex request/response logging of the Claude model.
#
# Terraform owns the destination; it cannot own the logging configuration
# itself -- setPublisherModelConfig has no provider resource
# (hashicorp/terraform-provider-google#24092). After `apply`, run the command
# in the `enable_logging_command` output to point Vertex at this dataset.

terraform {
  # Exact pin, because a `cloud` block runs plan/apply REMOTELY: this has to
  # match the workspace's Terraform Version setting in HCP as well as the
  # local CLI, or the run errors before it plans. Loosen to `~> 1.16` if that
  # coupling gets in the way.
  required_version = "1.16.3"

  cloud {
    # Your HCP Terraform organization NAME -- the /app/<name>/ segment of the
    # app.terraform.io URL. Not the `org-...` External ID from Settings ->
    # General; the cloud block does not take that.
    organization = "REPLACE_WITH_HCP_ORG"

    workspaces {
      name = "REPLACE_WITH_HCP_WORKSPACE"
    }
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

# No credentials argument on purpose: HCP Terraform injects a short-lived
# token per run via workload identity federation. Setting GOOGLE_CREDENTIALS
# or GOOGLE_APPLICATION_CREDENTIALS in the workspace breaks that -- see
# terraform/README.md.
provider "google" {
  project = var.project_id
}

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  # Vertex writes the logs as the Vertex AI service agent. Note this is NOT
  # the Reasoning Engine agent (…@gcp-sa-aiplatform-re…) that Agent Runtime
  # deployments use. Override with var.vertex_service_agent if a write ever
  # fails with a permission error naming a different principal.
  vertex_service_agent = coalesce(
    var.vertex_service_agent,
    "service-${data.google_project.this.number}@gcp-sa-aiplatform.iam.gserviceaccount.com",
  )
}

resource "google_bigquery_dataset" "claude_logs" {
  project     = var.project_id
  dataset_id  = var.dataset_id
  location    = var.dataset_location
  description = "Vertex request/response logs for Claude. Rows contain prompts and completions."

  # 0 means keep forever. Anything else expires tables after N days, which is
  # the lever for how long prompt/completion text is retained.
  default_table_expiration_ms = var.retention_days == 0 ? null : var.retention_days * 24 * 60 * 60 * 1000

  labels = var.labels
}

resource "google_bigquery_dataset_iam_member" "vertex_writer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.claude_logs.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${local.vertex_service_agent}"
}
