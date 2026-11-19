/**
 * api.ts — Constantes de negocio y catálogos.
 *
 * NUNCA hardcodees URLs de API en componentes: usa el cliente (`services/api`)
 * o, si no puede pasar por él, `apiUrl`/`apiWsUrl` de `services/api/urls`.
 */

// TODO type: business_config.json/constants.json have no schema — values inferred as `any`
import constants from './constants.json'
import businessConfig from './business_config.json'

// 19-11-2026: se borraron TIMEOUT, PAGINATION, REFETCH, LIMITS, AUTOMATION_*, PROJECT_TYPES,
// TASK_*, TICKET_TYPES, SLA_LEVELS y EMAIL_PROVIDER_GUIDES: 0 referencias (grep). Los catálogos
// de tipos/estados salen del backend (`hooks/useCatalogos`) o de `constants/catalogos.ts`.
// 19-11-2026 (matriz de permisos): fuera ROLES, ROLE_LABELS y ROLE_COLORS. Los roles reales
// salen de `GET /auth/roles` (`hooks/useRolesReales`); las etiquetas, de `rol_usuario` (i18n).

// Catálogos de negocio
export const BILLING_TYPES: unknown = constants.BILLING_TYPES

// Integraciones y automatizaciones
export const INTEGRATION_CATALOG: unknown = businessConfig.INTEGRATION_CATALOG

// Proveedores AI y docs
export const PROVIDER_META: unknown = businessConfig.PROVIDER_META
export const PROVIDER_DOCS: unknown = constants.PROVIDER_DOCS

