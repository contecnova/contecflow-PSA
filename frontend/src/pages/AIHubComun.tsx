// Constantes y tipos compartidos por el centro de IA. 23-11-2026: troceado de AIHubPage sin cambio de comportamiento.
import { PROVIDER_META, PROVIDER_DOCS } from '../constants/api'
import { type CSSProperties } from 'react'

export const PMETA = PROVIDER_META as Record<string, { name: string; icon: string; color: string }>

export const PDOCS = PROVIDER_DOCS as Record<string, string>

export const STATUS_KEYS = ['active', 'inactive', 'error'] as const

/** Color de marca del proveedor como variable CSS (--aih-color); lo consumen las clases aih-*. */
export const colorVar = (color?: string | null): CSSProperties | undefined =>
  color ? ({ '--aih-color': color } as CSSProperties) : undefined

export interface ProviderForm {
  name: string
  provider: string
  api_key: string
  api_base_url: string
  default_model: string
  max_tokens: number
  temperature: number
  is_default: boolean
  priority: number
}

export interface AiPolicy { id: string; name: string; is_active?: boolean; scope?: string; action?: string; applies_to_roles?: string[] }

export interface AiAuditEntry {
  id: string
  evaluated_at?: string | null
  module?: string | null
  scope?: string
  was_blocked?: boolean
  action_taken?: string | null
  pii_types_found?: string[]
}
