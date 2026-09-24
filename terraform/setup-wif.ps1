<#
.SYNOPSIS
  One-time GCP setup so HCP Terraform can authenticate without a key file.

.DESCRIPTION
  Creates a workload identity pool and OIDC provider trusting app.terraform.io,
  a service account for the runs, and the bindings between them. Prints the
  three TFC_GCP_* environment variables to set on the workspace.

  Bootstrapping this with Terraform would need the credentials the pool exists
  to grant, which is why it is a script.

  Safe to re-run: every step is skipped if the resource already exists.

.EXAMPLE
  .\setup-wif.ps1 -ProjectId my-project -HcpOrg my-org -HcpWorkspace my-workspace -DryRun
  .\setup-wif.ps1 -ProjectId my-project -HcpOrg my-org -HcpWorkspace my-workspace
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$ProjectId,
  [Parameter(Mandatory)][string]$HcpOrg,
  [Parameter(Mandatory)][string]$HcpWorkspace,
  [string]$PoolId = "hcp-terraform",
  [string]$ProviderId = "hcp-terraform-oidc",
  [string]$SaName = "hcp-terraform-runner",
  # roles/browser is not optional: the root's `data "google_project"` needs
  # resourcemanager.projects.get, which roles/bigquery.admin does NOT include.
  [string[]]$Roles = @("roles/bigquery.admin", "roles/browser"),
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# $ErrorActionPreference does not apply to native commands, so every gcloud
# call checks $LASTEXITCODE itself rather than running on after a failure.
function Invoke-GCloud {
  param([string]$Description, [string[]]$Arguments, [switch]$Quiet)
  Write-Host "`n== $Description" -ForegroundColor Cyan
  # Quote args containing spaces or shell metacharacters so the dry-run line
  # is copy-pasteable. Execution passes the array through untouched.
  $rendered = "gcloud " + (($Arguments | ForEach-Object {
    if ($_ -match '[\s&|<>()]') { "'" + $_.Replace("'", "''") + "'" } else { $_ }
  }) -join " ")
  if ($DryRun) { Write-Host "   $rendered" -ForegroundColor DarkGray; return }
  Write-Verbose $rendered
  $output = & gcloud @Arguments 2>&1
  if ($LASTEXITCODE -ne 0) {
    $output | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    throw "Failed (exit $LASTEXITCODE): $rendered"
  }
  if (-not $Quiet) { $output | ForEach-Object { Write-Host "   $_" -ForegroundColor DarkGray } }
}

# Probe for an existing resource. Non-zero exit means "not there".
function Test-GCloudResource {
  param([string[]]$Arguments)
  & gcloud @Arguments *>$null
  return $LASTEXITCODE -eq 0
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud is not on PATH. Install: https://cloud.google.com/sdk/docs/install"
}

$ProjectNumber = (& gcloud projects describe $ProjectId --format="value(projectNumber)")
if ($LASTEXITCODE -ne 0 -or -not $ProjectNumber) {
  throw "Could not read the project number for '$ProjectId'. Wrong ID, or no access?"
}
$ProjectNumber = $ProjectNumber.Trim()

$SaEmail   = "$SaName@$ProjectId.iam.gserviceaccount.com"
$PoolRef   = "projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId"
$Provider  = "$PoolRef/providers/$ProviderId"
# Scoped to ONE workspace: no other workspace in the org can assume this identity.
$Principal = "principalSet://iam.googleapis.com/$PoolRef/attribute.terraform_workspace_name/$HcpWorkspace"

Write-Host "project      : $ProjectId ($ProjectNumber)"
Write-Host "organization : $HcpOrg"
Write-Host "workspace    : $HcpWorkspace"
Write-Host "service acct : $SaEmail"
if ($DryRun) { Write-Host "mode         : DRY RUN, nothing will be created" -ForegroundColor Yellow }

