from app.models.user import User, UserRole, UserStatus  # noqa: F401
from app.models.public_forms import PublicForm, PublicFormSubmission  # noqa: F401
from app.models.oauth_apps import OAuthApp, OAuthToken  # noqa: F401
from app.models.project import Project, ProjectPhase, ProjectType, ProjectStatus, ProjectRisk  # noqa: F401
from app.models.task import Task, TaskComment, TaskStatus, TaskPriority  # noqa: F401
from app.models.imputation import Imputation, TimerSession, ImputationAlert, ImputationSnapshot  # noqa: F401
from app.models.alert import Alert  # noqa: F401
from app.models.settings import AppSetting, CustomProjectType, CustomProjectStatus, CustomTaskStatus, Department, Holiday  # noqa: F401
from app.models.financial import Timesheet, CapacityPlan, ProjectMilestone, TimesheetStatus  # noqa: F401
from app.models.sprints import Sprint, SprintTask, SprintStatus  # noqa: F401
from app.models.pipeline import Opportunity, OpportunityActivity, OpportunityStage, Contract, WorkOrder, ContractType, ContractStatus, Risk, RiskProbability, RiskImpact, RiskStatus, PipelineStageConfig  # noqa: F401
from app.models.resources import Skill, UserSkill, SkillLevel, SkillCategory, Absence, AbsenceType, AbsenceStatus, ChangeRequest, ChangeRequestStatus, ChangeRequestImpact, Deliverable, DeliverableStatus, ResourceAlert, ResourceAlertType, ResourceUtilizationSnapshot  # noqa: F401
from app.models.advanced_config import CustomRole, ProjectTemplate, TemplatePhase, TemplateTask, TemplateRisk, TemplateDeliverable, TaskType, AlertConfig, RateTable, RateEntry, VacationPolicy, UserVacationBalance, Office, NumberingSequence, CustomField, CustomFieldValue  # noqa: F401
from app.models.client_portal import ClientUser, ClientSession, FeatureRequest, FeatureRequestStatus, FeatureRequestPriority, UATSession, UATTestCase, UATIssue, UATStatus, ClientMessage, ClientSurvey, ClientDocument  # noqa: F401
from app.models.portal_conversations import (  # noqa: F401
    PortalConversationPolicy,
    PortalConversation, PortalConversationStatus, PortalConversationAssignmentMode,
    PortalConversationParticipant, PortalConversationParticipantType, PortalConversationRole,
    PortalConversationMessage, PortalConversationMessageType,
    PortalConversationClassification, PortalConversationGRCStatus, PortalConversationSource,
    PortalConversationAudit,
)
from app.models.service_desk import ServiceCategory, ServiceItem, SLAPolicy, ConfigurationItem, CIType, CIStatus, AgentGroup, AgentGroupMember, Ticket, TicketType, TicketStatus, TicketPriority, TicketUrgency, TicketImpact, SupportLevel, SLAStatus, TicketComment, TicketHistory, TicketTimeLog, Problem, ProblemStatus, KBArticle, KBArticleVersion, KBStatus, Announcement, AutonomousPlaybook, AutonomousPlaybookExecution, ITSMMetricSnapshot, ComplianceReport  # noqa: F401

