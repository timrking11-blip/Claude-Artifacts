# terraform/

Creates the BigQuery dataset that Vertex writes Claude request/response logs
into, managed in **HCP Terraform**, authenticated to Google Cloud with
**workload identity federation** — no service account keys anywhere.

It deliberately does **not** configure the logging itself. That is
`setPublisherModelConfig`, which has no Terraform resource
([#24092](https://github.com/hashicorp/terraform-provider-google/issues/24092)).
Terraform owns the destination; the script points the model at it. After
`apply`, `terraform output enable_logging_command` prints the exact next
command.

## One-time setup

### Which workspace this targets

Set `organization` and `workspaces.name` in the `cloud` block of `main.tf`.
They are easy to mix up: the organization is the `/app/<name>/` segment of
the app.terraform.io URL, and the `org-…` string under Settings → General is
its External ID, which the `cloud` block does **not** take. To list both
after `terraform login`:

```bash
curl -s -H "Authorization: Bearer $(jq -r '.credentials["app.terraform.io"].token' ~/.terraform.d/credentials.tfrc.json)" \
  https://app.terraform.io/api/v2/organizations | jq -r '.data[].attributes.name'
```

### 1. Workload identity federation, on the GCP side

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
   `assertion.terraform_organization_name == "<your org>" && assertion.terraform_workspace_name == "<your workspace>"`,
   matching the `cloud` block exactly. Get this wrong and it fails *closed*:
   the run dies in token exchange, with a credentials error rather than a
   Terraform one.
4. Create a service account for the runs and grant it what this root needs
   (BigQuery dataset creation and IAM on the project; `roles/bigquery.admin`
   is the blunt version — narrow it if you prefer).
5. Bind the pool principal to that service account with
   `roles/iam.workloadIdentityUser`.

### 2. Workspace environment variables

In the workspace, as **environment** variables (not Terraform variables):

| Variable | Value |
|---|---|
| `TFC_GCP_PROVIDER_AUTH` | `true` |
| `TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL` | the service account from step 1.4 |
| `TFC_GCP_WORKLOAD_PROVIDER_NAME` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL>/providers/<PROVIDER>` |

Do **not** set `GOOGLE_CREDENTIALS` or `GOOGLE_APPLICATION_CREDENTIALS` in
the workspace — they conflict with dynamic credentials and will break the run.

### Why not Infra Manager?

Fair question, since all of the above exists only to let a runner *outside*
Google Cloud authenticate in. Google's
[Infrastructure Manager](https://cloud.google.com/infrastructure-manager/docs)
runs Terraform inside the project as a service account, which would delete
this entire section — no pool, no OIDC provider, no attribute condition, no
`TFC_GCP_*` variables.

It was considered and not taken: HCP keeps the run history, policy hooks and
UI, and leaves the `required_version` pin above valid. Infra Manager supports
a conservative set of Terraform versions — run `gcloud infra-manager
terraform-versions list` to see whether it offers the pinned one at all.

If you do switch, it is a replacement rather than an addition: Infra Manager
keeps its own GCS-backed state, so the `cloud {}` block in `main.tf` comes
**out**. Do not try to run both.

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

Under **Terraform v1.16.3** — the version `required_version` pins, fetched
from releases.hashicorp.com to check the pin names a real release —
`terraform fmt -check` is clean and `terraform validate` passes against the
real `hashicorp/google` 6.50.0 schema. The provider comes from a local
filesystem mirror because `registry.terraform.io` is unreachable from the
environment this was authored in.

`init`/`plan` against HCP Terraform were **not** run: they need credentials
that belong on your machine, and nowhere else. On the first `plan`, expect
**2 to add, 0 to change, 0 to destroy**. If it shows anything more, stop —
the workspace is holding state for something else, and applying would act
on it.
