/**
 * Shared context, auth, API client, and styles for the client portal.
 * Import from here in all portal-client sub-pages.
 */
import React, { createContext, useContext, useState, useEffect, useId } from 'react'
import type { CSSProperties } from 'react'
import axios, { type AxiosResponse } from 'axios'
import { PORTAL_TRANSLATIONS as T, PORTAL_LANGUAGES as LANGUAGES } from '../../i18n/portalTranslations'
import { STATUS_CFG } from '../../constants/sharedStatus'
import { useIdleTimeout } from '../../hooks/useIdleTimeout'
import { useAppLang } from '../../i18n/AppLangContext'

type ApiListBody = {
  items: unknown[]
  meta: Record<string, unknown>
}

function isApiListBody(body: unknown): body is ApiListBody {
  return Boolean(
    body &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    Array.isArray((body as ApiListBody).items) &&
    (body as ApiListBody).meta &&
    typeof (body as ApiListBody).meta === 'object' &&
    Object.keys(body as Record<string, unknown>).length === 2,
  )
}

// ── API client ────────────────────────────────────────────────────────────────
export const CLIENT_API = axios.create({ baseURL: '/api/v1', withCredentials: true, timeout: 30000 })

// APIListResponse compatibility for portal client routes.
CLIENT_API.interceptors.response.use((res: AxiosResponse<unknown>) => {
  const body = res?.data
  if (isApiListBody(body)) {
    return {
      ...res,
      data: body.items,
      meta: body.meta,
    } as AxiosResponse<unknown[]> & { meta: Record<string, unknown> }
  }
  return res
})


// ─────────────────────────────────────────────────────────────────────────────
// La sesion del portal de cliente
//
// Auditoria 2026-09 (modo estricto): `createContext(null)` sin argumento de tipo
// fija el contexto a `null` **para siempre**, asi que `useClientAuth()` devolvia
// `null` y cualquier `const { login } = useClientAuth()` era un error que nadie
// veia. Declarar el valor del contexto es lo que arregla los 15 errores de este
// fichero de raiz.
//
// El contexto puede ser `null` de verdad —fuera del proveedor no hay sesion— y
// eso queda en el tipo a proposito: `useClientAuth()` devuelve
// `SesionDeCliente | null` y quien lo use tiene que decidir que hace sin sesion.
// ─────────────────────────────────────────────────────────────────────────────

/** El cliente autenticado, con lo que el portal puede o no puede hacer. */
export interface ClienteDelPortal {
  id?: string | number
  email?: string
  name?: string
  full_name?: string
  language?: string
  organization_name?: string
  company?: string
  project_id?: string | number | null
  project_ids?: Array<string | number>
  projects?: unknown[]
  can_approve_deliverables?: boolean
  can_request_changes?: boolean
  can_view_budget?: boolean
  can_view_team?: boolean
}

/** Lo que el proveedor de sesion ofrece a sus hijos. */
export interface SesionDeCliente {
  client: ClienteDelPortal | null
  login: (email: string, password: string) => Promise<unknown>
  logout: () => Promise<void>
  /** `false` mientras se comprueba la sesion contra el servidor: distinto de
   *  «no hay sesion», y por eso es un campo aparte y no un `client === null`. */
  isReady: boolean
}

// ── Language Context ──────────────────────────────────────────────────────────
export const LangContext = createContext('es')
export const PORTAL_CUSTOM_KEY = 'contecflow_portal_custom'

/** `T` con el tipo que el codigo ya usa: se indexa por codigo de idioma, que
 *  viene de la configuracion del usuario y no de la lista literal de hoy. El
 *  respaldo a espanol de mas abajo es justo el caso «no esta». */
const TRADUCCIONES = T as unknown as Record<string, Record<string, string> | undefined>

export function useLang() {
  const lang = useContext(LangContext)
  return (key: string): string => {
    try {
      const custom = JSON.parse(localStorage.getItem(PORTAL_CUSTOM_KEY) || '{}')
      if (custom[lang]?.[key]) return custom[lang][key]
      if (custom['es']?.[key] && !TRADUCCIONES[lang]?.[key]) return custom['es'][key]
    } catch { /* noop */ }
    return TRADUCCIONES[lang]?.[key] || TRADUCCIONES['es']?.[key] || key
  }
}

