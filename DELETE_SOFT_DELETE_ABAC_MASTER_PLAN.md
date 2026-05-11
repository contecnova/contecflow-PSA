# Plan Maestro Exhaustivo - Soft-Delete + ABAC (182 DELETE endpoints)

Fecha: 9 de mayo de 2026  
Scope baseline: DELETE_ENDPOINTS_MATRIX.csv (182 endpoints)

## Metodologia y baseline
- Fuente principal: DELETE_ENDPOINTS_MATRIX.csv (182 endpoints, 83 archivos con DELETE).
- Validacion adicional: escaneo de decoradores @router.delete en codigo (detecta 187).  
  Para este plan se usa el baseline contractual de 182 endpoints ya auditados.
- Criterios por endpoint: ABAC, SoftDelete, Validacion de dependencias, Response OK, FilterActive.

## 1) Archivos con DELETE endpoints (endpoints + routers)
- app/api/v1/endpoints/abac.py
- app/api/v1/endpoints/absences.py
- app/api/v1/endpoints/activity.py
- app/api/v1/endpoints/advanced_config.py
- app/api/v1/endpoints/ai_chat.py
- app/api/v1/endpoints/ai_governance.py
- app/api/v1/endpoints/ai_providers.py
- app/api/v1/endpoints/alm.py
- app/api/v1/endpoints/approvals.py
- app/api/v1/endpoints/automations.py
- app/api/v1/endpoints/bi_bookmarks.py
- app/api/v1/endpoints/bi_conditional_delivery.py
- app/api/v1/endpoints/bi_embed.py
- app/api/v1/endpoints/bi_intelligence.py
- app/api/v1/endpoints/bi_platform.py
- app/api/v1/endpoints/bi_query_builder.py
- app/api/v1/endpoints/bi_report_builder_v2.py
- app/api/v1/endpoints/bi_smart_alerts.py
- app/api/v1/endpoints/billing_reports.py
- app/api/v1/endpoints/bookings.py
- app/api/v1/endpoints/bpmn_processes.py
- app/api/v1/endpoints/cab.py
- app/api/v1/endpoints/capacity.py
- app/api/v1/endpoints/changes.py
- app/api/v1/endpoints/client_portal.py
- app/api/v1/endpoints/clients.py
- app/api/v1/endpoints/cmdb.py
- app/api/v1/endpoints/collaboration/admin.py
- app/api/v1/endpoints/collaboration/bots.py
- app/api/v1/endpoints/collaboration/messages.py
- app/api/v1/endpoints/collaboration/tus.py
- app/api/v1/endpoints/collaboration/workspaces.py
- app/api/v1/endpoints/contracts.py
- app/api/v1/endpoints/custom_fields.py
- app/api/v1/endpoints/deliverables.py
- app/api/v1/endpoints/developer_portal.py
- app/api/v1/endpoints/documents.py
- app/api/v1/endpoints/enterprise.py
- app/api/v1/endpoints/epics.py
- app/api/v1/endpoints/esign.py
- app/api/v1/endpoints/expenses.py
- app/api/v1/endpoints/grc.py
- app/api/v1/endpoints/imputations.py
- app/api/v1/endpoints/integrations/__init__.py
- app/api/v1/endpoints/issue_types.py
- app/api/v1/endpoints/jira_integration.py
- app/api/v1/endpoints/m365.py
- app/api/v1/endpoints/marketplace.py
- app/api/v1/endpoints/mfa.py
- app/api/v1/endpoints/milestones.py
- app/api/v1/endpoints/okrs.py
- app/api/v1/endpoints/pipeline.py
- app/api/v1/endpoints/portfolio.py
- app/api/v1/endpoints/profitability.py
- app/api/v1/endpoints/projects/__init__.py
- app/api/v1/endpoints/public_forms.py
- app/api/v1/endpoints/raci.py
- app/api/v1/endpoints/rate_cards.py
- app/api/v1/endpoints/report_builder.py
- app/api/v1/endpoints/revenue.py
- app/api/v1/endpoints/risks.py
- app/api/v1/endpoints/scim.py
- app/api/v1/endpoints/service_desk/assets.py
- app/api/v1/endpoints/service_desk/autonomous.py
- app/api/v1/endpoints/service_desk/cmdb.py
- app/api/v1/endpoints/service_desk/kb.py
- app/api/v1/endpoints/service_desk/misc.py
- app/api/v1/endpoints/service_desk/oncall.py
- app/api/v1/endpoints/service_desk/sla.py
- app/api/v1/endpoints/service_desk/templates.py
- app/api/v1/endpoints/service_desk/tickets.py
- app/api/v1/endpoints/service_desk/workflow_designer.py
- app/api/v1/endpoints/settings.py
- app/api/v1/endpoints/skills.py
- app/api/v1/endpoints/sprints.py
- app/api/v1/endpoints/tasks.py
- app/api/v1/endpoints/training.py
- app/api/v1/endpoints/user_costs.py
- app/api/v1/endpoints/users.py
- app/api/v1/endpoints/v239/baselines.py
- app/api/v1/endpoints/v239/branding.py
- app/api/v1/routers/auth_mfa.py
- app/api/v1/routers/auth_sessions.py

## 2) Tabla por archivo (TODOS los endpoints DELETE)

Columnas:
- Current Pattern: resumen operativo del endpoint.
- Needs is_active?: YES si SoftDelete=False.
- Needs enforce_abac?: YES si ABAC=False.
- Needs service fix?: YES si falla cualquiera de los 5 criterios.

### [FILE] endpoints/abac.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /users/{user_id}/attributes/{attribute_key} (L145) | Hard-delete + No ABAC + Bad response | YES | YES | YES | ABACPolicy;AttributeDefinition;PolicyAudit;User;UserAttribute | P0 |
| /policies/{policy_id} (L258) | Hard-delete + No ABAC + Bad response | YES | YES | YES | ABACPolicy;AttributeDefinition;PolicyAudit;User;UserAttribute | P0 |

### [FILE] endpoints/absences.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /my/{absence_id} (L97) | Hard-delete + No ABAC | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;Holiday;User;UserRole | P0 |

### [FILE] endpoints/activity.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /recurring-tasks/{rt_id} (L214) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMVendor;ActivityEvent;Budget;ClientHealthSnapshot;Imputation;Mention;Notification;NotificationType;Opportunity;OpportunityStage;Project;ProjectHealthSnapshot;ProjectStatus;RecurringFreqType;RecurringTask;ResourceDemandForecast;Task;TaskDependency;TaskStatus;User;VendorScore | P0 |
| /pipeline/resource-demand-lines/{line_id} (L354) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMVendor;ActivityEvent;Budget;ClientHealthSnapshot;Imputation;Mention;Notification;NotificationType;Opportunity;OpportunityStage;Project;ProjectHealthSnapshot;ProjectStatus;RecurringFreqType;RecurringTask;ResourceDemandForecast;Task;TaskDependency;TaskStatus;User;VendorScore | P0 |

### [FILE] endpoints/advanced_config.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /roles/{role_id} (L140) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /task-types/{type_id} (L174) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /rate-tables/{table_id}/entries/{entry_id} (L217) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /rate-tables/{table_id} (L224) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /vacation-policies/{policy_id} (L249) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /offices/{office_id} (L282) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /custom-fields/{field_id} (L328) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |
| /templates/{template_id} (L359) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy | P0 |

### [FILE] endpoints/ai_chat.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /ai/conversations/{conv_id} (L405) | Soft-delete + No ABAC + No dependency validation + Bad response | NO | YES | YES | AIGuardrailAuditLog;AIGuardrailPolicyModel;User | P0 |
| /ai/conversations (L417) | Soft-delete + No ABAC + No dependency validation + Bad response | NO | YES | YES | AIGuardrailAuditLog;AIGuardrailPolicyModel;User | P0 |
| /governance/prompts/{prompt_id} (L764) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AIGuardrailAuditLog;AIGuardrailPolicyModel;User | P0 |

### [FILE] endpoints/ai_governance.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /policies/{policy_id} (L191) | Soft-delete + No ABAC | NO | YES | YES | AIGuardrailAuditLog;AIGuardrailPolicyModel;User | P0 |

### [FILE] endpoints/ai_providers.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{pid} (L85) | Hard-delete + No ABAC | YES | YES | YES | AIProvider;AIUsageLog;User | P0 |

### [FILE] endpoints/alm.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /vendors/{vid} (L54) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |
| /contracts/{cid} (L78) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |
| /licenses/{lid} (L102) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |
| /licenses/{lid}/assignments/{aid} (L112) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |
| /assets/{aid} (L136) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |
| /cost-centers/{cid} (L158) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |
| /assets/{aid}/installs/{iid} (L168) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |

