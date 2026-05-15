/**
 * api.ts — Constantes de API y configuración del cliente
 *
 * NUNCA hardcodees URLs de API en componentes.
 * Usa siempre estas constantes o el cliente axios en services/api.js
 */

// TODO type: import.meta.env typings come from Vite — narrow once we add vite-env.d.ts
const VITE_API_URL = (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env?.VITE_API_URL

// Base URL de la API — configurable via variable de entorno Vite
// Recomendado: VITE_API_URL=https://api.miapp.com/api/v1
export const API_BASE: string = VITE_API_URL || '/api/v1'

// TODO type: business_config.json/constants.json have no schema — values inferred as `any`
import constants from './constants.json'
import businessConfig from './business_config.json'

// Configuración de negocio y catálogos
export const TIMEOUT: unknown = businessConfig.TIMEOUT
export const PAGINATION: unknown = businessConfig.PAGINATION
export const REFETCH: unknown = businessConfig.REFETCH
export const LIMITS: unknown = businessConfig.LIMITS

// Catálogos de negocio
export const ROLES: unknown = constants.ROLES
export const PROJECT_TYPES: unknown = constants.PROJECT_TYPES
export const BILLING_TYPES: unknown = constants.BILLING_TYPES
export const TASK_PRIORITIES: unknown = constants.TASK_PRIORITIES
export const TASK_STATUSES: unknown = constants.TASK_STATUSES
export const TICKET_TYPES: unknown = constants.TICKET_TYPES
export const SLA_LEVELS: unknown = constants.SLA_LEVELS

// Integraciones y automatizaciones
export const INTEGRATION_CATALOG: unknown = businessConfig.INTEGRATION_CATALOG
export const AUTOMATION_TRIGGERS: unknown = businessConfig.AUTOMATION_TRIGGERS
export const AUTOMATION_ACTIONS: unknown = businessConfig.AUTOMATION_ACTIONS
export const AUTOMATION_OPERATORS: unknown = businessConfig.AUTOMATION_OPERATORS
export const AUTOMATION_ACTION_PARAMS: unknown = businessConfig.AUTOMATION_ACTION_PARAMS

// Proveedores AI y docs
export const PROVIDER_META: unknown = businessConfig.PROVIDER_META
export const PROVIDER_DOCS: unknown = constants.PROVIDER_DOCS

// Roles y colores
export const ROLE_LABELS: Record<string, string> = businessConfig.ROLE_LABELS as Record<string, string>
export const ROLE_COLORS: Record<string, string> = businessConfig.ROLE_COLORS as Record<string, string>

// Guías de email providers
export const EMAIL_PROVIDER_GUIDES: unknown = businessConfig.EMAIL_PROVIDER_GUIDES
