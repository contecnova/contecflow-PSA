/**
 * services/api/seguridadDeCuentas.ts — políticas de cuenta (23-11-2026,
 * docs/seguridad/politicas_de_cuenta.md): política de la empresa, estado de los
 * usuarios, sesiones, aprobaciones con segundo administrador, recertificación
 * de accesos y mis dispositivos de confianza. Todo en `/security`.
 */
import api from './_core'
import type { User } from '../../context/AuthContext'

export type ValorDePolitica = string | number | boolean
export type Politica = Record<string, ValorDePolitica>

export interface DescripcionDePolitica {
  values: Politica
  recommended: Record<string, { value: ValorDePolitica; source: string }>
  ranges: Record<string, [number, number]>
  sensitive_capabilities: string[]
  mfa_methods: string[]
  pending_requests: number
  platform: { superadmin_bypass_enabled: boolean; geoip_enabled: boolean; environment: string }
}

export interface ResultadoDeCambio { applied: boolean; changed: string[]; pending_request_id?: string }

export interface EstadoDeUsuario {
  id: string; full_name: string; email: string; role: string; is_active: boolean; sso: boolean
  last_login: string | null; password_changed_at: string | null; password_expired: boolean
  password_must_change: boolean; password_temporary: boolean; locked_seconds: number
  mfa_totp: boolean; mfa_passkey: boolean; mfa_required: boolean; mfa_required_by: string | null
  mfa_enrollment_required: boolean; mfa_grace_until: string | null; active_sessions: number
}

export interface SesionDeEmpresa {
  id: string; user_id: string; user: string; email: string; ip_address: string | null
  country_code: string | null; device_name: string | null; auth_method: string | null
  risk_level: string | null; created_at: string; last_seen_at: string; expires_at: string
}

export interface SolicitudDeSeguridad {
  id: string; kind: 'policy' | 'mfa_reset'; status: 'pending' | 'applied' | 'rejected' | 'expired'
  payload: Record<string, unknown>; reason: string | null; target_user: string | null
  requested_by: string | null; requested_by_name: string | null; requested_at: string
  decided_by_name: string | null; decided_at: string | null; decision_comment: string | null
}

export interface Campana {
  id: string; name: string; status: 'open' | 'closed'; due_at: string | null; created_at: string
  closed_at: string | null; items: number; pending: number
}

export type DecisionDeAcceso = 'pending' | 'keep' | 'revoke' | 'modify'

export interface ElementoDeRevision {
  id: string; user_id: string; user: string | null; email: string | null; reviewer_id: string | null
  reviewer: string | null; decision: DecisionDeAcceso; comment: string | null; decided_by: string | null
  decided_at: string | null; applied_at: string | null
  snapshot: { role?: string; mfa?: boolean; last_login?: string | null; sensitive_capabilities?: string[]; department?: string | null }
}

export interface DispositivoDeConfianza {
  id: string; device_name: string | null; ip_address: string | null; created_at: string
  last_used_at: string | null; expires_at: string
}

export interface PoliticaDeContrasena {
  MIN_PASSWORD_LENGTH: number; PASSWORD_MAX_LENGTH: number; PASSWORD_REQUIRE_UPPERCASE: boolean
  PASSWORD_REQUIRE_LOWERCASE: boolean; PASSWORD_REQUIRE_DIGIT: boolean; PASSWORD_REQUIRE_SPECIAL: boolean
  PASSWORD_BLOCK_COMMON: boolean; PASSWORD_BLOCK_PERSONAL: boolean; PASSWORD_HISTORY_COUNT: number
  PASSWORD_EXPIRY_DAYS: number
}

