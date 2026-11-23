"""Prepare an explicit Azure recovery/monitoring plan. Never provisions by itself."""
import json
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parent
ref=lambda kind,name: "[resourceId('"+kind+"', '"+name+"')]"
variables={'storage':'leaguebackupdedf75','workspace':'league-ops-logs','insights':'league-paper-monitor',
           'test':'league-paper-readiness','group':'league-paper-email','alert':'league-paper-unavailable'}
r=[]
r.append({'type':'Microsoft.Storage/storageAccounts','apiVersion':'2023-05-01','name':variables['storage'],
          'location':"[parameters('location')]",'sku':{'name':'Standard_LRS'},'kind':'StorageV2',
          'tags':{'purpose':'league-paper-recovery'},'properties':{'accessTier':'Hot','minimumTlsVersion':'TLS1_2',
          'supportsHttpsTrafficOnly':True,'allowBlobPublicAccess':False,'allowSharedKeyAccess':False,
          'defaultToOAuthAuthentication':True,'allowCrossTenantReplication':False}})
r.append({'type':'Microsoft.Storage/storageAccounts/blobServices','apiVersion':'2023-05-01',
          'name':variables['storage']+'/default','dependsOn':[ref('Microsoft.Storage/storageAccounts',variables['storage'])],
          'properties':{'isVersioningEnabled':True,'deleteRetentionPolicy':{'enabled':True,'days':7,'allowPermanentDelete':False},
                        'containerDeleteRetentionPolicy':{'enabled':True,'days':7}}})
r.append({'type':'Microsoft.Storage/storageAccounts/blobServices/containers','apiVersion':'2023-05-01',
          'name':variables['storage']+'/default/paper-recovery','dependsOn':[ref('Microsoft.Storage/storageAccounts/blobServices',variables['storage']+"', 'default")],
          'properties':{'publicAccess':'None'}})
r.append({'type':'Microsoft.Storage/storageAccounts/managementPolicies','apiVersion':'2023-05-01',
          'name':variables['storage']+'/default','dependsOn':[ref('Microsoft.Storage/storageAccounts',variables['storage'])],
          'properties':{'policy':{'rules':[{'enabled':True,'name':'seven-day-recovery','type':'Lifecycle',
          'definition':{'filters':{'blobTypes':['blockBlob'],'prefixMatch':['paper-recovery/accounts/']},
          'actions':{'baseBlob':{'delete':{'daysAfterModificationGreaterThan':7}},
                     'version':{'delete':{'daysAfterCreationGreaterThan':7}}}}}]}}})
r.append({'type':'Microsoft.OperationalInsights/workspaces','apiVersion':'2022-10-01','name':variables['workspace'],
          'location':"[parameters('location')]",'tags':{'purpose':'league-paper-recovery'},
          'properties':{'sku':{'name':'PerGB2018'},'retentionInDays':30,'workspaceCapping':{'dailyQuotaGb':.023}}})
r.append({'type':'Microsoft.Insights/components','apiVersion':'2020-02-02','name':variables['insights'],
          'location':"[parameters('location')]",'kind':'web','tags':{'purpose':'league-paper-recovery'},
          'dependsOn':[ref('Microsoft.OperationalInsights/workspaces',variables['workspace'])],
          'properties':{'Application_Type':'web','WorkspaceResourceId':ref('Microsoft.OperationalInsights/workspaces',variables['workspace']),
                        'DisableLocalAuth':True,'RetentionInDays':30}})
r.append({'type':'Microsoft.Insights/actionGroups','apiVersion':'2023-01-01','name':variables['group'],'location':'global',
          'properties':{'groupShortName':'LeaguePaper','enabled':True,'emailReceivers':[{'name':'Owner',
          'emailAddress':"[parameters('alertEmail')]",'useCommonAlertSchema':True}]}})
guid=str(uuid.uuid5(uuid.NAMESPACE_URL,'league-paper-readiness'))
xml='<WebTest Name="League paper readiness" Id="'+guid+'" Enabled="True" CssProjectStructure="" CssIteration="" Timeout="30" WorkItemIds="" xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010"><Items><Request Method="GET" Version="1.1" Url="https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com/readyz" ThinkTime="0" Timeout="30" ParseDependentRequests="False" FollowRedirects="False" RecordResult="True" Cache="False" ResponseTimeGoal="0" Encoding="utf-8" ExpectedHttpStatusCode="200" ExpectedResponseUrl="" ReportingName="" IgnoreHttpStatusCode="False" /></Items></WebTest>'
r.append({'type':'Microsoft.Insights/webtests','apiVersion':'2015-05-01','name':variables['test'],'location':"[parameters('location')]",'kind':'ping',
          'dependsOn':[ref('Microsoft.Insights/components',variables['insights'])],
          'tags':{"[concat('hidden-link:', resourceId('Microsoft.Insights/components', 'league-paper-monitor'))]":'Resource'},
          'properties':{'Name':'League paper readiness','SyntheticMonitorId':variables['test'],'Kind':'ping','Frequency':300,
          'Enabled':True,'Timeout':30,'RetryEnabled':True,'Description':'Paper readiness only; no private account details.',
          'Locations':[{'Id':name} for name in ['apac-hk-hkn-azr','apac-sg-sin-azr','emea-nl-ams-azr','emea-gb-db3-azr','us-va-ash-azr']],
          'Configuration':{'WebTest':xml}}})
r.append({'type':'Microsoft.Insights/metricAlerts','apiVersion':'2018-03-01','name':variables['alert'],'location':'global',
          'dependsOn':[ref('Microsoft.Insights/webtests',variables['test']),ref('Microsoft.Insights/actionGroups',variables['group'])],
          'properties':{'description':'Last of Our League paper engine is unavailable or not ready. No broker orders are enabled.',
          'severity':1,'enabled':True,'evaluationFrequency':'PT1M','windowSize':'PT5M','autoMitigate':True,
          'scopes':[ref('Microsoft.Insights/webtests',variables['test']),ref('Microsoft.Insights/components',variables['insights'])],
          'criteria':{'odata.type':'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria',
          'webTestId':ref('Microsoft.Insights/webtests',variables['test']),
          'componentId':ref('Microsoft.Insights/components',variables['insights']),'failedLocationCount':3},
          'actions':[{'actionGroupId':ref('Microsoft.Insights/actionGroups',variables['group'])}]}})
plan={'$schema':'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#','contentVersion':'1.0.0.0',
      'parameters':{'location':{'type':'string','defaultValue':'indiasouthcentral'},'alertEmail':{'type':'secureString'}},
      'resources':r,'outputs':{'storageName':{'type':'string','value':variables['storage']}}}
(ROOT/'recovery-monitoring.arm.json').write_text(json.dumps(plan,indent=2)+'\n')
print('Prepared private Blob recovery, 7-day lifecycle, low-quota monitoring, email action group and 5-minute external readiness checks.')
print('No resources created. Ping tests are currently free but retire September 2028. Storage, logs and alerts can consume student credits.')
