# Auditoria Codigo - 2026-04-30

- Total incidencias ruff: 213
- Scope: app, tests, scripts

## Conteo por regla
- F401: 127
- W293: 48
- F841: 11
- F811: 10
- F601: 5
- F821: 5
- W191: 3
- W292: 2
- F541: 1
- W291: 1

## Listado completo
### F401
- app/api/v1/endpoints/auth.py:13 - `app.services.auth_service.issue_password_reset_token` imported but unused
- app/api/v1/endpoints/auth.py:14 - `app.services.auth_service.resolve_sso_organization_id` imported but unused
- app/api/v1/endpoints/auth.py:15 - `app.services.auth_service.validate_https_discovery_url` imported but unused
- app/api/v1/endpoints/jira_integration.py:22 - `pydantic.HttpUrl` imported but unused
- app/api/v1/endpoints/jira_integration.py:29 - `app.models.jira_integration.JiraFieldMap` imported but unused
- app/api/v1/endpoints/jira_integration.py:38 - `app.services.service_desk.jira_sync_service.pull_jira_issue` imported but unused
- app/api/v1/endpoints/pipeline.py:1 - `fastapi.HTTPException` imported but unused
- app/api/v1/endpoints/predictions.py:13 - `fastapi.Body` imported but unused
- app/api/v1/endpoints/predictions.py:13 - `fastapi.HTTPException` imported but unused
- app/api/v1/endpoints/predictions.py:15 - `typing.Dict` imported but unused
- app/api/v1/endpoints/predictions.py:15 - `typing.Any` imported but unused
- app/api/v1/endpoints/predictions.py:16 - `json` imported but unused
- app/api/v1/endpoints/service_desk/alert_correlation.py:55 - `app.services.service_desk.alert_correlation_service._PRIORITY_NUM` imported but unused
- app/api/v1/endpoints/service_desk/assets.py:7 - `fastapi.Body` imported but unused
- app/api/v1/endpoints/service_desk/assets.py:7 - `fastapi.HTTPException` imported but unused
- app/api/v1/endpoints/service_desk/change_impact.py:18 - `fastapi.Body` imported but unused
- app/api/v1/endpoints/service_desk/incident_assignment.py:10 - `typing.Any` imported but unused
- app/api/v1/endpoints/service_desk/incident_assignment.py:12 - `fastapi.HTTPException` imported but unused
- app/api/v1/endpoints/service_desk/multichannel.py:7 - `fastapi.Body` imported but unused
- app/api/v1/endpoints/service_desk/multichannel.py:7 - `fastapi.Query` imported but unused
- app/api/v1/endpoints/service_desk/predictive.py:5 - `typing.Optional` imported but unused
- app/api/v1/endpoints/service_desk/predictive.py:8 - `pydantic.BaseModel` imported but unused
- app/api/v1/endpoints/service_desk/predictive.py:84 - `app.models.service_desk.TicketStatus` imported but unused
- app/api/v1/endpoints/service_desk/predictive.py:85 - `sqlalchemy.func` imported but unused
- app/api/v1/endpoints/service_desk/problem_management.py:389 - `app.models.service_desk.ProblemRcaTemplate` imported but unused
- app/api/v1/endpoints/service_desk/sd_reports.py:15 - `typing.Optional` imported but unused
- app/api/v1/endpoints/service_desk/smart_catalog.py:7 - `fastapi.Body` imported but unused
- app/api/v1/endpoints/service_desk/tickets.py:46 - `app.services.service_desk.workload_service.auto_assign_ticket_command` imported but unused
- app/api/v1/endpoints/service_desk/voice_agent.py:192 - `urllib.parse.urlencode` imported but unused
- app/api/v1/routers/auth_core.py:50 - `app.services.auth_service.create_ephemeral_token` imported but unused
- app/api/v1/routers/auth_mfa.py:4 - `fastapi.status` imported but unused
- app/api/v1/routers/auth_mfa.py:16 - `app.schemas.users.UserPublic` imported but unused
- app/api/v1/routers/auth_saml.py:4 - `fastapi.status` imported but unused
- app/api/v1/routers/auth_sessions.py:12 - `app.services.session_security.revoke_session_by_jti` imported but unused
- app/api/v1/routers/auth_sso.py:4 - `fastapi.status` imported but unused
- app/api/v1/routers/auth_sso.py:6 - `typing.Optional` imported but unused
- app/api/v1/routers/auth_sso.py:20 - `app.models.user.User` imported but unused
- app/api/v1/routers/auth_sso.py:25 - `app.services.auth_service.client_ip` imported but unused
- app/api/v1/routers/auth_sso.py:26 - `app.services.auth_service.soc_svc` imported but unused
- app/integrations/bi_etl_connectors.py:271 - `hubspot` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/integrations/bi_etl_connectors.py:380 - `xero_python.api_client.configuration.Configuration` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/integrations/bi_etl_connectors.py:382 - `xero_python.accounting.AccountingApi` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/integrations/bi_etl_connectors.py:866 - `json` imported but unused
- app/models/service_desk.py:5 - `sqlalchemy` imported but unused
- app/services/ai_chat/core_service.py:6 - `datetime.datetime` imported but unused
- app/services/ai_chat/core_service.py:6 - `datetime.timezone` imported but unused
- app/services/ai_chat/core_service.py:9 - `app.models.ai_chat.AIConversation` imported but unused
- app/services/ai_chat/governance_service.py:9 - `sqlalchemy.func` imported but unused
- app/services/ai_chat/rate_limit_service.py:5 - `datetime.timedelta` imported but unused
- app/services/ai_chat/tool_execution_service.py:11 - `typing.Optional` imported but unused
- app/services/ai_chat/tool_execution_service.py:21 - `app.models.financial.CapacityPlan` imported but unused
- app/services/ai_chat/tool_execution_service.py:32 - `app.models.enterprise.Notification` imported but unused
- app/services/ask_the_data.py:14 - `json` imported but unused
- app/services/bi_dashboard_collab_service.py:18 - `typing.Any` imported but unused
- app/services/bi_dashboard_collab_service.py:22 - `app.models.bi_collaboration.DashboardShare` imported but unused
- app/services/bi_export_service.py:19 - `typing.Any` imported but unused
- app/services/bi_export_service.py:70 - `openpyxl.styles.Alignment` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/bi_export_service.py:71 - `openpyxl.utils.get_column_letter` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/bi_smart_alerts_service.py:234 - `datetime.timedelta` imported but unused
- app/services/bi_smart_alerts_service.py:277 - `app.models.service_desk.TicketStatus` imported but unused
- app/services/bi_smart_alerts_service.py:290 - `app.models.task.TaskStatus` imported but unused
- app/services/documents_collab_service.py:12 - `base64` imported but unused
- app/services/metrics/invoices_alerts.py:102 - `app.models.clients.Client` imported but unused
- app/services/metrics/training_git.py:185 - `sqlalchemy.cast` imported but unused
- app/services/metrics/training_git.py:185 - `sqlalchemy.Float` imported but unused
- app/services/ml_trainer.py:25 - `app.models.project.Project` imported but unused
- app/services/olap/etl.py:261 - `datetime.datetime` imported but unused
- app/services/olap/etl.py:261 - `datetime.timezone` imported but unused
- app/services/report_pdf_service.py:18 - `typing.Any` imported but unused
- app/services/report_pdf_service.py:25 - `reportlab.lib.enums.TA_LEFT` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/report_pdf_service.py:25 - `reportlab.lib.enums.TA_CENTER` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/report_pdf_service.py:25 - `reportlab.lib.enums.TA_RIGHT` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/report_pdf_service.py:31 - `reportlab.platypus.KeepTogether` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/revenue_service.py:20 - `datetime.datetime` imported but unused
- app/services/revenue_service.py:20 - `datetime.timezone` imported but unused
- app/services/service_desk/ai_auto_resolution_service.py:19 - `typing.Optional` imported but unused
- app/services/service_desk/ai_auto_resolution_service.py:25 - `app.core.config.settings` imported but unused
- app/services/service_desk/asset_service.py:286 - `datetime.datetime` imported but unused
- app/services/service_desk/asset_service.py:286 - `datetime.timezone` imported but unused
- app/services/service_desk/asset_service.py:287 - `uuid.uuid4` imported but unused
- app/services/service_desk/asset_service.py:440 - `app.models.service_desk.TicketType` imported but unused
- app/services/service_desk/autonomous_agent_service.py:40 - `app.models.service_desk.TicketPriority` imported but unused
- app/services/service_desk/autonomous_agent_service.py:44 - `app.services.service_desk.incident_intelligence_service.AUTO_RESOLVE_CONFIDENCE_THRESHOLD` imported but unused
- app/services/service_desk/cab_workflow_service.py:4 - `uuid` imported but unused
- app/services/service_desk/capacity_planning_service.py:13 - `collections.defaultdict` imported but unused
- app/services/service_desk/capacity_planning_service.py:15 - `typing.Optional` imported but unused
- app/services/service_desk/change_impact_service.py:32 - `app.models.service_desk.TicketStatus` imported but unused
- app/services/service_desk/change_impact_service.py:33 - `app.models.service_desk.TicketPriority` imported but unused
- app/services/service_desk/change_rollout_service.py:17 - `typing.Any` imported but unused
- app/services/service_desk/change_service.py:256 - `app.models.service_desk.ChangeType` imported but unused
- app/services/service_desk/cmdb_discovery_service.py:625 - `pysnmp.hlapi.bulkCmd` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/service_desk/cmdb_discovery_service.py:1426 - `app.models.cmdb.CMDBAgentRegistration` imported but unused
- app/services/service_desk/governance_compliance_service.py:25 - `typing.Optional` imported but unused
- app/services/service_desk/governance_compliance_service.py:34 - `app.models.service_desk.ChangeStatus` imported but unused
- app/services/service_desk/governance_compliance_service.py:40 - `app.models.service_desk.TicketStatus` imported but unused
- app/services/service_desk/incident_assignment_service.py:26 - `lightgbm` imported but unused; consider using `importlib.util.find_spec` to test for availability
- app/services/service_desk/incident_intelligence_service.py:26 - `app.models.user.User` imported but unused
- app/services/service_desk/incident_intelligence_service.py:27 - `app.services.sla_service.compute_sla_status` imported but unused
- app/services/service_desk/ml_routing_service.py:441 - `sqlalchemy.text` imported but unused
- app/services/service_desk/predictive_analytics_service.py:33 - `app.models.service_desk.TicketType` imported but unused
- app/services/service_desk/rca_wizard_service.py:388 - `json` imported but unused
- app/services/service_desk/rca_wizard_service.py:521 - `json` imported but unused
- app/services/service_desk/sd_reporting_service.py:14 - `typing.Any` imported but unused
- app/services/service_desk/sd_reporting_service.py:16 - `sqlalchemy.and_` imported but unused
- app/services/service_desk/sd_reporting_service.py:123 - `app.models.service_desk.Ticket` imported but unused
- app/services/service_desk/smart_catalog_service.py:30 - `app.models.service_desk.ServiceCategory` imported but unused
- app/services/service_desk/smart_catalog_service.py:33 - `app.models.service_desk.TicketType` imported but unused
- app/services/service_desk/workflow_designer_service.py:5 - `typing.Any` imported but unused
- tests/test_ai_auto_resolution_service.py:6 - `datetime.datetime` imported but unused
- tests/test_bi_anomaly.py:2 - `pytest` imported but unused
- tests/test_bi_conditional_delivery.py:2 - `pytest` imported but unused
- tests/test_bi_dashboard_collab.py:2 - `pytest` imported but unused
- tests/test_bi_etl.py:2 - `pytest` imported but unused
- tests/test_bi_etl_connector_celery.py:4 - `pytest` imported but unused
- tests/test_bi_forecasting.py:2 - `pytest` imported but unused
- tests/test_bi_gdpr.py:2 - `pytest` imported but unused
- tests/test_bi_governance.py:2 - `pytest` imported but unused
- tests/test_bi_o365.py:2 - `pytest` imported but unused
- tests/test_bi_query_builder.py:2 - `pytest` imported but unused
- tests/test_change_rollout.py:2 - `pytest` imported but unused
- tests/test_cmdb_3d.py:2 - `pytest` imported but unused
- tests/test_incident_assignment_ml.py:2 - `pytest` imported but unused
- tests/test_m365_bi_embed.py:6 - `io` imported but unused
- tests/test_m365_bi_embed.py:115 - `httpx` imported but unused
- tests/test_orchestration_readiness_and_webhook_worker.py:1 - `json` imported but unused
- tests/test_predictive_observability_endpoint.py:7 - `app.services.predictive_retraining_service.LAST_EVAL_KEY` imported but unused
- tests/test_voice_agent.py:2 - `pytest` imported but unused

