/**
 * api.js — Constantes de API y configuración del cliente
 *
 * NUNCA hardcodees URLs de API en componentes.
 * Usa siempre estas constantes o el cliente axios en services/api.js
 */

// Base URL de la API — configurable via variable de entorno Vite
// Recomendado: VITE_API_URL=https://api.miapp.com/api/v1
export const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

// Timeouts (ms)
export const TIMEOUT = {
  default:  15_000,   // 15 segundos
  upload:   60_000,   // 1 minuto para uploads
  ai:      120_000,   // 2 minutos para llamadas IA
}

// Paginación por defecto
export const PAGINATION = {
  defaultPageSize: 25,
  ganttPageSize:   300,
  maxPageSize:     500,
  selectPageSize:  100,  // para dropdowns y selects
}

// Intervalos de refresco (ms)
export const REFETCH = {
  alerts:       60_000,   // alertas: cada 60s
  notifications: 30_000,  // notificaciones: cada 30s
  dashboard:    120_000,  // dashboard: cada 2 min
  static:       300_000,  // datos estáticos: cada 5 min
}

// Límites de validación
export const LIMITS = {
  maxHoursPerDay:   24,
  maxTitleLength:   255,
  maxDescLength:    5000,
  maxTagsLength:    500,
  minPasswordLength: 8,
}

// Roles de usuario
export const ROLES = {
  admin:     'admin',
  pm:        'pm',
  teamLead:  'team_lead',
  developer: 'developer',
  employee:  'employee',
  hr:        'hr',
  client:    'client',
}

// Tipos de proyecto
export const PROJECT_TYPES = [
  { value: 'consulting',   label: 'Consultoría'       },
  { value: 'development',  label: 'Desarrollo'        },
  { value: 'managed',      label: 'Servicios gestionados' },
  { value: 'internal',     label: 'Proyecto interno'  },
  { value: 'training',     label: 'Formación'         },
  { value: 'research',     label: 'Investigación'     },
]

// Tipos de facturación
export const BILLING_TYPES = [
  { value: 'time_material',      label: 'Tiempo y materiales'   },
  { value: 'fixed_price',        label: 'Precio fijo'           },
  { value: 'hourly_bag',         label: 'Bolsa de horas'        },
  { value: 'recurring_retainer', label: 'Retainer recurrente'   },
  { value: 'retainer',           label: 'Retainer mensual'      },
  { value: 'milestone',          label: 'Por hitos'             },
]

// Prioridades de tarea
export const TASK_PRIORITIES = [
  { value: 'low',      label: 'Baja'    },
  { value: 'medium',   label: 'Media'   },
  { value: 'high',     label: 'Alta'    },
  { value: 'critical', label: 'Crítica' },
]

// Estados de tarea
export const TASK_STATUSES = [
  { value: 'backlog',     label: 'Backlog'      },
  { value: 'todo',        label: 'Por hacer'    },
  { value: 'in_progress', label: 'En progreso'  },
  { value: 'review',      label: 'En revisión'  },
  { value: 'done',        label: 'Hecho'        },
  { value: 'blocked',     label: 'Bloqueado'    },
  { value: 'cancelled',   label: 'Cancelado'    },
]

// Tipos de ticket de Service Desk
export const TICKET_TYPES = [
  { value: 'incident',        label: 'Incidencia',        icon: '🔴' },
  { value: 'service_request', label: 'Solicitud',         icon: '🔵' },
  { value: 'change',          label: 'Cambio',            icon: '🟡' },
  { value: 'question',        label: 'Consulta',          icon: '⚪' },
  { value: 'problem',         label: 'Problema',          icon: '🟠' },
]

// Niveles de SLA
export const SLA_LEVELS = [
  { value: 'l1', label: 'L1 — Soporte básico'    },
  { value: 'l2', label: 'L2 — Soporte técnico'   },
  { value: 'l3', label: 'L3 — Desarrollo / Experto' },
]

// ── URLs de consolas de proveedores IA ────────────────────────────────────────
// Centralizado aquí para no hardcodear en componentes.
// El backend expone estos valores via settings.ANTHROPIC_DOCS_URL etc.
export const PROVIDER_DOCS = {
  anthropic: 'https://console.anthropic.com',
  openai:    'https://platform.openai.com',
  gemini:    'https://aistudio.google.com',
  deepseek:  'https://platform.deepseek.com',
  groq:      'https://console.groq.com',
  mistral:   'https://console.mistral.ai',
  ollama:    'https://ollama.com',
  azure:     'https://oai.azure.com',
}
