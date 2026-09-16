@description('Existing managed Container Apps environment resource ID')
param environmentId string
@description('Existing user-assigned identity with AcrPull and Key Vault secrets permissions')
param identityId string
param location string = resourceGroup().location
param appName string = 'customer-intelligence-staging'
param image string
param registryServer string
@description('Versionless Key Vault HTTPS base URL, without trailing slash')
param vaultUrl string
@allowed(['demo', 'openai'])
param modelMode string = 'demo'
param openaiModel string = 'gpt-4.1-mini'

var secrets = [
  { name: 'database-url', keyVaultUrl: '${vaultUrl}/secrets/cia-database-url', identity: identityId }
  { name: 'sql-database-url', keyVaultUrl: '${vaultUrl}/secrets/cia-sql-database-url', identity: identityId }
  { name: 'reader-api-key', keyVaultUrl: '${vaultUrl}/secrets/cia-reader-api-key', identity: identityId }
  { name: 'reviewer-api-key', keyVaultUrl: '${vaultUrl}/secrets/cia-reviewer-api-key', identity: identityId }
]
var modelSecrets = modelMode == 'openai' ? [
  { name: 'openai-api-key', keyVaultUrl: '${vaultUrl}/secrets/cia-openai-api-key', identity: identityId }
] : []
var runtimeEnv = [
  { name: 'APP_ENV', value: 'staging' }
  { name: 'MODEL_MODE', value: modelMode }
  { name: 'OPENAI_MODEL', value: openaiModel }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'SQL_DATABASE_URL', secretRef: 'sql-database-url' }
  { name: 'READER_API_KEY', secretRef: 'reader-api-key' }
  { name: 'REVIEWER_API_KEY', secretRef: 'reviewer-api-key' }
]
var modelEnv = modelMode == 'openai' ? [{ name: 'OPENAI_API_KEY', secretRef: 'openai-api-key' }] : []

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Multiple'
      secrets: concat(secrets, modelSecrets)
      registries: [{ server: registryServer, identity: identityId }]
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        transport: 'auto'
      }
    }
    template: {
      containers: [{
        name: 'api'
        image: image
        env: concat(runtimeEnv, modelEnv)
        resources: { cpu: json('0.5'), memory: '1Gi' }
        probes: [
          { type: 'Startup', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 5, timeoutSeconds: 6, failureThreshold: 24 }
          { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 10, timeoutSeconds: 6, failureThreshold: 3 }
          { type: 'Liveness', tcpSocket: { port: 8000 }, periodSeconds: 30, timeoutSeconds: 3, failureThreshold: 3 }
        ]
      }]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}
output appUrl string = 'https://${app.properties.configuration.ingress.fqdn}'
