# terraform/

Creates the BigQuery dataset that Vertex writes Claude request/response logs
into, managed in **HCP Terraform** (workspace
`strategic-market-insights-crm`), authenticated to Google Cloud with
**workload identity federation** — no service account keys anywhere.

It deliberately does **not** configure the logging itself. That is
`setPublisherModelConfig`, which has no Terraform resource
([#24092](https://github.com/hashicorp/terraform-provider-google/issues/24092)).
Terraform owns the destination; the script points the model at it. After
`apply`, `terraform output enable_logging_command` prints the exact next
command.

## One-time setup

### 1. Fill in the organization

`main.tf` ships `organization = "REPLACE_WITH_HCP_ORG"`. Set it to your HCP
Terraform organization name. The workspace name is already correct.

### 2. Workload identity federation, on the GCP side

This part is console/`gcloud` work rather than code: bootstrapping the pool
with Terraform would need the credentials that the pool exists to grant.

1. Create a **workload identity pool**, then an **OIDC provider** in it with
   issuer `https://app.terraform.io`.
2. Map the claims HCP Terraform sends, e.g.
   `google.subject = assertion.sub`,
   `attribute.terraform_workspace_name = assertion.terraform_workspace_name`,
   `attribute.terraform_organization_name = assertion.terraform_organization_name`.
3. Add an **attribute condition** pinning it to this organization *and*
   workspace, so no other workspace can assume the identity — e.g.
   `assertion.terraform_organization_name == "<your org>" && assertion.terraform_workspace_name == "strategic-market-insights-crm"`.
4. Create a service account for the runs and grant it what this root needs
   (BigQuery dataset creation and IAM on the project; `roles/bigquery.admin`
   is the blunt version — narrow it if you prefer).
5. Bind the pool principal to that service account with
   `roles/iam.workloadIdentityUser`.

### 3. Workspace environment variables

In the workspace, as **environment** variables (not Terraform variables):

| Variable | Value |
|---|---|
| `TFC_GCP_PROVIDER_AUTH` | `true` |
| `TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL` | the service account from step 2.4 |
| `TFC_GCP_WORKLOAD_PROVIDER_NAME` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL>/providers/<PROVIDER>` |

Do **not** set `GOOGLE_CREDENTIALS` or `GOOGLE_APPLICATION_CREDENTIALS` in
the workspace — they conflict with dynamic credentials and will break the run.

## Running it

```bash
cd terraform
terraform login            # stores a token in ~/.terraform.d — never paste it anywhere
terraform init             # generates .terraform.lock.hcl — commit it (see below)
terraform plan             # expect: 1 dataset + 1 dataset IAM member
terraform apply
terraform output enable_logging_command
```

Then run that command, and confirm with
`python python/agents/account-research/scripts/claude_request_logging.py --show`.

## Variables worth a decision

| Variable | Default | Note |
|---|---|---|
| `project_id` | — | required; the project **ID**, not the number |
| `dataset_id` | `crm` | |
| `dataset_location` | `US` | immutable after creation |
| `retention_days` | `0` (forever) | see below |
| `vertex_service_agent` | derived | override if a write is denied for a different principal |

**These rows are sensitive.** They contain the prompts sent to Claude and the
completions returned — which here means contact records from the CRM ledger
and the account briefs written about them. `dataset_location`,
`retention_days` and who can read the dataset are choices to make before
enabling logging, not after.

## The dependency lockfile

`.terraform.lock.hcl` is normally committed, and should be — but it is not in
this repo yet. The environment this was authored in cannot reach
`registry.terraform.io`, so the only lockfile it could produce held a single
`linux_amd64` hash, which would make `terraform init` fail on any other
platform. Your first `terraform init` generates a complete one: commit it, and
drop the `terraform/.terraform.lock.hcl` line from `.gitignore`.

## Verified

`terraform fmt` is clean and `terraform validate` passes against the real
`hashicorp/google` 6.50.0 schema (provider fetched from releases.hashicorp.com
into a local mirror, since the registry is unreachable from there).
`init`/`plan` against HCP Terraform were **not** run — they need the
organization name and credentials that belong on your machine.