Invoke-GCloud "Enable the APIs this needs" @(
  "services", "enable",
  "iamcredentials.googleapis.com", "sts.googleapis.com",
  "cloudresourcemanager.googleapis.com", "bigquery.googleapis.com",
  "--project=$ProjectId"
)

if (Test-GCloudResource @("iam", "workload-identity-pools", "describe", $PoolId,
                          "--location=global", "--project=$ProjectId")) {
  Write-Host "`n== Pool '$PoolId' already exists, skipping" -ForegroundColor DarkYellow
} else {
  Invoke-GCloud "Create the workload identity pool" @(
    "iam", "workload-identity-pools", "create", $PoolId,
    "--location=global", "--display-name=HCP Terraform", "--project=$ProjectId"
  )
}

if (Test-GCloudResource @("iam", "workload-identity-pools", "providers", "describe", $ProviderId,
                          "--workload-identity-pool=$PoolId", "--location=global",
                          "--project=$ProjectId")) {
  Write-Host "`n== Provider '$ProviderId' already exists, skipping" -ForegroundColor DarkYellow
} else {
  # The attribute condition is the security boundary. Without it, ANY HCP
  # Terraform workspace anywhere could exchange a token for this identity.
  $mapping = @(
    "google.subject=assertion.sub",
    "attribute.terraform_organization_name=assertion.terraform_organization_name",
    "attribute.terraform_workspace_name=assertion.terraform_workspace_name",
    "attribute.terraform_project_name=assertion.terraform_project_name"
  ) -join ","
  $condition = "assertion.terraform_organization_name=='$HcpOrg' && " +
               "assertion.terraform_workspace_name=='$HcpWorkspace'"
  Invoke-GCloud "Create the OIDC provider trusting app.terraform.io" @(
    "iam", "workload-identity-pools", "providers", "create-oidc", $ProviderId,
    "--workload-identity-pool=$PoolId", "--location=global", "--project=$ProjectId",
    "--issuer-uri=https://app.terraform.io",
    "--attribute-mapping=$mapping",
    "--attribute-condition=$condition"
  )
}

if (Test-GCloudResource @("iam", "service-accounts", "describe", $SaEmail, "--project=$ProjectId")) {
  Write-Host "`n== Service account already exists, skipping" -ForegroundColor DarkYellow
} else {
  Invoke-GCloud "Create the run service account" @(
    "iam", "service-accounts", "create", $SaName,
    "--display-name=HCP Terraform runner", "--project=$ProjectId"
  )
}

foreach ($role in $Roles) {
  Invoke-GCloud "Grant $role on the project" @(
    "projects", "add-iam-policy-binding", $ProjectId,
    "--member=serviceAccount:$SaEmail", "--role=$role", "--condition=None"
  ) -Quiet
}

Invoke-GCloud "Let the pool impersonate the service account" @(
  "iam", "service-accounts", "add-iam-policy-binding", $SaEmail,
  "--member=$Principal", "--role=roles/iam.workloadIdentityUser",
  "--project=$ProjectId"
) -Quiet

Write-Host "`n--------------------------------------------------------------" -ForegroundColor Green
Write-Host "Set these as ENVIRONMENT variables on the '$HcpWorkspace' workspace" -ForegroundColor Green
Write-Host "(Variables tab -> category 'Environment', NOT 'Terraform'):" -ForegroundColor Green
Write-Host "--------------------------------------------------------------"
Write-Host "TFC_GCP_PROVIDER_AUTH              = true"
Write-Host "TFC_GCP_RUN_SERVICE_ACCOUNT_EMAIL  = $SaEmail"
Write-Host "TFC_GCP_WORKLOAD_PROVIDER_NAME     = $Provider"
Write-Host ""
Write-Host "Do NOT also set GOOGLE_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS -- they"
Write-Host "override dynamic credentials and the run will fail confusingly."
Write-Host ""
Write-Host "If the run fails in token exchange with an audience error, add:"
Write-Host "TFC_GCP_WORKLOAD_IDENTITY_AUDIENCE = //iam.googleapis.com/$Provider"
