param environmentId string
param identityId string
param migrationIdentityId string
param location string = resourceGroup().location
param image string
param registryServer string
param vaultUrl string
param scanJobName string = 'cia-intelligence-scan'
param migrationJobName string = 'cia-migrate'

resource scan 'Microsoft.App/jobs@2024-03-01' = {
  name: scanJobName
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 300
      replicaRetryLimit: 1
      scheduleTriggerConfig: { cronExpression: '0 6 * * *', parallelism: 1, replicaCompletionCount: 1 }
      secrets: [{ name: 'database-url', keyVaultUrl: '${vaultUrl}/secrets/cia-database-url', identity: identityId }]
      registries: [{ server: registryServer, identity: identityId }]
    }
    template: {
      containers: [{
        name: 'scan'
        image: image
        command: ['python', '-m', 'scripts.run_intelligence_scan']
        env: [
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'REQUIRE_DATABASE_TLS', value: 'true' }
        ]
        resources: { cpu: json('0.5'), memory: '1Gi' }
      }]
    }
  }
}

resource migration 'Microsoft.App/jobs@2024-03-01' = {
  name: migrationJobName
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${migrationIdentityId}': {} } }
  properties: {
    environmentId: environmentId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 300
      replicaRetryLimit: 0
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      secrets: [
        { name: 'admin-url', keyVaultUrl: '${vaultUrl}/secrets/cia-admin-database-url', identity: migrationIdentityId }
        { name: 'database-url', keyVaultUrl: '${vaultUrl}/secrets/cia-database-url', identity: migrationIdentityId }
        { name: 'app-password', keyVaultUrl: '${vaultUrl}/secrets/cia-app-db-password', identity: migrationIdentityId }
        { name: 'analyst-password', keyVaultUrl: '${vaultUrl}/secrets/cia-analyst-db-password', identity: migrationIdentityId }
      ]
      registries: [{ server: registryServer, identity: migrationIdentityId }]
    }
    template: {
      containers: [{
        name: 'migrate'
        image: image
        command: ['python', '-m', 'scripts.bootstrap']
        env: [
          { name: 'ADMIN_DATABASE_URL', secretRef: 'admin-url' }
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'APP_DB_PASSWORD', secretRef: 'app-password' }
          { name: 'ANALYST_DB_PASSWORD', secretRef: 'analyst-password' }
          { name: 'REQUIRE_DATABASE_TLS', value: 'true' }
        ]
        resources: { cpu: json('0.5'), memory: '1Gi' }
      }]
    }
  }
}
