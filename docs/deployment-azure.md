# Azure staging deployment runbook

These are preparation assets. No Azure deployment, paid resource creation, identity assignment or GitHub configuration was performed during the local build. The templates compile locally; live provisioning requires your subscription, approved budget, resource names, region and authorization.

## Target topology

```mermaid
flowchart LR
    GH[Successful main push CI] --> OIDC[GitHub OIDC identity]
    OIDC --> ACR[Azure Container Registry: commit-SHA image]
    OIDC --> MIG[Privileged manual migration job]
    OIDC --> REV[Candidate Container Apps revision]
    REV --> SMOKE[Revision-specific deterministic smoke test]
    SMOKE --> TRAFFIC[Promote traffic after success]
    REV --> DB[(Azure Database for PostgreSQL)]
    KV[Key Vault secrets] --> REV
    KV --> MIG
    JOB[Daily 06:00 UTC intelligence job] --> DB
    DB --> BI[Power BI via approved network path]
```

Microsoft documents [OIDC authentication](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect), [revision deployments and SHA image tags](https://learn.microsoft.com/en-us/azure/container-apps/github-actions), [health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes), and [job execution status](https://learn.microsoft.com/en-us/cli/azure/containerapp/job/execution?view=azure-cli-latest). This project uses OIDC rather than the password-based examples found in some older deployment guides.

## Prerequisites and network choices

Use a dedicated staging resource group, Container Apps environment, private container registry and PostgreSQL Flexible Server. Prefer VNet integration, private PostgreSQL connectivity and an approved Power BI gateway path. For a short-lived public-network synthetic demo, restrict PostgreSQL firewall rules to your known administrator and application egress IPs; never enable a blanket internet rule. Decide the region and SKU using your subscription's availability and budget rather than hardcoded assumptions.

Azure CLI with the Container Apps extension, Bicep and Docker are required on the operator machine. Configuration-only examples below use bash and placeholders; replace every capitalized placeholder. Azure CLI resource creation incurs costs and is intentionally not executed by the local setup scripts.

```bash
az login
az account set --subscription SUBSCRIPTION_ID
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az group create --name RESOURCE_GROUP --location REGION
az acr create --resource-group RESOURCE_GROUP --name UNIQUE_REGISTRY --sku Basic --admin-enabled false
az containerapp env create --resource-group RESOURCE_GROUP --name ENVIRONMENT_NAME --location REGION
# Configure VNet/private DNS at environment creation for private-network deployments.
```

Create PostgreSQL Flexible Server in your chosen network through the Azure portal or reviewed infrastructure workflow. Set version 17+, enforce TLS, configure backups/retention, create database `customer_intelligence`, and retain the schema owner in Key Vault. The application must not run as the Azure server administrator. Inspect the server's current CA guidance and network settings before connecting. Use connection URLs of the form:

```text
postgresql://cia_app:URL_ENCODED_PASSWORD@SERVER.postgres.database.azure.com:5432/customer_intelligence?sslmode=verify-full&sslrootcert=system
postgresql://cia_analyst:URL_ENCODED_PASSWORD@SERVER.postgres.database.azure.com:5432/customer_intelligence?sslmode=verify-full&sslrootcert=system
```

The container's libpq and system trust store must support `sslrootcert=system`; alternatively mount the current CA bundle and set `sslrootcert` to its absolute path. `verify-full` checks the server hostname as well as trust. Do not use `sslmode=disable` or `require` as a substitute for certificate verification. The API validates this configuration at startup.

## Identities and secrets

Create separate user-assigned identities for API/scan runtime and migrations. Grant both `AcrPull` on the specific registry. Grant runtime access only to its database, reader/reviewer and optional OpenAI secrets. Grant migration identity access to the owner URL and database-role passwords as well. The API Bicep template never references the owner URL.

Create a Key Vault with RBAC authorization and the following secrets using secure portal input or `az keyvault secret set --file` from an ignored, access-controlled temporary file. Do not put literal values in commands, GitHub variables, source files or committed parameter JSON.

| Secret name | Used by |
|---|---|
| `cia-admin-database-url` | Migration job only |
| `cia-database-url` | API, scan and migration jobs; `cia_app` role |
| `cia-sql-database-url` | API only; `cia_analyst` role |
| `cia-app-db-password` | Role provisioning in migration job |
| `cia-analyst-db-password` | Role provisioning in migration job |
| `cia-reader-api-key` | API and transient deployment smoke test |
| `cia-reviewer-api-key` | API only |
| `cia-openai-api-key` | Optional; only for `MODEL_MODE=openai` |

Reader/reviewer keys must be distinct, random and at least 32 characters. Database-role password secrets must match their URLs. Store versionless secret URIs in Bicep; Azure resolves values at runtime. Record a rotation/revision-restart procedure for your environment.

## Initial bootstrap

1. Build and push an initial reviewed image to ACR using a commit SHA tag. Grant runtime and migration identities image-pull access.
2. Fill the placeholder parameter file outside Git. The app template needs `environmentId`, `identityId`, `image`, `registryServer`, and `vaultUrl`; jobs also require `migrationIdentityId`.
3. Deploy the jobs first, run the manual migration job, and confirm `Succeeded`. This applies migrations, seeds synthetic data without replacing existing rows, provisions runtime roles and captures the current portfolio.
4. Deploy the app template, verify the candidate's health and metrics with the reader credential, and then configure CI/CD.

```bash
az bicep build --file infra/container-app.bicep
az bicep build --file infra/jobs.bicep
az deployment group what-if --resource-group RESOURCE_GROUP \
  --template-file infra/jobs.bicep --parameters @PRIVATE_JOBS_PARAMETERS.json
az deployment group create --resource-group RESOURCE_GROUP \
  --template-file infra/jobs.bicep --parameters @PRIVATE_JOBS_PARAMETERS.json
az containerapp job start --resource-group RESOURCE_GROUP --name cia-migrate
# Check execution status before deploying the API.
az deployment group create --resource-group RESOURCE_GROUP \
  --template-file infra/container-app.bicep --parameters @PRIVATE_APP_PARAMETERS.json
```

Jobs intentionally do not expose HTTP endpoints. The scan job runs daily at 06:00 UTC and calls `python -m scripts.run_intelligence_scan`. Its environment has only the runtime database URL; it does not need an LLM, owner password or reviewer credential. API deployment sets `APP_ENV=staging`, HTTPS-only ingress and secrets. The fixed local demo date is not deployed.

Readiness/startup probes use `/health`, including PostgreSQL connectivity. Liveness uses the TCP listener so a database outage does not cause a fleet-wide process restart loop. Start with one replica; limits and per-process counters are explicit in the architecture document.

## GitHub OIDC configuration

Create an Entra application/service principal or dedicated user-assigned deployment identity with a federated credential:

```json
{
  "name": "github-staging",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:newtocode80/customer-intelligence-agent:environment:staging",
  "audiences": ["api://AzureADTokenExchange"]
}
```

Grant the deployment identity `AcrPush` on the registry and permission to update this Container App and the two jobs. Scope Container Apps Contributor to the staging resource group or use a reviewed narrower custom role. It also needs read access to **only** `cia-reader-api-key` for smoke testing, not reviewer, owner or OpenAI secrets. Avoid subscription-wide Contributor and never create a long-lived Azure password for GitHub.

Create a GitHub environment named `staging`, restrict deployment branches to `main`, and configure reviewers if desired. Protect `main` with the CI check. Define the following non-secret repository/environment variables:

```text
AZURE_DEPLOY_ENABLED=true
AZURE_CLIENT_ID=deployment identity client ID
AZURE_TENANT_ID=tenant ID
AZURE_SUBSCRIPTION_ID=subscription ID
AZURE_RESOURCE_GROUP=staging resource group
AZURE_CONTAINER_APP=customer-intelligence-staging
AZURE_ACR_NAME=registry resource name, without .azurecr.io
AZURE_MIGRATION_JOB=cia-migrate
AZURE_SCAN_JOB=cia-intelligence-scan
AZURE_KEY_VAULT=vault resource name
```

Set `AZURE_DEPLOY_ENABLED` at **repository scope**, because it is evaluated before the environment starts. Runtime secret values stay in Key Vault. The reader key is retrieved transiently in a masked deployment shell for HTTP smoke tests and is not stored as a GitHub secret or artifact.

## What CD does

Only successful push-triggered CI on `main` from the same repository can trigger staging. Checkout uses the exact tested `head_sha`. CD downloads the Docker image artifact from that specific successful CI run, loads it and pushes the SHA-tagged image without rebuilding it. The job authenticates with OIDC (`id-token: write`), updates and runs the migration job, and waits for actual completion. A failing migration stops deployment. `actions: read` permits access to that CI artifact; it grants no repository mutation rights.

Before creating the candidate, traffic is fixed to the previously ready revision. A new SHA-suffixed revision receives revision-specific `/health`, `/metrics`, and `/customers/3/risk` smoke tests. Only success promotes traffic. On smoke failure, prior traffic is preserved; the candidate remains available for diagnosis. The daily job is updated to the same image after promotion. Runtime updates preserve existing Key Vault references.

## Rollback and operations

```bash
az containerapp revision list --resource-group RESOURCE_GROUP --name APP_NAME -o table
az containerapp revision activate --resource-group RESOURCE_GROUP --name APP_NAME --revision KNOWN_GOOD_REVISION
az containerapp ingress traffic set --resource-group RESOURCE_GROUP --name APP_NAME \
  --revision-weight KNOWN_GOOD_REVISION=100
# Align the scan job to the same known-good image after compatibility review.
az containerapp job update --resource-group RESOURCE_GROUP --name cia-intelligence-scan \
  --image REGISTRY.azurecr.io/customer-intelligence:KNOWN_GOOD_SHA
```

Rollback application traffic, not database history. Migrations must use expand/contract changes while old revisions remain possible. A destructive schema change needs its own recovery/backup plan and explicit authorization. Keep previous images and revisions until the retention window ends.

Monitor 5xx rates, latency, model failures, DB connection pressure, snapshot freshness, scan job failures and open-event volume. Configure Azure Monitor/Log Analytics alerts using approved notification destinations. A job with no baseline should yield zero events and `INSUFFICIENT_HISTORY`, not fail. Check the database snapshot history and scheduled execution logs before concluding that no customers deteriorated.

## Remaining operator actions

- Supply subscription/region/resource names, network plan and approved budget; provision resources and identity permissions.
- Populate Key Vault secrets, confirm PostgreSQL certificate validation, and run the initial owner job.
- Set GitHub OIDC/environment variables and branch protections; push the local commits to start hosted CI only when authorized.
- Run and inspect the first staging deployment and rollback rehearsal. No local compiler or workflow checker proves cloud authorization, quota or network reachability.
- Configure a Power BI credential/gateway and optionally supply an OpenAI key for separately reported live evaluations.