// ── Client Auth Context ───────────────────────────────────────────────────────
export const ClientAuthContext = createContext<SesionDeCliente | null>(null)
export function useClientAuth() { return useContext(ClientAuthContext) }

function _pickClientUiFields(client: ClienteDelPortal | null) {
  if (!client) return null
  const {
    id,
    email,
    name,
    full_name,
    language,
    organization_name,
    company,
    project_id,
    project_ids,
    projects,
    can_approve_deliverables,
    can_request_changes,
    can_view_budget,
    can_view_team,
  } = client
  return {
    id,
    email,
    name,
    full_name: full_name || name,
    language,
    organization_name,
    company,
    project_id,
    project_ids: Array.isArray(project_ids) ? project_ids : (project_id ? [project_id] : []),
    projects: Array.isArray(projects) ? projects : [],
    can_approve_deliverables: Boolean(can_approve_deliverables),
    can_request_changes: Boolean(can_request_changes),
    can_view_budget: Boolean(can_view_budget),
    can_view_team: Boolean(can_view_team),
  }
}

export function ClientAuthProvider({ children }: { children?: React.ReactNode }) {
  const { t: traducir } = useAppLang()
  const [client, setClient] = useState<ClienteDelPortal | null>(() => {
    try { return JSON.parse(localStorage.getItem('client_user') || 'null') } catch { return null }
  })
  const [isReady, setIsReady] = useState(false)
  const [idleEnabled, setIdleEnabled] = useState(false)
  const [idleMinutes, setIdleMinutes] = useState(30)
  useEffect(() => {
    let mounted = true
    // Only probe /portal/auth/me when localStorage has a hint that a portal
    // session existed in this browser. First-time visitors of /portal go
    // straight to the login screen without a noisy 401 in the console.
    const hasPortalHint = !!localStorage.getItem('client_user')
    if (!hasPortalHint) {
      setIsReady(true)
      return () => { mounted = false }
    }
    CLIENT_API.get('/portal/auth/me')
      .then((res) => {
        if (!mounted) return
        const me = _pickClientUiFields(res?.data)
        setClient(me)
        if (me) localStorage.setItem('client_user', JSON.stringify(me))
        else localStorage.removeItem('client_user')
        setIsReady(true)
      })
      .catch(() => {
        if (!mounted) return
        setClient(null)
        localStorage.removeItem('client_user')
        setIsReady(true)
      })
    return () => { mounted = false }
  }, [])
  const login = async (email: string, password: string) => {
    const res = await CLIENT_API.post('/portal/auth/login', { email, password })
    const clientData = _pickClientUiFields(res.data.client)
    localStorage.setItem('client_user', JSON.stringify(clientData))
    if (res.data.client?.language) {
      localStorage.setItem('portal_lang', res.data.client.language)
    }
    setClient(clientData)
    return res.data.client
  }
  const logout = async () => {
    try { await CLIENT_API.post('/portal/auth/logout') } catch { /* noop */ }
    localStorage.removeItem('client_user')
    setClient(null)
  }

  useEffect(() => {
    if (!client) return
    CLIENT_API.get('/portal/auth/session-config')
      .then((res) => {
        const cfg = res?.data || {}
        setIdleEnabled(Boolean(cfg.idle_timeout_enabled))
        setIdleMinutes(Math.max(1, parseInt(cfg.idle_timeout_minutes, 10) || 30))
      })
      .catch(() => {
        // Keep safe defaults when config is unavailable.
        setIdleEnabled(false)
        setIdleMinutes(30)
      })
  }, [client])

  const { showWarning, secondsLeft, dismiss } = useIdleTimeout({
    enabled: !!client && idleEnabled,
    timeoutMinutes: idleMinutes,
    onTimeout: logout,
    warningSeconds: 60,
  })

  return (
    <ClientAuthContext.Provider value={{ client, login, logout, isReady }}>
      {children}
      {showWarning && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
            borderRadius: 16, padding: '28px 30px', maxWidth: 420, width: '90%',
            boxShadow: '0 8px 40px rgba(0,0,0,0.4)', textAlign: 'center',
          }}>
            <div style={{ fontSize: 36, marginBottom: 10 }}>⏱️</div>
            <h3 style={{ margin: '0 0 8px', color: 'var(--text-1)', fontSize: 'var(--text-lg)', fontWeight: 700 }}>
              {traducir('portalclientcontext.sesion_a_punto_de_expirar')}
            </h3>
            <p style={{ color: 'var(--text-2)', margin: '0 0 22px', fontSize: 'var(--text-sm)', lineHeight: 1.5 }}>
              {traducir('portalclientcontext.tu_sesion_del_portal_se_cerrara_por')}{' '}
              <strong style={{ color: secondsLeft <= 15 ? '#ff4757' : 'var(--accent)' }}>
                {secondsLeft}s
              </strong>.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button
                onClick={dismiss}
                style={{
                  background: 'var(--accent)', color: 'var(--surface-0)', border: 'none',
                  borderRadius: 8, padding: '10px 24px', fontWeight: 700,
                  cursor: 'pointer', fontSize: 'var(--text-sm)',
                }}
              >
                {traducir('portalclientcontext.continuar_sesion')}
              </button>
              <button
                onClick={logout}
                style={{
                  background: 'transparent', color: 'var(--text-3)',
                  border: '1px solid var(--surface-4)', borderRadius: 8,
                  padding: '10px 20px', cursor: 'pointer', fontSize: 'var(--text-sm)',
                }}
              >
                {traducir('portalclientcontext.cerrar_sesion')}
              </button>
            </div>
          </div>
        </div>
      )}
    </ClientAuthContext.Provider>
  )
}

