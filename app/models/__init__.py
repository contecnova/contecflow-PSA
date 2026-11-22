from app.models.user import User, UserRole, UserStatus, UserOrganizationMembership  # noqa: F401
from app.models.public_forms import PublicForm, PublicFormSubmission  # noqa: F401
from app.models.oauth_apps import OAuthApp, OAuthToken  # noqa: F401
from app.models.project import Project, ProjectPhase, ProjectType, ProjectStatus, ProjectRisk  # noqa: F401
from app.models.task import Task, TaskComment, TaskStatus, TaskPriority  # noqa: F401
from app.models.task_movement_log import TaskMovementLog  # noqa: F401
from app.models.imputation import Imputation, TimerSession, ImputationAlert, ImputationSnapshot  # noqa: F401
from app.models.alert import Alert  # noqa: F401
from app.models.settings import AppSetting, Area, CustomClientIndustry, CustomExpenseCategory, CustomProjectType, CustomProjectStatus, CustomSupplierBillingUnit, CustomSupplierServiceType, CustomTaskStatus, Department, Holiday  # noqa: F401
from app.models.financial import Timesheet, CapacityPlan, ProjectMilestone, TimesheetStatus  # noqa: F401
from app.models.sprints import Sprint, SprintTask, SprintStatus  # noqa: F401
from app.models.pipeline import Opportunity, OpportunityActivity, OpportunityStage, Contract, WorkOrder, ContractType, ContractStatus, Risk, RiskProbability, RiskImpact, RiskStatus, PipelineStageConfig  # noqa: F401
from app.models.resources import Skill, UserSkill, SkillLevel, SkillCategory, Absence, AbsenceType, AbsenceStatus, ChangeRequest, ChangeRequestStatus, ChangeRequestImpact, Deliverable, DeliverableStatus, ResourceAlert, ResourceAlertType, ResourceUtilizationSnapshot  # noqa: F401
from app.models.advanced_config import CustomRole, ProjectTemplate, TemplatePhase, TemplateTask, TemplateTaskDependency, TemplateRisk, TemplateDeliverable, TaskType, AlertConfig, RateTable, RateEntry, VacationPolicy, UserVacationBalance, Office, NumberingSequence, CustomField, CustomFieldValue  # noqa: F401
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
from app.models.alm import (  # noqa: F401
    ALMCostCenter, ALMVendor, ALMContract, ALMLicense, ALMAsset, ALMAssetHistory,
    ALMAsignacion, ALMEvento, ALMActa, ALMAdjunto, ALMPicoConcurrencia, ALMRenovacion, ALMFacturaProveedor,
)
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
    Organization, MFABackupCode, SlackConfig, SlackNotificationLog,
    Budget, BudgetLine, BudgetCampaign, BudgetTemplate, BudgetCommitment, BudgetClose, BudgetVarianceNote, BudgetTransfer, AITaskEstimate, AITicketTriage,
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
    GanttBaseline, GanttBaselineTask, WhatIfTask,
    IntegrationConnector, IntegrationInstance,
    TemplateDocument, TemplateRole,
)
from app.models.issue_types import (  # noqa: F401
    IssueType, IssueTypeField, EpicDependencyMeta, FTSEntry,
)
from app.models.cmdb import (  # noqa: F401
    WikiTag, WikiPageTag, WikiExportJob,
    KanbanConfig, KanbanColumn, SprintPlan, SprintPlanTask,
    SLACalendar, V21SLAHoliday, CMDBChangelog,
    CMDBDiscoveryProvider, CMDBDiscoveryJob,
)
from app.models.okrs import Objective, KeyResult, KRCheckin  # noqa: F401
from app.models.performance import (  # noqa: F401
    ReviewCycle, PerformanceReview, ReviewQuestion, QuestionKind,
    ReviewCycleStatus, ReviewStatus,
    Review360Campaign, Review360CampaignStatus,
    DevelopmentPlan, DevGoal, DevPlanStatus, DevGoalStatus,
)
from app.models.training import Course, CourseEnrollment, Certification  # noqa: F401
from app.models.documents import (  # noqa: F401
    Document, DocumentVersion, DocumentPermission, DocumentTag,
    DocumentCategory, DocumentAccessLevel, ApprovalStatus,
)
from app.models.portfolio import (  # noqa: F401
    Portfolio, PortfolioProject, PortfolioStatus,
    PortfolioCriterion, PortfolioGate, PortfolioProposal,
)
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
from app.models.governance import TenantPolicyPack, ComplianceEvidence, RetentionPolicy, LegalHold  # noqa: F401
from app.models.conectores import ConectorLlamada, EnlaceDocumental, CarpetaDocumental  # noqa: F401
from app.models.lecciones import Leccion, LeccionUso, LeccionAccion  # noqa: F401
from app.models.expenses import ExpenseAttachment, ExpenseAllocation  # noqa: F401
from app.models.politicas import (  # noqa: F401
    Politica, ReglaDePolitica, TablaDeReferencia, FilaDeTablaDeReferencia, EvaluacionDePolitica,
)
from app.models.ausencias import (  # noqa: F401
    TipoDeAusencia, TipoDeDocumentoDeAusencia, RequisitoDocumentalDeTipo, Turno, PatronDeTurnos, MiembroDePatron,
    AsignacionDeTurno, HuecoDeCupo, ReservaDeCupo, DocumentoDeAusencia, RequisitoDeAusencia, EventoDeAusencia,
    AccesoEspecialAusencias,
)
from app.models.horario import JornadaLaboral, AsignacionDeJornada, MovimientoDeSaldo  # noqa: F401 — rev. 180
from app.models.horas_extra import (  # noqa: F401 — rev. 184: horas extra
    ConfigDeHorasExtra, PeticionDeHorasExtra, EventoDeHorasExtra, PresupuestoDeHorasExtra,
)
from app.models.alm_uso import (  # noqa: F401  — licencias y hardware, fase 2: uso real
    ALMUsoConexion, ALMUsoSincronizacion, ALMUsoEvidencia, ALMUsoMapeo, ALMUsoDerecho, ALMUsoNivel,
    ALMUsoAjusteDecision, ALMUsoRecuperacion, ALMSoftwareNoControlado,
)
from app.models.alm_integracion import (  # noqa: F401  — licencias y hardware, fase 4: integración
    ALMKit, ALMKitElemento, ALMPropuestaDeKit, ALMBaja, ALMDevolucion, ALMItemDeCatalogo, ALMPeticion,
)
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
    WorkflowRun, WorkflowRunStatus, WorkflowRunStep, WorkflowRunStepStatus,
)
from app.models.bpmn_process import (  # noqa: F401
    BPMNInstance, BPMNInstanceStep,
    BPMNProcess, BPMNProcessVersion, BPMNProcessStatus,
)
from app.models.user_cost import (  # noqa: F401
    CountryEmployerCost, UserCostProfile,
)
from app.models.service_desk_ai_governance import (  # noqa: F401
    SDAIEvaluationRun, SDAIDriftSnapshot,
)
from app.models.bi_collaboration import (  # noqa: F401
    DashboardComment, DashboardVersion, DashboardShare, DashboardNotification,
)
from app.models.cab import (  # noqa: F401
    CABVote, MaintenanceWindow, ChangeRequestWindow,
    WebhookTrigger, WebhookTriggerLog,
    EmailTemplate, EmailLog,
    GDPRRequest, IntegrationConfig, CommitLink,
    CalendarEvent,
    DashboardWidget, OnboardingState, ProjectRiskScore,
)
from app.models.automations import AutomationRule, AutomationExecution, AutomationEvent  # noqa: F401
from app.models.expenses import Expense  # noqa: F401
from app.models.collaboration import (  # noqa: F401
    ConversationKind, ChannelType, TeamRole, ChannelRole,
    MessageType, MessageStatus, ReactionEmoji,
    CallKind, CallStatus, PresenceStatus,
    NotificationKind, ModerationVerdict,
    IntegrationKind, BotKind,
    CollaborationWorkspace, CollaborationTeam, CollaborationTeamMember,
    CollaborationConversation,
    CollaborationChannel, CollaborationChannelMember,
    CollaborationDirectConversation, CollaborationGroupConversation,
    CollaborationConversationMember,
    CollaborationMessage, CollaborationMessageVersion, CollaborationThread,
    CollaborationReaction, CollaborationMention, CollaborationRead,
    CollaborationAttachment, CollaborationAttachmentVersion,
    CollaborationCall, CollaborationCallParticipant,
    CollaborationRecording, CollaborationTranscript,
    CollaborationNotification, CollaborationPresenceState,
    CollaborationIntegration, CollaborationWebhook, CollaborationBotApp,
    CollaborationModerationCase, CollaborationRetentionPolicy,
    CollaborationLegalHold, CollaborationAuditEvent,
    CollaborationPinnedMessage, CollaborationSavedMessage,
    CollaborationDraft, CollaborationNotificationRule,
    CollaborationBotExecution, CollaborationSlashCommandLog,
    CollaborationSavedSearch, CollaborationPushSubscription,
)


