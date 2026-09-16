#!/usr/bin/env bash
set -euo pipefail

# Called only by the gated main-branch staging workflow. Secrets stay in Azure.
for name in DEPLOY_SHA AZURE_RESOURCE_GROUP AZURE_CONTAINER_APP AZURE_ACR_NAME AZURE_MIGRATION_JOB AZURE_SCAN_JOB AZURE_KEY_VAULT; do
  if [[ -z "${!name:-}" ]]; then echo "Missing configuration: $name"; exit 1; fi
done
[[ "$DEPLOY_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo "Invalid deployment SHA"; exit 1; }
az acr login --name "$AZURE_ACR_NAME" --only-show-errors
registry=$(az acr show --name "$AZURE_ACR_NAME" --query loginServer -o tsv)
image="$registry/customer-intelligence:$DEPLOY_SHA"
docker load -i .local/deployment-image/deployment-image.tar
docker tag "customer-intelligence:$DEPLOY_SHA" "$image"
docker push "$image"

# A separately privileged, pre-provisioned job performs backward-compatible migrations.
az containerapp job update --name "$AZURE_MIGRATION_JOB" --resource-group "$AZURE_RESOURCE_GROUP" --image "$image" --only-show-errors -o none
execution=$(az containerapp job start --name "$AZURE_MIGRATION_JOB" --resource-group "$AZURE_RESOURCE_GROUP" --query name -o tsv)
status=Running
for attempt in $(seq 1 30); do
  status=$(az containerapp job execution show --name "$AZURE_MIGRATION_JOB" --resource-group "$AZURE_RESOURCE_GROUP" --job-execution-name "$execution" --query properties.status -o tsv)
  [[ "$status" == "Succeeded" ]] && break
  [[ "$status" == "Failed" ]] && { echo "Migration job failed"; exit 1; }
  sleep 10
done
[[ "$status" == "Succeeded" ]] || { echo "Migration job timed out"; exit 1; }

previous=$(az containerapp show --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --query properties.latestReadyRevisionName -o tsv)
az containerapp revision set-mode --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --mode multiple -o none
if [[ -n "$previous" ]]; then
  az containerapp ingress traffic set --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --revision-weight "$previous=100" -o none
fi
suffix="sha-${DEPLOY_SHA:0:12}"
revision="$AZURE_CONTAINER_APP--$suffix"
az containerapp update --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --image "$image" --revision-suffix "$suffix" --only-show-errors -o none
fqdn=$(az containerapp revision show --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --revision "$revision" --query properties.fqdn -o tsv)

# Fetch only the reader token transiently; it is masked, not stored in GitHub secrets/artifacts.
reader=$(az keyvault secret show --vault-name "$AZURE_KEY_VAULT" --name cia-reader-api-key --query value -o tsv)
echo "::add-mask::$reader"
if ! READER_API_KEY="$reader" python scripts/smoke_test.py --base-url "https://$fqdn" --attempts 20; then
  unset reader
  if [[ -n "$previous" ]]; then
    az containerapp ingress traffic set --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --revision-weight "$previous=100" -o none
  fi
  echo "Candidate failed smoke testing; prior revision retains traffic"
  exit 1
fi
unset reader
az containerapp ingress traffic set --name "$AZURE_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" --revision-weight "$revision=100" -o none
az containerapp job update --name "$AZURE_SCAN_JOB" --resource-group "$AZURE_RESOURCE_GROUP" --image "$image" --only-show-errors -o none
echo "Deployed and verified revision $revision; previous revision $previous is available for rollback"