export const seguridadApi = {
  politica: () => api.get<DescripcionDePolitica>('/security/policy').then(r => r.data),
  guardarPolitica: (changes: Politica, reason?: string) =>
    api.put<ResultadoDeCambio>('/security/policy', { changes, reason }).then(r => r.data),
  usuarios: () => api.get<{ items: EstadoDeUsuario[] }>('/security/users').then(r => r.data.items),
  desbloquear: (id: string) => api.post(`/security/users/${id}/unlock`),
  forzarCambio: (id: string) => api.post(`/security/users/${id}/force-password-change`),
  /** 23-11-2026: cambio obligatorio + cierre de sesiones + enlace de un solo uso, con motivo. */
  forzarRestablecimiento: (id: string, reason: string, send_link = true) =>
    api.post<{ ok: boolean; link_sent: boolean; sessions_revoked: number }>(
      `/security/users/${id}/force-password-reset`, { reason, send_link }).then(r => r.data),
  forzarCambioATodos: () => api.post<{ users: number }>('/security/force-password-change-all').then(r => r.data),
  contrasenaTemporal: (id: string) =>
    api.post<{ password: string | null; expires_at: string }>(`/security/users/${id}/temporary-password`, {}).then(r => r.data),
  restablecerMfa: (id: string, reason?: string) =>
    api.post<{ applied: boolean; pending_request_id?: string }>(`/security/users/${id}/reset-mfa`, { reason }).then(r => r.data),
  cerrarSesionesDe: (id: string) => api.post(`/security/users/${id}/revoke-sessions`),
  sesiones: () => api.get<{ items: SesionDeEmpresa[] }>('/security/sessions').then(r => r.data.items),
  cerrarSesion: (id: string) => api.delete(`/security/sessions/${id}`),
  solicitudes: () => api.get<{ items: SolicitudDeSeguridad[] }>('/security/change-requests').then(r => r.data.items),
  aprobar: (id: string, comment?: string) => api.post(`/security/change-requests/${id}/approve`, { comment }),
  rechazar: (id: string, comment?: string) => api.post(`/security/change-requests/${id}/reject`, { comment }),
  campanas: () => api.get<{ items: Campana[] }>('/security/access-reviews').then(r => r.data.items),
  abrirCampana: (name: string, due_at?: string) => api.post('/security/access-reviews', { name, due_at: due_at || null }),
  elementos: (id: string) =>
    api.get<{ items: ElementoDeRevision[] }>(`/security/access-reviews/${id}/items`).then(r => r.data.items),
  misRevisiones: () =>
    api.get<{ items: { campaign: { id: string; name: string; due_at: string | null }; items: ElementoDeRevision[] }[] }>(
      '/security/access-reviews/mine').then(r => r.data.items),
  decidir: (campana: string, elemento: string, decision: DecisionDeAcceso, comment: string) =>
    api.post(`/security/access-reviews/${campana}/items/${elemento}/decide`, { decision, comment }),
  cerrarCampana: (id: string, apply_revocations: boolean) =>
    api.post<{ pending_at_close: number; deactivated: string[] }>(`/security/access-reviews/${id}/close`, { apply_revocations }).then(r => r.data),
  exportarCampana: (id: string, format: 'csv' | 'json') =>
    api.get<Blob>(`/security/access-reviews/${id}/export`, { params: { format }, responseType: 'blob' }).then(r => r.data),
  misDispositivos: () => api.get<{ items: DispositivoDeConfianza[] }>('/security/me/devices').then(r => r.data.items),
  olvidarDispositivo: (id: string) => api.delete(`/security/me/devices/${id}`),
  politicaDeContrasena: () => api.get<PoliticaDeContrasena>('/auth/password-policy').then(r => r.data),
  /** Cambio obligatorio de contraseña (pantalla de `EstadoDeCuenta`). */
  cambiarContrasena: (body: { current_password: string; new_password: string; mfa_code?: string }) =>
    api.post('/auth/change-password', body),
  /** El usuario de la sesión, para refrescar `account_security` tras cambiar contraseña o MFA. */
  yo: () => api.get<User>('/auth/me').then(r => r.data),
}
