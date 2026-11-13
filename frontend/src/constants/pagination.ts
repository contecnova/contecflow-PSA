/**
 * Tamaños de página y límites de listas centralizados.
 *
 * Ojo con los topes del backend: la mayoría de listados aceptan como máximo
 * 200 por página; /tasks y algunos otros aceptan 500. No subir estos valores
 * sin comprobar el endpoint.
 */

// ── Escalones genéricos ─────────────────────────────────────────────────
export const DEFAULT_PAGE_SIZE = 50
export const SMALL_PAGE_SIZE = 20
export const LARGE_PAGE_SIZE = 200
export const MAX_PAGE_SIZE = 500

/** Solo interesa el total (se pide 1 elemento). */
export const COUNT_ONLY_PAGE_SIZE = 1
/** Filas por página en el componente DataTable. */
export const DATA_TABLE_PAGE_SIZE = 15

// ── Listas completas / selectores ───────────────────────────────────────
/** Listas para selectores (usuarios, clientes, contratos, proyectos, CIs). */
export const SELECTOR_LIST_SIZE = LARGE_PAGE_SIZE
/** Lista completa en endpoints que aceptan 500 (/tasks, /users, CMDB, /bookings). */
export const FULL_LIST_SIZE = MAX_PAGE_SIZE
/** Tareas para planificación (Gantt, planificación inteligente). */
export const SCHEDULE_TASKS_LIST_SIZE = 300
/** Clientes para el selector de NPS. */
export const NPS_CLIENTS_LIST_SIZE = 300
/** Listas secundarias de cuadros de mando (OKRs, formaciones, ausencias). */
export const DASHBOARD_LIST_SIZE = 100
/** Documentos en la vista de documentos. */
export const DOCUMENTS_LIST_LIMIT = 200

// ── Calendario ──────────────────────────────────────────────────────────
export const CALENDAR_TASKS_LIMIT = 100
export const CALENDAR_SPRINTS_LIMIT = 20
export const CALENDAR_ABSENCES_LIMIT = 200

// ── Auditoría / registros ───────────────────────────────────────────────
export const AUDIT_LOG_PAGE_SIZE = DEFAULT_PAGE_SIZE
export const AUDIT_LOG_SMALL_PAGE_SIZE = SMALL_PAGE_SIZE
export const PREDICTION_LOGS_LIMIT = 30
export const ESCALATION_LOGS_LIMIT = 20
export const MONITORING_ALERTS_LIMIT = 30
export const INBOUND_MESSAGES_LIMIT = 30
export const GOVERNANCE_LOGS_LIMIT = 100

// ── Chat / colaboración ─────────────────────────────────────────────────
export const CHAT_MESSAGES_PAGE_SIZE = 50
export const CHAT_THREAD_MESSAGES_LIMIT = 200
export const CHAT_SEARCH_LIMIT = 30
export const CHAT_DECISIONS_LIMIT = 100
export const CHAT_AUDIT_LIMIT = 200
export const MENTION_SUGGESTIONS_LIMIT = 12
export const MENTION_SUGGESTIONS_MEMBERS_LIMIT = 16
export const MENTION_SUGGESTIONS_COMPACT_LIMIT = 8

// ── Búsqueda ────────────────────────────────────────────────────────────
/** Resultados por tipo de entidad en la búsqueda global. */
export const SEARCH_RESULTS_PER_ENTITY = 8
/** Candidatos al vincular un ticket por número/búsqueda. */
export const TICKET_LINK_SEARCH_LIMIT = 5

// ── Consultas / informes / lotes ────────────────────────────────────────
export const DATA_PREVIEW_ROWS = 20
export const VISUAL_QUERY_ROW_LIMIT = 100
export const REPORT_BUILDER_ROW_LIMIT = 500
export const INVOICES_BATCH_SIZE = 500
export const ACCOUNTING_PUSH_BATCH_SIZE = 100
/** Opciones de contexto (clientes/servicios/CIs) en formularios dinámicos. */
export const DYNAMIC_FORM_OPTIONS_LIMIT = 60
