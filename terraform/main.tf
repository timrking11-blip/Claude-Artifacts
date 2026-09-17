# Destination for Vertex request/response logging of the Claude model.
#
# Terraform owns the destination; it cannot own the logging configuration
# itself -- setPublisherModelConfig has no provider resource
# (hashicorp/terraform-provider-google#24092). After `apply`, run the command
# in the `enable_logging_command` output to point Vertex at this dataset.

terraform {
  required_version = ">= 1.9"

  cloud {
    # The HCP Terraform organization that owns the workspace below.
    organization = "REPLACE_WITH_HCP_ORG"

    workspaces {
      name = "strategic-market-insights-crm"
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
