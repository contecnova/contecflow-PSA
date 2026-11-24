/**
 * services/api/auth.ts — Audit #C10 (gradual split of services/api.ts).
 *
 * Typed surface for /auth endpoints. Replaces the loose definition in _core.ts;
 * the barrel `index.ts` re-exports this AFTER `_core` so the typed version wins.
 */
import type { AxiosResponse } from 'axios'
import api from './_core'
import type { CreationOptionsJSON, RequestOptionsJSON } from '../../lib/webauthn'
import type { UserPublic } from './users'
import type { PoliticaDeContrasena } from './seguridadDeCuentas'

// ── Request / response payloads ──────────────────────────────────────────────

/** Prueba de identidad para cambiar el segundo factor (ReautenticacionIn del backend). */
export interface Reautenticacion {
  password?: string
  code?: string
}

export interface LoginCredentials {
  username: string
  password: string
  mfa_code?: string
  /** Código de la empresa (modo de entrada `org_field`). */
  organization?: string
}

/** Una empresa entre las que se puede entrar. */
export interface OrganizacionDeEntrada {
  id: string
  name: string
  slug: string
  logo_url?: string | null
  primary_color?: string | null
}

/** Cómo se entra en este despliegue (`TENANT_ENTRY_MODE`). */
export interface ConfiguracionDeEntrada {
  mode: 'email_selector' | 'subdomain' | 'org_field'
  organization: OrganizacionDeEntrada | null
}

/** `TokenResponse` (app/schemas/auth.py). */
export interface LoginResponse {
  access_token?: string
  refresh_token?: string
  token_type?: 'bearer'
  user: UserPublic
  mfa_required?: boolean
  mfa_challenge_token?: string
  mfa_methods?: string[]
  organization_selection_required?: boolean
  organizations?: OrganizacionDeEntrada[]
  selection_token?: string
}

export interface MfaValidatePayload {
  mfa_challenge_token: string
  code: string
  /** Recordar este dispositivo (si la empresa lo permite: MFA_REMEMBER_DEVICE_DAYS). */
  remember_device?: boolean
}

export interface PasskeyStartPayload {
  mfa_challenge_token: string
}

export interface PasskeyFinishPayload {
  mfa_challenge_token: string
  webauthn_challenge_token: string
  credential: Record<string, unknown>
}

export interface SsoProvider {
  id: string
  provider: string
  name: string
  icon?: string
}

export interface MeResponse {
  id: string
  email: string
  full_name: string
  role: string
  /** Capacidades efectivas (matriz de permisos, 19-11-2026). El superadmin las tiene todas. */
  capacidades?: string[]
  blocked_routes?: string[]
  organization_id: string | null
  language: string | null
  hourly_rate?: number | null
  picture_url?: string | null
}

export interface ForgotPasswordPayload {
  email_or_username: string
}

