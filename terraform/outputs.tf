output "dataset_id" {
  description = "The dataset that was created."
  value       = google_bigquery_dataset.claude_logs.dataset_id
}

output "dataset_uri" {
  description = "The bq:// prefix Vertex logging writes under."
  value       = "bq://${var.project_id}.${google_bigquery_dataset.claude_logs.dataset_id}"
}

output "vertex_writer" {
  description = "Service account granted dataEditor on the dataset."
  value       = local.vertex_service_agent
}

output "enable_logging_command" {
  description = "Run this next: Terraform cannot configure the logging itself (#24092)."
  value = join(" ", [
    "python python/agents/account-research/scripts/claude_request_logging.py",
    "--enable",
    "--dataset ${google_bigquery_dataset.claude_logs.dataset_id}",
    "--table claude_request_response",
  ])
}