// ── Shared styles ─────────────────────────────────────────────────────────────
export const S = {
  page: { minHeight: '100vh', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: "'Inter', system-ui, sans-serif" },
  card: { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: 'var(--space-4) var(--space-5)' },
  badge: (color: string) => ({ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: color + '20', color, border: `1px solid ${color}40`, textTransform: 'uppercase' }),
  btn: { background: 'var(--accent)', border: 'none', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--portal-bg)', fontSize: "var(--text-md)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' },
  btnSec: { background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit' },
  input: { background: 'var(--surface-4)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: "var(--text-md)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' },
  label: { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 },
}

// ── Shared components ─────────────────────────────────────────────────────────
export function Badge({ status }: { status?: string }) {
  const cfg = (status && STATUS_CFG[status]) || { label: status, color: 'var(--text-2)' }
  return <span style={S.badge(cfg.color)}>{cfg.label}</span>
}

interface LangSelectorProps {
  onChange: (code: string) => void
  current?: string
  /** Variante para fondos oscuros. */
  dark?: boolean
}

export function LangSelector({ onChange, current, dark = false }: LangSelectorProps) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {LANGUAGES.map(l => (
        <button key={l.code} onClick={() => onChange(l.code)}
          title={l.label}
          style={{
            background: current === l.code ? (dark ? 'var(--surface-4)' : 'var(--accent-glow)') : 'transparent',
            border: `1px solid ${current === l.code ? 'var(--accent-glow)' : (dark ? 'var(--surface-4)' : 'rgba(255,255,255,0.12)')}`,
            borderRadius: 8, padding: '5px 9px', cursor: 'pointer',
            fontSize: "var(--text-lg)", lineHeight: 1, fontFamily: 'inherit',
            transition: 'all 0.15s',
          }}>
          {l.flag}
        </button>
      ))}
    </div>
  )
}