### F541
- app/services/m365_bi_embed_service.py:241 - f-string without any placeholders

### F601
- app/api/v1/endpoints/analytics.py:573 - Dictionary key literal `"sprint_completion_rate"` repeated
- app/api/v1/endpoints/analytics.py:579 - Dictionary key literal `"tasks_by_status"` repeated
- app/api/v1/endpoints/analytics.py:603 - Dictionary key literal `"tasks_by_assignee"` repeated
- app/api/v1/endpoints/analytics.py:652 - Dictionary key literal `"absences_by_type"` repeated
- app/api/v1/endpoints/analytics.py:658 - Dictionary key literal `"absences_by_person"` repeated

### F811
- app/services/ml_trainer.py:314 - Redefinition of unused `Project` from line 25: `Project` redefined here
- app/services/service_desk/asset_service.py:464 - Redefinition of unused `uuid4` from line 287: `uuid4` redefined here
- app/services/service_desk/cmdb_discovery_service.py:1273 - Redefinition of unused `hashlib` from line 16: `hashlib` redefined here
- tests/test_bi_gdpr.py:169 - Redefinition of unused `test_record_consent` from line 6: `test_record_consent` redefined here
- tests/test_bi_gdpr.py:183 - Redefinition of unused `test_get_consent` from line 20: `test_get_consent` redefined here
- tests/test_bi_gdpr.py:192 - Redefinition of unused `test_create_dsr_erasure` from line 44: `test_create_dsr_erasure` redefined here
- tests/test_bi_gdpr.py:205 - Redefinition of unused `test_list_dsrs` from line 82: `test_list_dsrs` redefined here
- tests/test_bi_gdpr.py:213 - Redefinition of unused `test_resolve_dsr` from line 99: `test_resolve_dsr` redefined here
- tests/test_bi_gdpr.py:221 - Redefinition of unused `test_field_masks` from line 144: `test_field_masks` redefined here
- tests/test_bi_gdpr.py:231 - Redefinition of unused `test_gdpr_requires_auth` from line 163: `test_gdpr_requires_auth` redefined here

