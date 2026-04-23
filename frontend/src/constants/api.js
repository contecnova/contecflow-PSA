/**
 * api.js — Constantes de API y configuración del cliente
 *
 * NUNCA hardcodees URLs de API en componentes.
 * Usa siempre estas constantes o el cliente axios en services/api.js
 */

// Base URL de la API — configurable via variable de entorno Vite
// Recomendado: VITE_API_URL=https://api.miapp.com/api/v1
export const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

import constants from './constants.json'
import businessConfig from './business_config.json'

// Configuración de negocio y catálogos
export const TIMEOUT = businessConfig.TIMEOUT;
export const PAGINATION = businessConfig.PAGINATION;
export const REFETCH = businessConfig.REFETCH;
export const LIMITS = businessConfig.LIMITS;

// Catálogos de negocio
export const ROLES = constants.ROLES;
export const PROJECT_TYPES = constants.PROJECT_TYPES;
export const BILLING_TYPES = constants.BILLING_TYPES;
export const TASK_PRIORITIES = constants.TASK_PRIORITIES;
export const TASK_STATUSES = constants.TASK_STATUSES;
export const TICKET_TYPES = constants.TICKET_TYPES;
export const SLA_LEVELS = constants.SLA_LEVELS;

// Integraciones y automatizaciones
export const INTEGRATION_CATALOG = businessConfig.INTEGRATION_CATALOG;
export const AUTOMATION_TRIGGERS = businessConfig.AUTOMATION_TRIGGERS;
export const AUTOMATION_ACTIONS = businessConfig.AUTOMATION_ACTIONS;
export const AUTOMATION_OPERATORS = businessConfig.AUTOMATION_OPERATORS;
export const AUTOMATION_ACTION_PARAMS = businessConfig.AUTOMATION_ACTION_PARAMS;

// Proveedores AI y docs
export const PROVIDER_META = businessConfig.PROVIDER_META;
export const PROVIDER_DOCS = constants.PROVIDER_DOCS;

// Roles y colores
export const ROLE_LABELS = businessConfig.ROLE_LABELS;
export const ROLE_COLORS = businessConfig.ROLE_COLORS;

// Guías de email providers
export const EMAIL_PROVIDER_GUIDES = businessConfig.EMAIL_PROVIDER_GUIDES;
