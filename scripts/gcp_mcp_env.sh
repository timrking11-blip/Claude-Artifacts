#!/usr/bin/env bash
# Print the environment the Google Cloud MCP entries in .mcp.json need.
# Usage:  eval "$(scripts/gcp_mcp_env.sh)" && claude
# Re-run when the token expires (1 h by default; up to 12 h with
# `gcloud auth application-default print-access-token --lifetime=43200`).
# Never prints the token to the terminal on its own -- only as an export line
# meant for eval.
set -euo pipefail

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is not installed or not on PATH. Install the Google Cloud SDK:" >&2
  echo "  https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

if ! token=$(gcloud auth application-default print-access-token 2>/dev/null); then
  echo "No Application Default Credentials. Run once:" >&2
  echo "  gcloud auth application-default login" >&2
  exit 1
fi

# GCP_PROJECT wins; otherwise fall back to gcloud's configured project.
project="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
if [ -z "$project" ] || [ "$project" = "(unset)" ]; then
  echo "No project. Set GCP_PROJECT, or: gcloud config set project <id>" >&2
  exit 1
fi
printf 'export GCP_MCP_ACCESS_TOKEN=%q\n' "$token"
printf 'export GCP_PROJECT=%q\n' "$project"