from app.models.clients import Client, ClientStatus, ClientIndustry, ClientContact, ClientContactRole, ClientPortalConfig, ClientLicenseLink, ClientContractLink  # noqa: F401
from app.models.alm import ALMCostCenter, ALMVendor, ALMContract, ALMLicense, ALMAsset  # noqa: F401
from app.models.enterprise import (  # noqa: F401
    AuditLog, ProjectPermission, Webhook, WebhookDelivery, SSOConfig,
    Notification, Subcontractor, SubcontractorRate, SubcontractorAssignment,
    SubcontractorWorker, SubcontractorWorkerSkill,
    SubcontractorInvoice, SubcontractorTimeLog, RevenueForecast,
)
from app.models.billing_reports import (  # noqa: F401
    SLABreachLog, AutomationWorkflow, WorkflowStep, WorkflowExecution,
    ImportJob, Invoice, InvoiceLine, ReportDefinition, ScheduledReport,
    ApprovalWorkflow, ApprovalStep, ApprovalRequest, ApprovalDecision,
    FinancialApprovalAuditLog,
    RolePermission, SodRule, GrcAuditLog, SodViolation,
)
from app.models.bookings import (  # noqa: F401
    TaskDependency, ResourceBooking, ExchangeRate,
    SLASchedule, SLAHoliday, ApiKey, RecurringInvoice,
    WorkflowQueueItem, OAuthState,
)
from app.models.mfa import (  # noqa: F401 — Organization required for User.organization relationship
    Organization, MFAConfig, MFABackupCode, SlackConfig, SlackNotificationLog,
    Budget, BudgetEntry, AITaskEstimate, AITicketTriage,
    ScenarioModel, ScenarioProject, PDFExportJob,
    WebAuthnCredential, MFAChallenge,
)
from app.models.ai_chat import (  # noqa: F401
    AIConversation, AIMessage, AIAgentExecution, AIAgentStep,
    AIPrediction, AIAnomaly, AIGovernanceConfig, AIActionLog,
    AIMeeting, AIMeetingAction, AIContract, AIContractClause,
    AIKBArticle, AIVoiceCommand, AIClientChatSession, AIClientChatMessage,
)
from app.models.custom_fields import (  # noqa: F401
    WorkflowState, WorkflowTransition, ProjectCustomField, ProjectCustomFieldValue,
)
from app.models.epics import (  # noqa: F401
    WikiSpace, WikiPage, WikiVersion, WikiTemplate, WikiComment,
    Epic, EpicTask, EpicDependency, SavedFilter, TaskStateSnapshot,
    Mention, ThreadedComment,
)
from app.models.white_label import OrgBranding  # noqa: F401
from app.models.marketplace import (  # noqa: F401
    GanttBaseline, WhatIfTask,
    IntegrationConnector, IntegrationInstance,
    TemplateDocument, TemplateRole,
)
from app.models.issue_types import (  # noqa: F401
    IssueType, IssueTypeField, TaskDependencyMeta, EpicDependencyMeta, FTSEntry,
)
from app.models.cmdb import (  # noqa: F401
    WikiTag, WikiPageTag, TicketInternalComment, CMDBCategory, CMDBItem,
    CMDBRelation, AgentMetricSnapshot, WikiExportJob,
    KanbanConfig, KanbanColumn, SprintPlan, SprintPlanTask,
    SLACalendar, V21SLAHoliday, CMDBChangelog,
    CMDBDiscoveryProvider, CMDBDiscoveryJob,
)
from app.models.okrs import Objective, KeyResult, KRCheckin  # noqa: F401
from app.models.performance import ReviewCycle, PerformanceReview  # noqa: F401
from app.models.training import Course, CourseEnrollment, Certification  # noqa: F401
from app.models.documents import (  # noqa: F401
    Document, DocumentVersion, DocumentPermission, DocumentTag,
    DocumentCategory, DocumentAccessLevel, ApprovalStatus,
)
from app.models.portfolio import Portfolio, PortfolioProject, PortfolioStatus  # noqa: F401
from app.models.git_integration import GitPullRequest, GitDeployment, PRStatus, DeployStatus, GitProvider  # noqa: F401
from app.models.esign import ESignEnvelope, ESignSigner, ESignProvider, ESignStatus  # noqa: F401
from app.models.nps import ClientNPS, ClientHealthSnapshot, NPSCategory  # noqa: F401
from app.models.activity import (  # noqa: F401
    ActivityEvent, ProjectHealthSnapshot,
    RecurringTask, RecurringFreqType,
    ResourceDemandForecast, VendorScore,
)
from app.models.raci import (  # noqa: F401
    RACIEntry, RACIRole,
    SprintRetroNote,
    BurnoutRiskSnapshot, BurnoutRiskLevel,
    ProjectChangelogEntry, ChangelogEntryType,
)
from app.models.sessions import UserSession  # noqa: F401
from app.models.governance import TenantPolicyPack, ComplianceEvidence  # noqa: F401
from app.models.abac import (  # noqa: F401
    AttributeDefinition, UserAttribute, ABACPolicy, PolicyAudit,
)
from app.models.security_observability import (  # noqa: F401
    SecurityEvent, SecurityDetection, SecurityIncident,
    LoginAnomaly, SecurityMetricSnapshot,
    EventCategory, EventSeverity, IncidentStatus, KillChainStage,
)
from app.models.ai_governance import AIGuardrailPolicyModel, AIGuardrailAuditLog  # noqa: F401
from app.models.exchange_rates_log import CurrencyConversionLog  # noqa: F401  — ExchangeRate already declared in bookings.py
from app.models.document_collab import DocumentCollabSnapshot  # noqa: F401
from app.models.semantic_engine import (  # noqa: F401
    SemProfile, SemEmbeddingCache, SemAssignment, SemFeedback,
    SemConfig, SemEngineMode, SemAssignmentType,
)
from app.models.ai_providers import AIProvider, AIUsageLog  # noqa: F401
from app.models.revenue import (  # noqa: F401
    RevenueContract, RevenueObligation, RevenueEntry, RevenuePeriodClose,
    ASCMethod, EntryType,
)
from app.models.ml_model import MLModel, MLPredictionLog, MLModelType  # noqa: F401
from app.models.pipeline import ProposalTemplate  # noqa: F401  — ensures Alembic detects the new table
from app.models.jira_integration import (  # noqa: F401
    JiraConfig, JiraSyncMap, JiraSyncLog, JiraFieldMap,
    JiraSyncDirection, JiraSyncStatus, JiraSyncEventType,
)
from app.models.workflow_designer import (  # noqa: F401
    WorkflowBlueprint, WorkflowBlueprintVersion, WorkflowBlueprintStatus,
)
from app.models.service_desk_ai_governance import (  # noqa: F401
    SDAIEvaluationRun, SDAIDriftSnapshot,
)