### F821
- app/api/v1/endpoints/service_desk/tickets.py:348 - Undefined name `HTTPException`
- app/api/v1/endpoints/service_desk/tickets.py:350 - Undefined name `HTTPException`
- app/services/ai_chat/tool_execution_service.py:932 - Undefined name `timedelta`
- app/services/ai_chat/tool_execution_service.py:934 - Undefined name `timedelta`
- app/services/ai_chat/tool_execution_service.py:935 - Undefined name `timedelta`

### F841
- app/api/v1/endpoints/jira_integration.py:310 - Local variable `event` is assigned to but never used
- app/api/v1/endpoints/service_desk/change_impact.py:271 - Local variable `exc` is assigned to but never used
- app/api/v1/endpoints/service_desk/voice_agent.py:266 - Local variable `caller_id` is assigned to but never used
- app/services/ai_chat/context_service.py:49 - Local variable `org_project_ids` is assigned to but never used
- app/services/ai_provider_service.py:815 - Local variable `base_url` is assigned to but never used
- app/services/bi_forecasting_service.py:144 - Local variable `preds_in_sample` is assigned to but never used
- app/services/bi_intelligence_service.py:189 - Local variable `fitted` is assigned to but never used
- app/services/scheduled_reports.py:166 - Local variable `include_narrative` is assigned to but never used
- app/services/service_desk/alert_correlation_service.py:411 - Local variable `window_start` is assigned to but never used
- app/services/service_desk/cmdb_discovery_service.py:814 - Local variable `old_attributes` is assigned to but never used
- tests/test_bi_collaboration_complete.py:379 - Local variable `comment_res` is assigned to but never used