export function LoginScreen({ _changeLang, _currentLang }: { _changeLang?: (code: string) => void; _currentLang?: string }) {
  const { t: traducir } = useAppLang()
  // Sin proveedor no hay sesion. Pasa solo si alguien monta esta pantalla
  // fuera del portal, y con el `?.` falla en el sitio y no cinco lineas mas
  // abajo con un «login is not a function».
  const login = useClientAuth()?.login
  const t = useLang()
  const idPrefix = useId()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setError(''); setLoading(true)
    try { await login?.(email, password) }
    catch { setError(t('login_error')) }
    finally { setLoading(false) }
  }

  const fieldStyle = {
    width: '100%', boxSizing: 'border-box',
    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-md, 8px)', padding: '11px 13px',
    color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none',
    fontFamily: 'inherit', transition: 'border-color 0.15s, box-shadow 0.15s',
  } satisfies CSSProperties
  const labelStyle = {
    fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)',
    textTransform: 'uppercase', letterSpacing: '0.07em',
    display: 'block', marginBottom: 6,
  } satisfies CSSProperties

  return (
    <div style={{
      minHeight: '100vh', display: 'flex',
      background: 'var(--surface-0)', color: 'var(--text-1)',
      fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      {/* Brand panel (oculto en pantallas pequeñas) */}
      <div className="portal-login-brand" style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: 'linear-gradient(135deg, var(--surface-1) 0%, var(--surface-2) 100%)',
        borderRight: '1px solid var(--surface-4)',
        padding: '48px 56px', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: 'linear-gradient(135deg, var(--accent), var(--purple))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 'var(--text-xl-em)', fontWeight: 800, color: '#fff',
          }}>◈</div>
          <div>
            <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 800 }}>Contecflow</div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Portal cliente</div>
          </div>
        </div>
        <div>
          <h1 style={{ fontSize: 'var(--text-3xl-em, 28px)', fontWeight: 800, margin: '0 0 14px', letterSpacing: '-0.02em', lineHeight: 1.15 }}>
            {t('login_title')}
          </h1>
          <p style={{ fontSize: 'var(--text-md)', color: 'var(--text-2)', margin: 0, maxWidth: 460, lineHeight: 1.6 }}>
            {t('login_subtitle')}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 28, maxWidth: 480 }}>
            {[
              { t: 'Roadmap y entregables', s: 'Visibilidad clara del avance del proyecto' },
              { t: 'Soporte y SLA', s: 'Tickets, KB y comunicados centralizados' },
              { t: 'UAT colaborativos', s: 'Valida entregas con feedback estructurado' },
              { t: 'Facturación', s: 'Aprueba facturas y revisa el histórico' },
            ].map((it, i) => (
              <div key={i} style={{
                background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                borderRadius: 10, padding: '12px 14px',
              }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700 }}>{it.t}</div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>{it.s}</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
          © {new Date().getFullYear()} Contecflow PSA — Portal cliente
        </div>
      </div>

      {/* Form panel */}
      <div style={{
        width: 460, maxWidth: '100%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '32px 36px',
      }}>
        <div style={{ width: '100%', maxWidth: 360 }}>
          <h2 style={{ fontSize: 'var(--text-xl-em)', fontWeight: 800, margin: '0 0 6px' }}>{traducir('portalclientcontext.acceder_al_portal')}</h2>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: '0 0 24px' }}>
            {traducir('portalclientcontext.usa_tu_correo_corporativo_para_acceder')}
          </p>
          <form onSubmit={e => { e.preventDefault(); handleLogin() }} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label htmlFor={`${idPrefix}-email`} style={labelStyle}>{t('login_email')}</label>
              <input id={`${idPrefix}-email`} type="email" autoComplete="email"
                value={email} onChange={e => setEmail(e.target.value)}
                style={fieldStyle} placeholder="tu@empresa.com" />
            </div>
            <div>
              <label htmlFor={`${idPrefix}-password`} style={labelStyle}>{t('login_password')}</label>
              <input id={`${idPrefix}-password`} type="password" autoComplete="current-password"
                value={password} onChange={e => setPassword(e.target.value)}
                style={fieldStyle} placeholder="••••••••" />
            </div>
            {error && (
              <div style={{
                fontSize: 'var(--text-sm)', color: 'var(--danger)',
                background: 'var(--danger-bg, rgba(239,68,68,0.12))',
                border: '1px solid var(--danger-border, rgba(239,68,68,0.3))',
                borderRadius: 8, padding: '10px 12px',
              }}>{error}</div>
            )}
            <button type="submit" disabled={loading || !email || !password} style={{
              width: '100%', padding: '12px',
              background: 'var(--accent)', color: '#fff',
              border: '1px solid var(--accent)',
              borderRadius: 'var(--radius-md, 8px)',
              fontSize: 'var(--text-md)', fontWeight: 700,
              cursor: (loading || !email || !password) ? 'not-allowed' : 'pointer',
              opacity: (loading || !email || !password) ? 0.6 : 1,
              fontFamily: 'inherit', marginTop: 6,
            }}>
              {loading ? t('login_loading') : t('login_btn')}
            </button>
          </form>
        </div>
      </div>

      <style>{`
        @media (max-width: 880px) {
          .portal-login-brand { display: none !important; }
        }
      `}</style>
    </div>
  )
}