export interface ResetPasswordPayload {
  token: string
  new_password: string
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

// ── Typed API surface ────────────────────────────────────────────────────────

/** Rol base real con sus etiquetas (`GET /auth/roles`, 19-11-2026). */
export interface RolReal {
  id: string
  etiquetas: { es: string; en: string; zh: string }
  interno: boolean
}

export const authApi = {
  /** Roles base que existen, para los selectores (sustituye a las listas escritas a mano). */
  roles: (): Promise<AxiosResponse<{ items: RolReal[] }>> => api.get('/auth/roles'),

  login: (credentials: LoginCredentials): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/login', credentials),

  validateMfa: (payload: MfaValidatePayload): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/mfa/validate', payload),

  startPasskeyAuth: (payload: PasskeyStartPayload): Promise<AxiosResponse<{ options: RequestOptionsJSON; webauthn_challenge_token: string }>> =>
    api.post('/auth/mfa/webauthn/authenticate/start', payload),

  finishPasskeyAuth: (payload: PasskeyFinishPayload): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/mfa/webauthn/authenticate/finish', payload),

  // Segunda auditoría 2026-11 (#11): en modo email_selector el backend solo
  // devuelve los proveedores del dominio del correo (ninguno sin él).
  listSsoProviders: (email?: string): Promise<AxiosResponse<SsoProvider[]>> =>
    api.get('/auth/sso/providers', email ? { params: { email } } : undefined),

  authorizeSso: (providerId: string, redirectUri: string): Promise<AxiosResponse<{ authorization_url?: string }>> =>
    api.get(`/auth/sso/${providerId}/authorize`, { params: { redirect_uri: redirectUri } }),

  // Auditoría 2026-11: la vuelta del proveedor no se procesaba en ningún sitio.
  ssoCallback: (providerId: string, payload: { code: string; state: string; redirect_uri: string }): Promise<AxiosResponse<LoginResponse>> =>
    api.post(`/auth/sso/${providerId}/callback`, payload),

  // SAML 2.0 (23-11-2026): URL del IdP con la AuthnRequest; el IdP vuelve al ACS
  // del backend, que redirige a /login?saml_ticket=… y aquí se canjea el ticket.
  authorizeSaml: (providerId: string): Promise<AxiosResponse<{ authorization_url?: string }>> =>
    api.get(`/auth/saml/${providerId}/login`),
  samlCanjear: (ticket: string): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/saml/canjear', { ticket }),
  samlLogout: (providerId: string): Promise<AxiosResponse<{ logout_url: string | null }>> =>
    api.post(`/auth/saml/${providerId}/logout`),
  // URLs del SP (metadata, ACS y SLO) para darlas de alta en el IdP (org.administrar).
  samlUrlsDelSp: (): Promise<AxiosResponse<{ metadata_url: string; acs_url: string; slo_url: string }>> =>
    api.get('/auth/saml/health'),

  // Gestión de passkeys del propio usuario (Perfil → Seguridad).
  // Auditoria 2026-11 (#21, backend): una passkey nueva es un segundo factor
  // nuevo; el servidor exige la contrasena actual o un codigo TOTP
  // (ReautenticacionIn). Sin ellos responde 401.
  passkeyRegisterStart: (reauth: Reautenticacion): Promise<AxiosResponse<{ options: CreationOptionsJSON; webauthn_challenge_token: string }>> =>
    api.post('/auth/mfa/webauthn/register/start', reauth),
  passkeyRegisterFinish: (payload: { webauthn_challenge_token: string; credential: Record<string, unknown>; name?: string }): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/mfa/webauthn/register/finish', payload),
  passkeyList: (): Promise<AxiosResponse<Array<{ id: string; name: string | null; created_at: string; last_used_at: string | null }>>> =>
    api.get('/auth/mfa/webauthn/credentials'),
  passkeyRename: (id: string, name: string): Promise<AxiosResponse<unknown>> =>
    api.patch(`/auth/mfa/webauthn/credentials/${id}`, { name }),
  passkeyDelete: (id: string): Promise<AxiosResponse<unknown>> =>
    api.delete(`/auth/mfa/webauthn/credentials/${id}`),

  // Acceso solo con passkey (credencial descubrible), sin usuario ni contraseña.
  passkeyLoginStart: (): Promise<AxiosResponse<{ options: RequestOptionsJSON; webauthn_challenge_token: string }>> =>
    api.post('/auth/passkey/login/start'),

  passkeyLoginFinish: (payload: { webauthn_challenge_token: string; credential: Record<string, unknown> }): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/passkey/login/finish', payload),

  // Revisión multitenant 2026-11: en qué empresa se entra y cambio de empresa.
  entryConfig: (): Promise<AxiosResponse<ConfiguracionDeEntrada>> =>
    api.get('/auth/entry-config'),
  selectOrganization: (payload: { selection_token: string; organization_id: string }): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/select-organization', payload),
  myOrganizations: (): Promise<AxiosResponse<{ current: string | null; items: OrganizacionDeEntrada[] }>> =>
    api.get('/auth/organizations'),
  switchOrganization: (organization_id: string): Promise<AxiosResponse<LoginResponse>> =>
    api.post('/auth/switch-organization', { organization_id }),

  forgotPassword: (payload: ForgotPasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/password/forgot', payload),

  resetPassword: (payload: ResetPasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/password/reset', payload),
  // 23-11-2026: reglas de la empresa del enlace (no consume el token).
  resetPasswordPolicy: (token: string): Promise<AxiosResponse<PoliticaDeContrasena>> =>
    api.post('/auth/password/reset/policy', { token }),

  changePassword: (data: ChangePasswordPayload): Promise<AxiosResponse<{ ok: boolean }>> =>
    api.post('/auth/change-password', data),
} as const