### W191
- app/api/v1/endpoints/auth.py:13 - Indentation contains tabs
- app/api/v1/endpoints/auth.py:14 - Indentation contains tabs
- app/api/v1/endpoints/auth.py:15 - Indentation contains tabs

### W291
- tests/test_bi_collaboration_complete.py:4 - Trailing whitespace

### W292
- app/api/v1/endpoints/portal_conversations.py:245 - No newline at end of file
- app/models/portal_conversations.py:214 - No newline at end of file

### W293
- app/api/v1/endpoints/predictions.py:40 - Blank line contains whitespace
- app/api/v1/endpoints/predictions.py:42 - Blank line contains whitespace
- app/api/v1/endpoints/predictions.py:49 - Blank line contains whitespace
- app/api/v1/endpoints/service_desk/ai_auto_resolution.py:54 - Blank line contains whitespace
- app/api/v1/endpoints/service_desk/ai_auto_resolution.py:99 - Blank line contains whitespace
- app/api/v1/endpoints/service_desk/ai_auto_resolution.py:163 - Blank line contains whitespace
- app/api/v1/endpoints/service_desk/ai_auto_resolution.py:165 - Blank line contains whitespace
- app/api/v1/endpoints/service_desk/ai_auto_resolution.py:179 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:322 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:331 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:334 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:338 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:341 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:344 - Blank line contains whitespace
- app/api/v1/routers/auth_core.py:347 - Blank line contains whitespace
- app/api/v1/routers/auth_mfa.py:150 - Blank line contains whitespace
- app/api/v1/routers/auth_mfa.py:382 - Blank line contains whitespace
- app/services/ai_chat/core_service.py:74 - Blank line contains whitespace
- app/services/ai_provider_service.py:607 - Blank line contains whitespace
- app/services/ai_provider_service.py:612 - Blank line contains whitespace
- app/services/ai_provider_service.py:620 - Blank line contains whitespace
- app/services/ai_provider_service.py:631 - Blank line contains whitespace
- app/services/ai_provider_service.py:637 - Blank line contains whitespace
- app/services/ai_provider_service.py:651 - Blank line contains whitespace
- app/services/ai_provider_service.py:658 - Blank line contains whitespace
- app/services/ai_provider_service.py:665 - Blank line contains whitespace
- app/services/ai_provider_service.py:686 - Blank line contains whitespace
- app/services/ai_provider_service.py:692 - Blank line contains whitespace
- app/services/ai_provider_service.py:699 - Blank line contains whitespace
- app/services/ai_provider_service.py:741 - Blank line contains whitespace
- app/services/bi_collaboration_service.py:964 - Blank line contains whitespace
- app/services/bi_collaboration_service.py:997 - Blank line contains whitespace
- app/services/bi_collaboration_service.py:1001 - Blank line contains whitespace
- app/services/bi_collaboration_service.py:1008 - Blank line contains whitespace
- app/services/service_desk/ai_auto_resolution_service.py:301 - Blank line contains whitespace
- app/services/service_desk/ai_auto_resolution_service.py:351 - Blank line contains whitespace
- app/services/service_desk/ai_auto_resolution_service.py:362 - Blank line contains whitespace
- app/services/service_desk/ai_auto_resolution_service.py:568 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:57 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:68 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:74 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:79 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:131 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:219 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:235 - Blank line contains whitespace
- app/services/service_desk/change_management_service.py:285 - Blank line contains whitespace
- tests/test_ai_auto_resolution_service.py:20 - Blank line contains whitespace
- tests/test_bi_collaboration_complete.py:289 - Blank line contains whitespace