### [FILE] endpoints/approvals.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /workflows/{workflow_id} (L174) | Hard-delete + No ABAC | YES | YES | YES | ApprovalDecision;ApprovalGroup;ApprovalRequest;ApprovalStep;ApprovalWorkflow;FinancialApprovalAuditLog;User;UserRole | P0 |
| /workflows/{workflow_id}/steps/{step_id} (L212) | Hard-delete + No ABAC | YES | YES | YES | ApprovalDecision;ApprovalGroup;ApprovalRequest;ApprovalStep;ApprovalWorkflow;FinancialApprovalAuditLog;User;UserRole | P0 |
| /groups/{group_id} (L431) | Hard-delete + No ABAC | YES | YES | YES | ApprovalDecision;ApprovalGroup;ApprovalRequest;ApprovalStep;ApprovalWorkflow;FinancialApprovalAuditLog;User;UserRole | P0 |

### [FILE] endpoints/automations.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{rule_id} (L83) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ActionType;Alert;AlertSeverity;AlertType;AutomationExecution;AutomationRule;Project;Task;Timesheet;TriggerType;User | P0 |

### [FILE] endpoints/bi_bookmarks.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/bookmarks/{bookmark_id} (L114) | Hard-delete + No ABAC + Bad response | YES | YES | YES | AppSetting;User | P0 |

### [FILE] endpoints/bi_conditional_delivery.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/delivery/rules/{rule_id} (L121) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AppSetting;User | P0 |

### [FILE] endpoints/bi_embed.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /token/{jti} (L42) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User | P0 |

### [FILE] endpoints/bi_intelligence.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/delivery/schedules/{schedule_id} (L614) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | AppSetting;Imputation;Project;User | P0 |