# Proyectos — planificador, hub y vistas (rev. 173)
from app.models.planificacion import EvmSnapshot  # noqa: F401,E402


# Traduccion en tiempo real (rev. 175)
from app.models.traduccion import (  # noqa: F401,E402
    TranslationCacheEntry, MessageTranslation, TranslationGlossaryTerm, KBArticleTranslation,
    PortalContentTranslation,  # rev. 181: avisos y catalogo
)
# Proveedores y externalizacion (rev. 187)
from app.models.proveedores import (  # noqa: F401,E402
    SupplierContract, SupplierPricingLine, SupplierService, SupplierWorkPackage, SupplierReport,
    SupplierUsageRecord, SupplierStatement, SupplierDocument, SupplierRiskAssessment, SupplierAccessGrant,
)
# Asistente de reuniones (rev. 188, 19-11-2026)
from app.models.reuniones import (  # noqa: F401,E402
    AIMeetingParticipant, AIMeetingSegment, AIMeetingTranslation, AIMeetingAudio, AIMeetingEvent,
    AIMeetingUserPrefs,
)
# CMDB de software, composición y vulnerabilidades (rev. 190, 19-11-2026)
from app.models.cmdb_software import (  # noqa: F401,E402
    SoftwareProduct, SoftwareVersion, SoftwareComponent, SoftwareSbomImport, SoftwareProductLicense,
    SoftwareInstance, SoftwareInstanceRelation, SoftwareConfigSnapshot, SoftwareBaseline,
    Vulnerability, VulnerabilityAffect, VulnerabilityFinding, VulnerabilityException, SoftwareConfig,
    VulnerabilitySyncRun,
)
# Índice de riesgo y gestión de vulnerabilidades (rev. 194, 22-11-2026)
from app.models.cmdb_riesgo import (  # noqa: F401,E402
    RiskSnapshot, CompensatingControl, ExploitEvent, SavedVulnView, RiskAlertLog,
)
# Clientes internos: cargos, repartos, beneficios y adopción (rev. 193, 22-11-2026)
from app.models.clientes_internos import (  # noqa: F401,E402
    InternalClientRole, InternalSharedCost, InternalCharge, InternalChargeLine,
    ProjectBenefit, InternalAdoptionItem,
)
# Flujo de demanda configurable (rev. 195, 22-11-2026, docs/FLUJO_DE_DEMANDA.md)
from app.models.demanda import (  # noqa: F401,E402
    DemandRequestType, DemandFlow, DemandRequest, DemandStepState, DemandTransition,
    DemandFieldVersion, DemandDocument, DemandComment,
)