### [FILE] endpoints/bi_platform.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/platform/connectors/custom/{connector_id} (L190) | Hard-delete + No ABAC | YES | YES | YES | AppSetting;User | P0 |
| /bi/platform/governance/field-sensitivity/{sensiti (L347) | Hard-delete + No ABAC | YES | YES | YES | AppSetting;User | P0 |

### [FILE] endpoints/bi_query_builder.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/query-builder/queries/{query_id} (L159) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AppSetting;User | P0 |

### [FILE] endpoints/bi_report_builder_v2.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/reports/v2/templates/{template_id} (L269) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | AppSetting;User | P0 |

### [FILE] endpoints/bi_smart_alerts.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /bi/alerts/custom-metrics/{key} (L94) | Hard-delete + No ABAC + Bad response | YES | YES | YES | AppSetting;User | P0 |
| /bi/alerts/rules/{rule_id} (L156) | Hard-delete + No ABAC + Bad response | YES | YES | YES | AppSetting;User | P0 |

### [FILE] endpoints/billing_reports.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /report-catalog/{report_id} (L145) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Absence;AbsenceStatus;ApiKey;AutomationWorkflow;BookingType;CapacityPlan;ExchangeRate;Expense;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;Project;ProjectPhase;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Sprint;SprintStatus;SprintTask;Task;TaskDependency;Ticket;Timesheet;TimesheetStatus;User;UserRole;UserSkill;WorkflowExecution;WorkflowQueueItem;WorkflowStep | P0 |
| /automation-workflows/{wf_id} (L408) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Absence;AbsenceStatus;ApiKey;AutomationWorkflow;BookingType;CapacityPlan;ExchangeRate;Expense;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;Project;ProjectPhase;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Sprint;SprintStatus;SprintTask;Task;TaskDependency;Ticket;Timesheet;TimesheetStatus;User;UserRole;UserSkill;WorkflowExecution;WorkflowQueueItem;WorkflowStep | P0 |
| /scheduled-reports/{report_id} (L557) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Absence;AbsenceStatus;ApiKey;AutomationWorkflow;BookingType;CapacityPlan;ExchangeRate;Expense;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;Project;ProjectPhase;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Sprint;SprintStatus;SprintTask;Task;TaskDependency;Ticket;Timesheet;TimesheetStatus;User;UserRole;UserSkill;WorkflowExecution;WorkflowQueueItem;WorkflowStep | P0 |

### [FILE] endpoints/bookings.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{booking_id} (L95) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ApiKey;AutomationWorkflow;BookingType;Document;DocumentCollabSnapshot;ExchangeRate;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;PipelineStageConfig;Project;ProjectCustomField;ProjectCustomFieldValue;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Task;TaskDependency;Ticket;User;WorkflowExecution;WorkflowQueueItem | P0 |
| /sla-schedules/{schedule_id}/holidays/{holiday_id} (L128) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ApiKey;AutomationWorkflow;BookingType;Document;DocumentCollabSnapshot;ExchangeRate;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;PipelineStageConfig;Project;ProjectCustomField;ProjectCustomFieldValue;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Task;TaskDependency;Ticket;User;WorkflowExecution;WorkflowQueueItem | P0 |
| /api-keys/{key_id} (L150) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ApiKey;AutomationWorkflow;BookingType;Document;DocumentCollabSnapshot;ExchangeRate;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;PipelineStageConfig;Project;ProjectCustomField;ProjectCustomFieldValue;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Task;TaskDependency;Ticket;User;WorkflowExecution;WorkflowQueueItem | P0 |

### [FILE] endpoints/bpmn_processes.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{process_id} (L164) | Soft-delete + No ABAC | NO | YES | YES | BPMNProcess;BPMNProcessStatus;BPMNProcessVersion;User | P0 |

### [FILE] endpoints/cab.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /webhooks/{trigger_id} (L246) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | CABVote;CalendarEvent;ChangeRequest;ChangeRequestWindow;CommitLink;DashboardWidget;EmailLog;EmailTemplate;GDPRRequest;GDPRRequestStatus;GDPRRequestType;Imputation;IntegrationConfig;Invoice;MaintenanceWindow;OnboardingState;Opportunity;Project;ProjectRiskScore;RecognitionMethod;RevenueRecognitionEntry;RevenueRecognitionRule;Risk;Sprint;Task;Ticket;User;WorkflowQueueItem | P0 |
| /dashboard-widgets/reset (L413) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | CABVote;CalendarEvent;ChangeRequest;ChangeRequestWindow;CommitLink;DashboardWidget;EmailLog;EmailTemplate;GDPRRequest;GDPRRequestStatus;GDPRRequestType;Imputation;IntegrationConfig;Invoice;MaintenanceWindow;OnboardingState;Opportunity;Project;ProjectRiskScore;RecognitionMethod;RevenueRecognitionEntry;RevenueRecognitionRule;Risk;Sprint;Task;Ticket;User;WorkflowQueueItem | P0 |

### [FILE] endpoints/capacity.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /plans/{plan_id} (L249) | Hard-delete + No ABAC | YES | YES | YES | Absence;AbsenceStatus;CapacityPlan;Imputation;Project;Sprint;SprintStatus;SprintTask;Timesheet;TimesheetStatus;User;UserRole;UserStatus | P0 |

### [FILE] endpoints/changes.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{project_id}/{cr_id} (L220) | Hard-delete + No ABAC | YES | YES | YES | ChangeRequest;ChangeRequestStatus;User | P0 |

### [FILE] endpoints/client_portal.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /clients/{client_id} (L241) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AppSetting;ApprovalRequest;ChangeRequest;ChangeRequestImpact;ChangeRequestStatus;Client;ClientDocument;ClientMessage;ClientPortalConfig;ClientSurvey;ClientUser;Deliverable;DeliverableStatus;FeatureRequest;FeatureRequestStatus;Imputation;Invoice;InvoiceStatus;Project;ProjectMilestone;Ticket;TicketStatus;UATIssue;UATSession;UATStatus;UATTestCase;User;WikiPage;client_user_projects | P0 |

### [FILE] endpoints/clients.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{cid} (L73) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMLicense;Client;ClientContact;ClientContractLink;ClientLicenseLink;ClientPortalConfig;ClientUser;Contract;Invoice;Project;Ticket;User | P0 |
| /{cid}/contacts/{contact_id} (L100) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMLicense;Client;ClientContact;ClientContractLink;ClientLicenseLink;ClientPortalConfig;ClientUser;Contract;Invoice;Project;Ticket;User | P0 |
| /{cid}/licenses/{link_id} (L117) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMLicense;Client;ClientContact;ClientContractLink;ClientLicenseLink;ClientPortalConfig;ClientUser;Contract;Invoice;Project;Ticket;User | P0 |
| /{cid}/contracts/{link_id} (L134) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMLicense;Client;ClientContact;ClientContractLink;ClientLicenseLink;ClientPortalConfig;ClientUser;Contract;Invoice;Project;Ticket;User | P0 |
| /{cid}/projects/{project_id}/link (L250) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ALMLicense;Client;ClientContact;ClientContractLink;ClientLicenseLink;ClientPortalConfig;ClientUser;Contract;Invoice;Project;Ticket;User | P0 |

### [FILE] endpoints/cmdb.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /wiki-tags/{tag_id} (L48) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /wiki-pages/{page_id}/tags/{tag_id} (L60) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /items/{item_id} (L250) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /relations/{relation_id} (L278) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /kanban/columns/{column_id} (L360) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /sprint-plans/{plan_id} (L406) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /sla-calendars/{cal_id} (L447) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |
| /sla-calendars/{cal_id}/holidays/{holiday_id} (L471) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;SprintTask;Task;User;WikiPage;WikiSpace | P0 |

### [FILE] endpoints/collaboration/admin.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /push/unsubscribe (L74) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User | P0 |

### [FILE] endpoints/collaboration/bots.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /integrations/{integration_id} (L101) | Soft-delete + No ABAC | NO | YES | YES | User | P0 |

### [FILE] endpoints/collaboration/messages.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /messages/{message_id} (L80) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /conversations/{conversation_id}/pins/{message_id} (L114) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /saved/{message_id} (L132) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |

### [FILE] endpoints/collaboration/tus.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /tus/{uid} (L255) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User | P0 |

### [FILE] endpoints/collaboration/workspaces.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /teams/{team_id}/members/{user_id} (L140) | Soft-delete + No ABAC + No dependency validation + Bad response | NO | YES | YES | User | P0 |
| /conversations/{conversation_id}/members/{user_id} (L343) | Hard-delete + No ABAC + Bad response | YES | YES | YES | User | P0 |
| /search/saved/{saved_id} (L584) | Hard-delete + No ABAC | YES | YES | YES | User | P0 |

### [FILE] endpoints/contracts.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{contract_id} (L69) | Hard-delete + No ABAC | YES | YES | YES | Contract;Project;User;WorkOrder | P0 |

### [FILE] endpoints/custom_fields.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /custom-fields/{project_id}/{field_id} (L59) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;ProjectCustomField;ProjectCustomFieldValue;ProjectPermission;ProjectPermissionLevel;Task;User;WorkflowState;WorkflowTransition | P0 |
| /project-workflows/{project_id}/states/{state_id} (L130) | Hard-delete + No dependency validation + Bad response | YES | NO | YES | Project;ProjectCustomField;ProjectCustomFieldValue;ProjectPermission;ProjectPermissionLevel;Task;User;WorkflowState;WorkflowTransition | P0 |
| /project-workflows/{project_id}/transitions/{trans (L150) | Hard-delete + No dependency validation + Bad response | YES | NO | YES | Project;ProjectCustomField;ProjectCustomFieldValue;ProjectPermission;ProjectPermissionLevel;Task;User;WorkflowState;WorkflowTransition | P0 |
| /project-workflows/{project_id}/reset (L169) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;ProjectCustomField;ProjectCustomFieldValue;ProjectPermission;ProjectPermissionLevel;Task;User;WorkflowState;WorkflowTransition | P0 |
| /permissions/{project_id}/{permission_id} (L223) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;ProjectCustomField;ProjectCustomFieldValue;ProjectPermission;ProjectPermissionLevel;Task;User;WorkflowState;WorkflowTransition | P0 |

### [FILE] endpoints/deliverables.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{project_id}/{del_id} (L131) | Hard-delete | YES | NO | YES | Deliverable;DeliverableStatus;User;UserRole | P0 |

### [FILE] endpoints/developer_portal.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /apps/{app_id} (L130) | Hard-delete + No ABAC + Bad response | YES | YES | YES | OAuthApp;OAuthToken;User;UserRole | P0 |

### [FILE] endpoints/documents.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{doc_id} (L163) | Soft-delete + No ABAC + No dependency validation + Bad response | NO | YES | YES | ApprovalStatus;Document;DocumentAccessLevel;DocumentAccessLog;DocumentCategory;DocumentPermission;DocumentTag;DocumentVersion;User;UserRole | P0 |
| /{doc_id}/permissions/{perm_id} (L305) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | ApprovalStatus;Document;DocumentAccessLevel;DocumentAccessLog;DocumentCategory;DocumentPermission;DocumentTag;DocumentVersion;User;UserRole | P0 |
| /{doc_id}/tags/{tag_name} (L595) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | ApprovalStatus;Document;DocumentAccessLevel;DocumentAccessLog;DocumentCategory;DocumentPermission;DocumentTag;DocumentVersion;User;UserRole | P0 |

### [FILE] endpoints/enterprise.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /project-permissions/{project_id}/{permission_id} (L78) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /webhooks/{hook_id} (L122) | Hard-delete + No ABAC + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /sso/{config_id} (L177) | Hard-delete + No ABAC + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /notifications/clear-old (L221) | Soft-delete + No ABAC + No dependency validation + Bad response | NO | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /subcontractors/{sub_id} (L260) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /subcontractors/{sub_id}/rates/{rate_id} (L281) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /subcontractors/workers/{worker_id} (L349) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /subcontractors/workers/{worker_id}/skills/{skill_ (L370) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |
| /subcontractors/{sub_id}/timelogs/{log_id} (L400) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent | P0 |

### [FILE] endpoints/epics.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /wiki/spaces/{space_id} (L54) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |
| /wiki/pages/{page_id} (L90) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |
| /filters/{filter_id} (L191) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |
| /comments/{comment_id} (L253) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |
| /{epic_id} (L272) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |
| /{epic_id}/tasks/{task_id} (L284) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |
| /{epic_id}/dependencies/{depends_on_id} (L296) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Project;Task;Ticket;User;WikiTemplate | P0 |

### [FILE] endpoints/esign.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{envelope_id} (L320) | Hard-delete + No ABAC + Bad response | YES | YES | YES | AppSetting;Document;ESignEnvelope;ESignProvider;ESignSigner;ESignStatus;User | P0 |

### [FILE] endpoints/expenses.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /my/{expense_id} (L187) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Expense;ExpenseStatus;Project;ProjectStatus;User;UserRole | P0 |

### [FILE] endpoints/grc.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /sod-rules/{rule_id} (L251) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | GrcAuditLog;RolePermission;SodRule;SodViolation;User | P0 |

### [FILE] endpoints/imputations.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{imputation_id} (L90) | Hard-delete | YES | NO | YES | Absence;AbsenceStatus;CapacityPlan;Imputation;ImputationAlert;Organization;Project;ProjectMember;ProjectStatus;Sprint;SprintStatus;SprintTask;Task;TaskStatus;TimerSession;Timesheet;TimesheetStatus;User;UserRole | P0 |

### [FILE] endpoints/integrations/__init__.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /instances/{instance_id} (L58) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | IntegrationConnector;IntegrationInstance | P0 |

### [FILE] endpoints/issue_types.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /issue-types/{project_id}/{type_id} (L125) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Epic;Project;Task;User;WikiPage;WikiSpace | P0 |
| /task-dependencies/{dep_id} (L184) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Epic;Project;Task;User;WikiPage;WikiSpace | P0 |
| /epic-dependencies/{dep_id} (L227) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Epic;Project;Task;User;WikiPage;WikiSpace | P0 |

### [FILE] endpoints/jira_integration.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /configs/{config_id} (L186) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Ticket;User | P0 |

### [FILE] endpoints/m365.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /calendar/events/{event_id} (L125) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | ProjectMilestone;Task;User | P0 |

### [FILE] endpoints/marketplace.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /uninstall (L32) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | (por definir en servicio de dominio) | P0 |

### [FILE] endpoints/mfa.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /organizations/{org_id}/remove-user/{user_id} (L24) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Imputation;Project;Task;Ticket;User | P0 |
| /mfa/disable (L122) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Imputation;Project;Task;Ticket;User | P0 |
| /scenarios/{scenario_id} (L468) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Imputation;Project;Task;Ticket;User | P0 |
| /bi/tokens/{token_id} (L548) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Imputation;Project;Task;Ticket;User | P0 |

### [FILE] endpoints/milestones.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{milestone_id} (L82) | Hard-delete + No ABAC | YES | YES | YES | Contract;Invoice;InvoiceLine;Project;ProjectMilestone;User | P0 |

### [FILE] endpoints/okrs.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{obj_id} (L61) | Hard-delete + Bad response | YES | NO | YES | KRCheckin;KeyResult;Objective;Project;Task;TaskStatus;User | P0 |
| /key-results/{kr_id} (L96) | Hard-delete + Bad response | YES | NO | YES | KRCheckin;KeyResult;Objective;Project;Task;TaskStatus;User | P0 |

### [FILE] endpoints/pipeline.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{opp_id} (L85) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Opportunity;OpportunityActivity;OpportunityStage;PipelineStageConfig;Project;ProjectStatus;ProjectType;ProposalTemplate;User | P0 |
| /proposals/templates/{template_id} (L217) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | Opportunity;OpportunityActivity;OpportunityStage;PipelineStageConfig;Project;ProjectStatus;ProjectType;ProposalTemplate;User | P0 |
| /stages/{stage_id} (L345) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Opportunity;OpportunityActivity;OpportunityStage;PipelineStageConfig;Project;ProjectStatus;ProjectType;ProposalTemplate;User | P0 |
| /stage-configs/{stage_id} (L346) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Opportunity;OpportunityActivity;OpportunityStage;PipelineStageConfig;Project;ProjectStatus;ProjectType;ProposalTemplate;User | P0 |

### [FILE] endpoints/portfolio.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{portfolio_id} (L86) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Imputation;Portfolio;PortfolioProject;Project;ProjectMilestone;Task;TaskStatus;User | P0 |
| /{portfolio_id}/projects/{project_id} (L125) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Imputation;Portfolio;PortfolioProject;Project;ProjectMilestone;Task;TaskStatus;User | P0 |

### [FILE] endpoints/profitability.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{project_id}/milestones/{milestone_id} (L204) | Hard-delete + No ABAC | YES | YES | YES | ExchangeRate;Imputation;Project;ProjectMilestone;ProjectStatus;TaskStatus;User;UserRole | P0 |

### [FILE] endpoints/projects/__init__.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{project_id} (L163) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Client;Imputation;Project;ProjectMember;ProjectMilestone;ProjectPhase;ProjectStatus;ProjectType;Task;TaskStatus;User;UserRole | P0 |
| /{project_id}/members/{member_id} (L218) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | Client;Imputation;Project;ProjectMember;ProjectMilestone;ProjectPhase;ProjectStatus;ProjectType;Task;TaskStatus;User;UserRole | P0 |

### [FILE] endpoints/public_forms.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{form_id} (L130) | Hard-delete + No ABAC + Bad response | YES | YES | YES | PublicForm;PublicFormSubmission;Ticket;TicketPriority;TicketStatus;TicketType;User;UserRole | P0 |

### [FILE] endpoints/raci.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /projects/{project_id}/raci/{entry_id} (L85) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | BurnoutRiskSnapshot;ChangelogEntryType;Imputation;Project;ProjectChangelogEntry;RACIRole;Sprint;SprintRetroNote;SprintTask;Task;TaskPriority;TaskStatus;UATStatus;User;UserStatus | P0 |
| /projects/{project_id}/changelog/{entry_id} (L242) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | BurnoutRiskSnapshot;ChangelogEntryType;Imputation;Project;ProjectChangelogEntry;RACIRole;Sprint;SprintRetroNote;SprintTask;Task;TaskPriority;TaskStatus;UATStatus;User;UserStatus | P0 |
| /projects/{project_id}/uat/{case_id} (L304) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | BurnoutRiskSnapshot;ChangelogEntryType;Imputation;Project;ProjectChangelogEntry;RACIRole;Sprint;SprintRetroNote;SprintTask;Task;TaskPriority;TaskStatus;UATStatus;User;UserStatus | P0 |

### [FILE] endpoints/rate_cards.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{table_id} (L128) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | RateEntry;RateOverride;RateTable;User | P0 |
| /{table_id}/entries/{entry_id} (L176) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | RateEntry;RateOverride;RateTable;User | P0 |
| /{table_id}/overrides/{override_id} (L198) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | RateEntry;RateOverride;RateTable;User | P0 |

### [FILE] endpoints/report_builder.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /templates/{template_id} (L126) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | AppSetting;Imputation;Project;Task;User | P0 |

### [FILE] endpoints/revenue.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /contracts/{contract_id} (L90) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | Project;ProjectMilestone;User | P0 |
| /obligations/{obligation_id} (L134) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | Project;ProjectMilestone;User | P0 |
| /period-closes/{year}/{month} (L195) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | Project;ProjectMilestone;User | P0 |

### [FILE] endpoints/risks.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{project_id}/{risk_id} (L97) | Hard-delete + No ABAC | YES | YES | YES | Risk;User;UserRole | P0 |

### [FILE] endpoints/scim.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /Users/{user_id} (L173) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | Organization;User;UserRole;UserStatus | P0 |

### [FILE] endpoints/service_desk/assets.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{asset_id} (L283) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/autonomous.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /playbooks/{playbook_id} (L80) | Soft-delete + No ABAC + Bad response | NO | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/cmdb.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /cmdb/agents/{agent_id} (L494) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | CMDBDiscoveryJob;CMDBDiscoveryProvider;User | P0 |

### [FILE] endpoints/service_desk/kb.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /kb/{article_id} (L60) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/misc.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /catalog/categories/{cat_id} (L95) | Soft-delete + No ABAC + No dependency validation | NO | YES | YES | User | P0 |
| /catalog/services/{service_id} (L113) | Soft-delete + No ABAC + No dependency validation | NO | YES | YES | User | P0 |
| /groups/{group_id} (L137) | Soft-delete + No ABAC + No dependency validation | NO | YES | YES | User | P0 |
| /groups/{group_id}/members/{user_id} (L149) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /announcements/{ann_id} (L203) | Soft-delete + No ABAC + No dependency validation | NO | YES | YES | User | P0 |
| /routing-rules/{rule_id} (L228) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /assets/{asset_id} (L443) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /status-page/components/{component_id} (L481) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/oncall.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /oncall/schedules/{schedule_id} (L40) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /oncall/entries/{entry_id} (L54) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/sla.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /sla-policies/{policy_id} (L46) | Soft-delete + No ABAC + No dependency validation | NO | YES | YES | User | P0 |
| /sla-holidays/{holiday_id} (L79) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /escalation-rules/{rule_id} (L105) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/templates.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /ticket-templates/{template_id} (L47) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | User | P0 |
| /canned-responses/{canned_id} (L78) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User | P0 |

### [FILE] endpoints/service_desk/tickets.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /tickets/{ticket_id}/links/{link_id} (L264) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | AgentGroupMember;ClientUser;ConfigurationItem;KBArticle;Problem;SDSLAHoliday;Ticket;TicketHistory;User | P0 |
| /tickets/{ticket_id}/watch (L302) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | AgentGroupMember;ClientUser;ConfigurationItem;KBArticle;Problem;SDSLAHoliday;Ticket;TicketHistory;User | P0 |

### [FILE] endpoints/service_desk/workflow_designer.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /workflow-designer/blueprints/{blueprint_id} (L195) | Soft-delete + No ABAC | NO | YES | YES | User | P0 |

### [FILE] endpoints/settings.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /project-types/{item_id} (L81) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User;UserRole | P0 |
| /project-statuses/{item_id} (L108) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User;UserRole | P0 |
| /task-statuses/{item_id} (L135) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User;UserRole | P0 |
| /departments/{item_id} (L162) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User;UserRole | P0 |
| /holidays/{item_id} (L186) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User;UserRole | P0 |

### [FILE] endpoints/skills.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /catalog/{skill_id} (L60) | Soft-delete + No ABAC | NO | YES | YES | Skill;SkillHistory;User;UserRole;UserSkill | P0 |
| /users/{user_id}/{skill_id} (L113) | Hard-delete + No ABAC | YES | YES | YES | Skill;SkillHistory;User;UserRole;UserSkill | P0 |

### [FILE] endpoints/sprints.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{project_id}/sprints/{sprint_id}/tasks/{task_id} (L194) | Hard-delete + No ABAC | YES | YES | YES | Absence;AbsenceStatus;CapacityPlan;Imputation;Project;Sprint;SprintStatus;SprintTask;Task;Timesheet;TimesheetStatus;User;UserRole | P0 |

### [FILE] endpoints/tasks.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{task_id} (L219) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | DependencyType;Project;ProjectMember;SemAssignment;SemConfig;SemEmbeddingCache;SemFeedback;SemProfile;Task;TaskComment;TaskDependency;TaskMovementLog;TaskPriority;TaskStatus;ThreadedComment;Ticket;User;UserRole;UserSkill | P0 |
| /dependencies/{dep_id} (L317) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | DependencyType;Project;ProjectMember;SemAssignment;SemConfig;SemEmbeddingCache;SemFeedback;SemProfile;Task;TaskComment;TaskDependency;TaskMovementLog;TaskPriority;TaskStatus;ThreadedComment;Ticket;User;UserRole;UserSkill | P0 |

### [FILE] endpoints/training.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /courses/{course_id} (L55) | Soft-delete + No ABAC + Bad response | NO | YES | YES | Certification;Course;CourseEnrollment;User;UserRole | P0 |
| /enrollments/{enroll_id} (L106) | Hard-delete + No ABAC + Bad response | YES | YES | YES | Certification;Course;CourseEnrollment;User;UserRole | P0 |

### [FILE] endpoints/user_costs.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /countries/{preset_id} (L161) | Hard-delete + No ABAC | YES | YES | YES | CountryEmployerCost;User;UserCostProfile | P0 |
| /profiles/{profile_id} (L269) | Hard-delete + No ABAC | YES | YES | YES | CountryEmployerCost;User;UserCostProfile | P0 |

### [FILE] endpoints/users.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /{user_id} (L195) | Soft-delete + ABAC + Bad response | NO | NO | YES | Imputation;Task;TaskStatus;User;UserPreference;UserRole;UserStatus | P1 |
| /{user_id}/permanent (L210) | Hard-delete + Bad response | YES | NO | YES | Imputation;Task;TaskStatus;User;UserPreference;UserRole;UserStatus | P0 |

### [FILE] endpoints/v239/baselines.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /projects/{project_id}/baselines/{baseline_id} (L196) | Hard-delete + No ABAC + Bad response | YES | YES | YES | User | P0 |

### [FILE] endpoints/v239/branding.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /orgs/{org_id}/branding (L155) | Hard-delete + No ABAC + No dependency validation + Bad response | YES | YES | YES | User | P0 |

### [FILE] routers/auth_mfa.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /mfa/webauthn/credentials/{credential_id} (L347) | Soft-delete + No ABAC | NO | YES | YES | MFAChallenge;Organization;SSOConfig;User;UserRole;UserSession;UserStatus;WebAuthnCredential | P0 |

### [FILE] routers/auth_sessions.py

| Endpoint | Current Pattern | Needs is_active? | Needs enforce_abac? | Needs service fix? | Model | Priority |
|---|---|---|---|---|---|---|
| /sessions/{session_id} (L56) | Hard-delete + No ABAC + No dependency validation | YES | YES | YES | MFAChallenge;Organization;SSOConfig;User;UserRole;UserSession;UserStatus;WebAuthnCredential | P0 |

## 3) Archivos criticos (40-50) con problemas
Seleccionados: Top 50 por cantidad de endpoints con gap en ABAC o soft-delete (desempate por score total de gaps).

1. app/api/v1/endpoints/enterprise.py (critical_endpoints=9, score=42)
2. app/api/v1/endpoints/cmdb.py (critical_endpoints=8, score=40)
3. app/api/v1/endpoints/advanced_config.py (critical_endpoints=8, score=32)
4. app/api/v1/endpoints/service_desk/misc.py (critical_endpoints=8, score=28)
5. app/api/v1/endpoints/alm.py (critical_endpoints=7, score=35)
6. app/api/v1/endpoints/epics.py (critical_endpoints=7, score=35)
7. app/api/v1/endpoints/clients.py (critical_endpoints=5, score=25)
8. app/api/v1/endpoints/settings.py (critical_endpoints=5, score=25)
9. app/api/v1/endpoints/custom_fields.py (critical_endpoints=5, score=23)
10. app/api/v1/endpoints/mfa.py (critical_endpoints=4, score=20)
11. app/api/v1/endpoints/pipeline.py (critical_endpoints=4, score=19)
12. app/api/v1/endpoints/bookings.py (critical_endpoints=3, score=15)
13. app/api/v1/endpoints/issue_types.py (critical_endpoints=3, score=15)
14. app/api/v1/endpoints/raci.py (critical_endpoints=3, score=15)
15. app/api/v1/endpoints/billing_reports.py (critical_endpoints=3, score=14)
16. app/api/v1/endpoints/ai_chat.py (critical_endpoints=3, score=13)
17. app/api/v1/endpoints/documents.py (critical_endpoints=3, score=13)
18. app/api/v1/endpoints/collaboration/messages.py (critical_endpoints=3, score=12)
19. app/api/v1/endpoints/rate_cards.py (critical_endpoints=3, score=12)
20. app/api/v1/endpoints/revenue.py (critical_endpoints=3, score=12)
21. app/api/v1/endpoints/collaboration/workspaces.py (critical_endpoints=3, score=11)
22. app/api/v1/endpoints/service_desk/sla.py (critical_endpoints=3, score=11)
23. app/api/v1/endpoints/approvals.py (critical_endpoints=3, score=9)
24. app/api/v1/endpoints/activity.py (critical_endpoints=2, score=10)
25. app/api/v1/endpoints/cab.py (critical_endpoints=2, score=10)
26. app/api/v1/endpoints/tasks.py (critical_endpoints=2, score=10)
27. app/api/v1/endpoints/projects/__init__.py (critical_endpoints=2, score=9)
28. app/api/v1/endpoints/service_desk/templates.py (critical_endpoints=2, score=9)
29. app/api/v1/endpoints/abac.py (critical_endpoints=2, score=8)
30. app/api/v1/endpoints/bi_smart_alerts.py (critical_endpoints=2, score=8)
31. app/api/v1/endpoints/portfolio.py (critical_endpoints=2, score=8)
32. app/api/v1/endpoints/service_desk/oncall.py (critical_endpoints=2, score=8)
33. app/api/v1/endpoints/service_desk/tickets.py (critical_endpoints=2, score=8)
34. app/api/v1/endpoints/training.py (critical_endpoints=2, score=7)
35. app/api/v1/endpoints/bi_platform.py (critical_endpoints=2, score=6)
36. app/api/v1/endpoints/okrs.py (critical_endpoints=2, score=6)
37. app/api/v1/endpoints/user_costs.py (critical_endpoints=2, score=6)
38. app/api/v1/endpoints/skills.py (critical_endpoints=2, score=5)
39. app/api/v1/endpoints/automations.py (critical_endpoints=1, score=5)
40. app/api/v1/endpoints/bi_conditional_delivery.py (critical_endpoints=1, score=5)
41. app/api/v1/endpoints/bi_embed.py (critical_endpoints=1, score=5)
42. app/api/v1/endpoints/bi_query_builder.py (critical_endpoints=1, score=5)
43. app/api/v1/endpoints/client_portal.py (critical_endpoints=1, score=5)
44. app/api/v1/endpoints/collaboration/admin.py (critical_endpoints=1, score=5)
45. app/api/v1/endpoints/collaboration/tus.py (critical_endpoints=1, score=5)
46. app/api/v1/endpoints/expenses.py (critical_endpoints=1, score=5)
47. app/api/v1/endpoints/integrations/__init__.py (critical_endpoints=1, score=5)
48. app/api/v1/endpoints/marketplace.py (critical_endpoints=1, score=5)
49. app/api/v1/endpoints/scim.py (critical_endpoints=1, score=5)
50. app/api/v1/endpoints/service_desk/assets.py (critical_endpoints=1, score=5)

## 4) Detalle por archivo critico
Formato:
- Import enforce_abac
- Endpoints to fix (lineas)
- Service changes
- Model changes
- Migration needed
- Priority

[FILE] endpoints/enterprise.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /project-permissions/{project_id}/{permission_id} (L78); /webhooks/{hook_id} (L122); /sso/{config_id} (L177); /notifications/clear-old (L221); /subcontractors/{sub_id} (L260); /subcontractors/{sub_id}/rates/{rate_id} (L281); /subcontractors/workers/{worker_id} (L349); /subcontractors/workers/{worker_id}/skills/{skill_ (L370); /subcontractors/{sub_id}/timelogs/{log_id} (L400); 
- Service changes: import app.services.enterprise_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AuditLog;Notification;Project;ProjectPermission;RevenueForecast;SSOConfig;Subcontractor;SubcontractorAssignment;SubcontractorInvoice;SubcontractorRate;SubcontractorTimeLog;SubcontractorWorker;SubcontractorWorkerSkill;User;UserRole;UserStatus;Webhook;WebhookDelivery;WebhookEvent
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/cmdb.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /wiki-tags/{tag_id} (L48); /wiki-pages/{page_id}/tags/{tag_id} (L60); /items/{item_id} (L250); /relations/{relation_id} (L278); /kanban/columns/{column_id} (L360); /sprint-plans/{plan_id} (L406); /sla-calendars/{cal_id} (L447); /sla-calendars/{cal_id}/holidays/{holiday_id} (L471); 
- Service changes: import app.services.cmdb_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Project;SprintTask;Task;User;WikiPage;WikiSpace
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/advanced_config.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /roles/{role_id} (L140); /task-types/{type_id} (L174); /rate-tables/{table_id}/entries/{entry_id} (L217); /rate-tables/{table_id} (L224); /vacation-policies/{policy_id} (L249); /offices/{office_id} (L282); /custom-fields/{field_id} (L328); /templates/{template_id} (L359); 
- Service changes: import app.services.advanced_config_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Absence;AbsenceStatus;AbsenceType;AlertConfig;CustomField;CustomFieldValue;CustomRole;Deliverable;NumberingSequence;Office;Project;ProjectPhase;ProjectTemplate;RateEntry;RateTable;Risk;Task;TaskPriority;TaskStatus;TaskType;TemplateDeliverable;TemplateDocument;TemplatePhase;TemplateRisk;TemplateRole;TemplateTask;User;UserVacationBalance;VacationPolicy
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/service_desk/misc.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /catalog/categories/{cat_id} (L95); /catalog/services/{service_id} (L113); /groups/{group_id} (L137); /groups/{group_id}/members/{user_id} (L149); /announcements/{ann_id} (L203); /routing-rules/{rule_id} (L228); /assets/{asset_id} (L443); /status-page/components/{component_id} (L481); 
- Service changes: from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback;from app.services.service_desk.problem_service import ( from app.services.service_desk.catalog_service import (;from app.services.service_desk.agent_group_service import ( from app.services.service_desk.workload_service import get_group_workload_payload;from app.services.service_desk.announcement_service import ( from app.services.service_desk.routing_rule_service import (;from app.services.service_desk.change_service import ( from app.services.service_desk.change_management_service import (;from app.services.service_desk.major_incident_service import ( from app.services.service_desk.asset_service import (;from app.services.service_desk.status_page_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/alm.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /vendors/{vid} (L54); /contracts/{cid} (L78); /licenses/{lid} (L102); /licenses/{lid}/assignments/{aid} (L112); /assets/{aid} (L136); /cost-centers/{cid} (L158); /assets/{aid}/installs/{iid} (L168); 
- Service changes: from app.services.alm_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: (por definir en servicio de dominio)
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/epics.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /wiki/spaces/{space_id} (L54); /wiki/pages/{page_id} (L90); /filters/{filter_id} (L191); /comments/{comment_id} (L253); /{epic_id} (L272); /{epic_id}/tasks/{task_id} (L284); /{epic_id}/dependencies/{depends_on_id} (L296); 
- Service changes: from app.services.epics_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Project;Task;Ticket;User;WikiTemplate
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/clients.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{cid} (L73); /{cid}/contacts/{contact_id} (L100); /{cid}/licenses/{link_id} (L117); /{cid}/contracts/{link_id} (L134); /{cid}/projects/{project_id}/link (L250); 
- Service changes: from app.services.client_service import (;import app.services.client_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ALMLicense;Client;ClientContact;ClientContractLink;ClientLicenseLink;ClientPortalConfig;ClientUser;Contract;Invoice;Project;Ticket;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/settings.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /project-types/{item_id} (L81); /project-statuses/{item_id} (L108); /task-statuses/{item_id} (L135); /departments/{item_id} (L162); /holidays/{item_id} (L186); 
- Service changes: import app.services.settings_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User;UserRole
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/custom_fields.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /custom-fields/{project_id}/{field_id} (L59); /project-workflows/{project_id}/states/{state_id} (L130); /project-workflows/{project_id}/transitions/{trans (L150); /project-workflows/{project_id}/reset (L169); /permissions/{project_id}/{permission_id} (L223); 
- Service changes: import app.services.custom_fields_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Project;ProjectCustomField;ProjectCustomFieldValue;ProjectPermission;ProjectPermissionLevel;Task;User;WorkflowState;WorkflowTransition
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/mfa.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /organizations/{org_id}/remove-user/{user_id} (L24); /mfa/disable (L122); /scenarios/{scenario_id} (L468); /bi/tokens/{token_id} (L548); 
- Service changes: import app.services.mfa_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Imputation;Project;Task;Ticket;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/pipeline.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{opp_id} (L85); /proposals/templates/{template_id} (L217); /stages/{stage_id} (L345); /stage-configs/{stage_id} (L346); 
- Service changes: from app.services import pipeline_service;from app.services.pipeline_service import STAGE_LABELS, serialize_opportunity as _opp_out from app.services import proposal_service as proposal_svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Opportunity;OpportunityActivity;OpportunityStage;PipelineStageConfig;Project;ProjectStatus;ProjectType;ProposalTemplate;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/bookings.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{booking_id} (L95); /sla-schedules/{schedule_id}/holidays/{holiday_id} (L128); /api-keys/{key_id} (L150); 
- Service changes: from app.services import bookings_service as svc;from app.services import v238_service; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ApiKey;AutomationWorkflow;BookingType;Document;DocumentCollabSnapshot;ExchangeRate;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;PipelineStageConfig;Project;ProjectCustomField;ProjectCustomFieldValue;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Task;TaskDependency;Ticket;User;WorkflowExecution;WorkflowQueueItem
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/issue_types.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /issue-types/{project_id}/{type_id} (L125); /task-dependencies/{dep_id} (L184); /epic-dependencies/{dep_id} (L227); 
- Service changes: import app.services.issue_type_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Epic;Project;Task;User;WikiPage;WikiSpace
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/raci.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /projects/{project_id}/raci/{entry_id} (L85); /projects/{project_id}/changelog/{entry_id} (L242); /projects/{project_id}/uat/{case_id} (L304); 
- Service changes: import app.services.raci_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: BurnoutRiskSnapshot;ChangelogEntryType;Imputation;Project;ProjectChangelogEntry;RACIRole;Sprint;SprintRetroNote;SprintTask;Task;TaskPriority;TaskStatus;UATStatus;User;UserStatus
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/billing_reports.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /report-catalog/{report_id} (L145); /automation-workflows/{wf_id} (L408); /scheduled-reports/{report_id} (L557); 
- Service changes: from app.services.billing_reports.history_service import (;from app.services.billing_reports.report_catalog_service import ( from app.services.billing_reports.data_source_service import (;from app.services.psa_flows import build_invoice_preview_from_timesheets_flow from app.services import bookings_service as _bookings_svc;import app.services.billing_reports_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Absence;AbsenceStatus;ApiKey;AutomationWorkflow;BookingType;CapacityPlan;ExchangeRate;Expense;Imputation;Invoice;InvoiceLine;OAuthState;Opportunity;OpportunityStage;Project;ProjectPhase;ProjectStatus;RecurringInvoice;ResourceBooking;SLAHoliday;SLASchedule;SSOConfig;Sprint;SprintStatus;SprintTask;Task;TaskDependency;Ticket;Timesheet;TimesheetStatus;User;UserRole;UserSkill;WorkflowExecution;WorkflowQueueItem;WorkflowStep
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/ai_chat.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /ai/conversations/{conv_id} (L405); /ai/conversations (L417); /governance/prompts/{prompt_id} (L764); 
- Service changes: from app.services.ai_dispatch import call_ai, get_default_provider;from app.services.ai_governance import check_prompt, check_output from app.services.ai_client import (  # noqa: E402;from app.services.ai_chat.context_service import build_tenant_context as _build_tenant_context  # noqa: E402 import app.services.ai_chat_service as _svc  # noqa: E402; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AIGuardrailAuditLog;AIGuardrailPolicyModel;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/documents.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{doc_id} (L163); /{doc_id}/permissions/{perm_id} (L305); /{doc_id}/tags/{tag_name} (L595); 
- Service changes: from app.services.s3_service import file_storage;from app.services.ai_dispatch import call_ai from app.services import documents_service as doc_svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ApprovalStatus;Document;DocumentAccessLevel;DocumentAccessLog;DocumentCategory;DocumentPermission;DocumentTag;DocumentVersion;User;UserRole
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/collaboration/messages.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /messages/{message_id} (L80); /conversations/{conversation_id}/pins/{message_id} (L114); /saved/{message_id} (L132); 
- Service changes: from app.services.collaboration import messages as msg_svc;from app.services.collaboration._permissions import _org, assert_conversation_access; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/rate_cards.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{table_id} (L128); /{table_id}/entries/{entry_id} (L176); /{table_id}/overrides/{override_id} (L198); 
- Service changes: import app.services.rate_card_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: RateEntry;RateOverride;RateTable;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/revenue.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /contracts/{contract_id} (L90); /obligations/{obligation_id} (L134); /period-closes/{year}/{month} (L195); 
- Service changes: from app.services import revenue_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Project;ProjectMilestone;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/collaboration/workspaces.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /teams/{team_id}/members/{user_id} (L140); /conversations/{conversation_id}/members/{user_id} (L343); /search/saved/{saved_id} (L584); 
- Service changes: from app.services.collaboration import audit_log;from app.services.collaboration._bus import bus, user_channel from app.services.collaboration._permissions import (;from app.services.collaboration._search import search_engine from app.services.collaboration import workspaces as ws_svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/service_desk/sla.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /sla-policies/{policy_id} (L46); /sla-holidays/{holiday_id} (L79); /escalation-rules/{rule_id} (L105); 
- Service changes: from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback;from app.services.service_desk.sla_policy_service import ( from app.services.service_desk.sla_assignment_service import assign_sla_policy_target, sla_policy_id_from_payload;from app.services.service_desk.holiday_service import list_holidays_payload, create_holiday_record, delete_holiday as delete_holiday_svc from app.services.service_desk.escalation_service import (;from app.services.service_desk.metrics_service import priority_matrix_payload; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/approvals.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /workflows/{workflow_id} (L174); /workflows/{workflow_id}/steps/{step_id} (L212); /groups/{group_id} (L431); 
- Service changes: from app.services.approval_engine import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ApprovalDecision;ApprovalGroup;ApprovalRequest;ApprovalStep;ApprovalWorkflow;FinancialApprovalAuditLog;User;UserRole
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/activity.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /recurring-tasks/{rt_id} (L214); /pipeline/resource-demand-lines/{line_id} (L354); 
- Service changes: from app.services.activity_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ALMVendor;ActivityEvent;Budget;ClientHealthSnapshot;Imputation;Mention;Notification;NotificationType;Opportunity;OpportunityStage;Project;ProjectHealthSnapshot;ProjectStatus;RecurringFreqType;RecurringTask;ResourceDemandForecast;Task;TaskDependency;TaskStatus;User;VendorScore
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/cab.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /webhooks/{trigger_id} (L246); /dashboard-widgets/reset (L413); 
- Service changes: import app.services.cab_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: CABVote;CalendarEvent;ChangeRequest;ChangeRequestWindow;CommitLink;DashboardWidget;EmailLog;EmailTemplate;GDPRRequest;GDPRRequestStatus;GDPRRequestType;Imputation;IntegrationConfig;Invoice;MaintenanceWindow;OnboardingState;Opportunity;Project;ProjectRiskScore;RecognitionMethod;RevenueRecognitionEntry;RevenueRecognitionRule;Risk;Sprint;Task;Ticket;User;WorkflowQueueItem
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/tasks.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{task_id} (L219); /dependencies/{dep_id} (L317); 
- Service changes: from app.services.task_service import (;from app.services.semantic_engine_service import enrich_suggestion from app.services.semantic_classifier import SemanticAssigner; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: DependencyType;Project;ProjectMember;SemAssignment;SemConfig;SemEmbeddingCache;SemFeedback;SemProfile;Task;TaskComment;TaskDependency;TaskMovementLog;TaskPriority;TaskStatus;ThreadedComment;Ticket;User;UserRole;UserSkill
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/projects/__init__.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{project_id} (L163); /{project_id}/members/{member_id} (L218); 
- Service changes: from app.services.project_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Client;Imputation;Project;ProjectMember;ProjectMilestone;ProjectPhase;ProjectStatus;ProjectType;Task;TaskStatus;User;UserRole
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/service_desk/templates.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /ticket-templates/{template_id} (L47); /canned-responses/{canned_id} (L78); 
- Service changes: from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback;from app.services.service_desk.ticket_template_service import ( from app.services.service_desk.canned_response_service import (;from app.services.service_desk.customer_context_service import get_customer_context_payload from app.services.service_desk.inbound_email_service import process_inbound_email; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/abac.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /users/{user_id}/attributes/{attribute_key} (L145); /policies/{policy_id} (L258); 
- Service changes: from app.services.abac import ABACService, DEFAULT_ABAC_ATTRIBUTES; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ABACPolicy;AttributeDefinition;PolicyAudit;User;UserAttribute
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/bi_smart_alerts.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /bi/alerts/custom-metrics/{key} (L94); /bi/alerts/rules/{rule_id} (L156); 
- Service changes: from app.services import bi_smart_alerts_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AppSetting;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/portfolio.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{portfolio_id} (L86); /{portfolio_id}/projects/{project_id} (L125); 
- Service changes: from app.services import portfolio_service;from app.services.portfolio_service import serialize_portfolio as _serialize_portfolio; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Imputation;Portfolio;PortfolioProject;Project;ProjectMilestone;Task;TaskStatus;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/service_desk/oncall.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /oncall/schedules/{schedule_id} (L40); /oncall/entries/{entry_id} (L54); 
- Service changes: from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback;from app.services.service_desk.oncall_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/service_desk/tickets.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /tickets/{ticket_id}/links/{link_id} (L264); /tickets/{ticket_id}/watch (L302); 
- Service changes: from app.services.service_desk.ticket_ops_service import commit_or_rollback as _commit_or_rollback;from app.services.sla_service import ticket_out as _ticket_out from app.services.service_desk.ticket_read_service import (;from app.services.service_desk.ticket_update_service import get_scoped_ticket_or_404, apply_ticket_update from app.services.service_desk.ticket_creation_service import build_internal_ticket, build_client_portal_ticket;from app.services.service_desk.comment_service import ( from app.services.service_desk.csat_service import submit_ticket_csat;from app.services.service_desk.ticket_ops_service import ( from app.services.service_desk.link_service import (;from app.services.service_desk.sla_event_service import ( from app.services.service_desk.watcher_service import (;from app.services.service_desk.merge_split_service import ( from app.services.service_desk.ai_suggest_service import build_ai_ticket_suggestion;from app.services.service_desk.workload_service import auto_assign_ticket_command, score_agent_for_ticket, auto_assign_ticket_ml_command from app.services.service_desk.incident_intelligence_service import score_auto_resolution;from app.services.service_desk.kb_service import create_kb_from_ticket from app.services.service_desk.portal_auth_service import require_portal_client;from app.services.service_desk.semantic_feedback_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AgentGroupMember;ClientUser;ConfigurationItem;KBArticle;Problem;SDSLAHoliday;Ticket;TicketHistory;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/training.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /courses/{course_id} (L55); /enrollments/{enroll_id} (L106); 
- Service changes: from app.services import training_service;from app.services.training_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Certification;Course;CourseEnrollment;User;UserRole
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/bi_platform.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /bi/platform/connectors/custom/{connector_id} (L190); /bi/platform/governance/field-sensitivity/{sensiti (L347); 
- Service changes: from app.services import bi_platform_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AppSetting;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/okrs.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{obj_id} (L61); /key-results/{kr_id} (L96); 
- Service changes: from app.services import okr_service;from app.services.okr_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: KRCheckin;KeyResult;Objective;Project;Task;TaskStatus;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/user_costs.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /countries/{preset_id} (L161); /profiles/{profile_id} (L269); 
- Service changes: import app.services.cost_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: CountryEmployerCost;User;UserCostProfile
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/skills.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /catalog/{skill_id} (L60); /users/{user_id}/{skill_id} (L113); 
- Service changes: from app.services import skill_service; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Skill;SkillHistory;User;UserRole;UserSkill
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/automations.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{rule_id} (L83); 
- Service changes: import app.services.automations_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: ActionType;Alert;AlertSeverity;AlertType;AutomationExecution;AutomationRule;Project;Task;Timesheet;TriggerType;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/bi_conditional_delivery.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /bi/delivery/rules/{rule_id} (L121); 
- Service changes: from app.services import bi_conditional_delivery_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AppSetting;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/bi_embed.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /token/{jti} (L42); 
- Service changes: from app.services import bi_embed_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/bi_query_builder.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /bi/query-builder/queries/{query_id} (L159); 
- Service changes: from app.services import bi_query_builder_service as svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AppSetting;User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/client_portal.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /clients/{client_id} (L241); 
- Service changes: import app.services.client_portal_service as _svc; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: AppSetting;ApprovalRequest;ChangeRequest;ChangeRequestImpact;ChangeRequestStatus;Client;ClientDocument;ClientMessage;ClientPortalConfig;ClientSurvey;ClientUser;Deliverable;DeliverableStatus;FeatureRequest;FeatureRequestStatus;Imputation;Invoice;InvoiceStatus;Project;ProjectMilestone;Ticket;TicketStatus;UATIssue;UATSession;UATStatus;UATTestCase;User;WikiPage;client_user_projects
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/collaboration/admin.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /push/unsubscribe (L74); 
- Service changes: from app.services.collaboration import _push as push_svc;from app.services.collaboration._integrations import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/collaboration/tus.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /tus/{uid} (L255); 
- Service changes: from app.services.collaboration import audit_log;from app.services.collaboration._permissions import _org, assert_conversation_access from app.services.collaboration._storage import scan_dlp, scan_with_av, storage; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/expenses.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /my/{expense_id} (L187); 
- Service changes: from app.services.expense_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Expense;ExpenseStatus;Project;ProjectStatus;User;UserRole
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/integrations/__init__.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /instances/{instance_id} (L58); 
- Service changes: from app.services import marketplace_service; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: IntegrationConnector;IntegrationInstance
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/marketplace.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /uninstall (L32); 
- Service changes: (endpoint realiza logica inline; crear/usar servicio de dominio); convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: (por definir en servicio de dominio)
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/scim.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /Users/{user_id} (L173); 
- Service changes: from app.services.scim_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: Organization;User;UserRole;UserStatus
- Migration needed: Yes
- Priority: P0

[FILE] endpoints/service_desk/assets.py
- Import: from app.core.abac_enforce import enforce_abac
- Endpoints to fix: /{asset_id} (L283); 
- Service changes: from app.services.service_desk.asset_service import (; convertir delete fisico a soft-delete cuando aplique; agregar validacion de dependencias; estandarizar respuesta {"ok": true, "message": "..."}
- Model changes: User
- Migration needed: Yes
- Priority: P0

## 5) Checklist de dependencias y orden de migracion

### Checklist global (aplicar a todos los dominios)
- [ ] Inventariar modelos realmente persistidos por cada DELETE endpoint.
- [ ] Confirmar si el recurso es archivado (soft-delete) o revocado/purge legitimo.
- [ ] Agregar columna is_active BOOLEAN NOT NULL DEFAULT TRUE a cada modelo persistido que hoy hace hard-delete.
- [ ] Crear indices compuestos para unicidad con is_active cuando exista UNIQUE funcional.
- [ ] Actualizar servicios: reemplazar db.delete() por is_active=False + commit.
- [ ] Actualizar lecturas/listados con filtro is_active=True.
- [ ] Insertar enforce_abac() en todos los DELETE antes de mutar.
- [ ] Implementar validacion de dependencias activas antes de eliminar.
- [ ] Normalizar respuestas DELETE al contrato {"ok": true, "message": "..."}.
- [ ] Actualizar tests unitarios, API y regresion para soft-delete + ABAC.

### Orden recomendado de migracion (dependencias)
1. Core identity y acceso: users, abac, auth routers, mfa.
2. Configuracion transversal: settings, advanced_config, enterprise.
3. Estructura de proyectos: projects, clients, pipeline, tasks, epics, sprints, milestones.
4. Gobernanza y aprobaciones: approvals, grc, ai_governance.
5. Operacion y service desk: service_desk/*, bookings, capacity, changes.
6. Datos empresariales: cmdb, alm, contracts, profitability, revenue.
7. BI/Analytics: bi_* y report_builder, billing_reports.
8. Colaboracion e integraciones: collaboration/*, integrations, m365, scim, jira.

## 6) Top 10 + plan de ejecucion + LOC estimadas

### Top 10 archivos por numero de endpoints rotos
1. app/api/v1/endpoints/enterprise.py -> 9 endpoints rotos
2. app/api/v1/endpoints/advanced_config.py -> 8 endpoints rotos
3. app/api/v1/endpoints/cmdb.py -> 8 endpoints rotos
4. app/api/v1/endpoints/service_desk/misc.py -> 8 endpoints rotos
5. app/api/v1/endpoints/alm.py -> 7 endpoints rotos
6. app/api/v1/endpoints/epics.py -> 7 endpoints rotos
7. app/api/v1/endpoints/clients.py -> 5 endpoints rotos
8. app/api/v1/endpoints/custom_fields.py -> 5 endpoints rotos
9. app/api/v1/endpoints/settings.py -> 5 endpoints rotos
10. app/api/v1/endpoints/mfa.py -> 4 endpoints rotos

### Top 10 modelos/dominios que mas requieren is_active
(estimado por endpoints con SoftDelete=False agrupados por archivo de endpoint)
1. endpoints/advanced_config.py -> 8 endpoints sin is_active
2. endpoints/cmdb.py -> 8 endpoints sin is_active
3. endpoints/enterprise.py -> 8 endpoints sin is_active
4. endpoints/alm.py -> 7 endpoints sin is_active
5. endpoints/epics.py -> 7 endpoints sin is_active
6. endpoints/clients.py -> 5 endpoints sin is_active
7. endpoints/custom_fields.py -> 5 endpoints sin is_active
8. endpoints/settings.py -> 5 endpoints sin is_active
9. endpoints/mfa.py -> 4 endpoints sin is_active
10. endpoints/pipeline.py -> 4 endpoints sin is_active

### Plan de ejecucion por prioridad
- P0 (bloqueante): cualquier endpoint con Hard-delete o sin ABAC.
- P1 (alto): endpoint con soft-delete+ABAC pero sin validacion/filter/response.
- P2 (normalizacion): consistencia de respuesta y filtros globales, deuda de tests.

Batch sugeridos:
1. Batch A (P0-config): advanced_config, settings, enterprise, users, auth routers.
2. Batch B (P0-core work): projects, clients, pipeline, tasks, epics, sprints, milestones.
3. Batch C (P0-ops): service_desk/*, bookings, capacity, changes, approvals.
4. Batch D (P0-data): cmdb, alm, contracts, revenue, profitability.
5. Batch E (P1/P2-analytics): bi_*, report_builder, billing_reports.
6. Batch F (P1/P2-collab/integrations): collaboration/*, integrations, m365, scim, jira.

### LOC estimadas por archivo (heuristica)
Formula: 14 LOC por endpoint roto + 8 LOC por archivo para imports/helpers.
- app/api/v1/endpoints/enterprise.py: ~134 LOC (9 endpoints rotos)
- app/api/v1/endpoints/advanced_config.py: ~120 LOC (8 endpoints rotos)
- app/api/v1/endpoints/cmdb.py: ~120 LOC (8 endpoints rotos)
- app/api/v1/endpoints/service_desk/misc.py: ~120 LOC (8 endpoints rotos)
- app/api/v1/endpoints/alm.py: ~106 LOC (7 endpoints rotos)
- app/api/v1/endpoints/epics.py: ~106 LOC (7 endpoints rotos)
- app/api/v1/endpoints/clients.py: ~78 LOC (5 endpoints rotos)
- app/api/v1/endpoints/custom_fields.py: ~78 LOC (5 endpoints rotos)
- app/api/v1/endpoints/settings.py: ~78 LOC (5 endpoints rotos)
- app/api/v1/endpoints/mfa.py: ~64 LOC (4 endpoints rotos)
- app/api/v1/endpoints/pipeline.py: ~64 LOC (4 endpoints rotos)
- app/api/v1/endpoints/ai_chat.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/approvals.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/billing_reports.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/bookings.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/collaboration/messages.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/collaboration/workspaces.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/documents.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/issue_types.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/raci.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/rate_cards.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/revenue.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/service_desk/sla.py: ~50 LOC (3 endpoints rotos)
- app/api/v1/endpoints/abac.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/activity.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/bi_platform.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/bi_smart_alerts.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/cab.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/okrs.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/portfolio.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/projects/__init__.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/service_desk/oncall.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/service_desk/templates.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/service_desk/tickets.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/skills.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/tasks.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/training.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/user_costs.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/users.py: ~36 LOC (2 endpoints rotos)
- app/api/v1/endpoints/absences.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/ai_governance.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/ai_providers.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/automations.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bi_bookmarks.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bi_conditional_delivery.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bi_embed.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bi_intelligence.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bi_query_builder.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bi_report_builder_v2.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/bpmn_processes.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/capacity.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/changes.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/client_portal.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/collaboration/admin.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/collaboration/bots.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/collaboration/tus.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/contracts.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/deliverables.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/developer_portal.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/esign.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/expenses.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/grc.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/imputations.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/integrations/__init__.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/jira_integration.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/m365.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/marketplace.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/milestones.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/profitability.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/public_forms.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/report_builder.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/risks.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/scim.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/service_desk/assets.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/service_desk/autonomous.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/service_desk/cmdb.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/service_desk/kb.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/service_desk/workflow_designer.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/sprints.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/v239/baselines.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/endpoints/v239/branding.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/routers/auth_mfa.py: ~22 LOC (1 endpoints rotos)
- app/api/v1/routers/auth_sessions.py: ~22 LOC (1 endpoints rotos)

## Anexo: discrepancia 182 vs 187
- Escaneo directo de decoradores detecta 187 @router.delete.
- Baseline contractual auditado (matriz) contiene 182.
- Recomendacion: ejecutar reconciliacion final antes de cerrar QA para incluir/excluir explicitamente los 5 extras.
