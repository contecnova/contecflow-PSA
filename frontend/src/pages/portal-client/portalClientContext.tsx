/**
 * Shared context, auth, API client, and styles for the client portal.
 * Import from here in all portal-client sub-pages.
 */
import { PRODUCT_FULL_NAME, PRODUCT_NAME } from '../../constants/brand'
import React, { type CSSProperties, createContext, useContext, useState, useEffect, useId } from 'react'
import { type AxiosResponse } from 'axios'
import { useQuery } from '@tanstack/react-query'
import { PORTAL_TRANSLATIONS as T, PORTAL_LANGUAGES as LANGUAGES } from '../../i18n/portalTranslations'
import { STATUS_CFG } from '../../constants/sharedStatus'
import { useIdleTimeout } from '../../hooks/useIdleTimeout'
import { crearClienteDeApi } from '../../services/api/clienteBase'
import StatusBadge from '../../components/ui/StatusBadge'
import { useDialogo } from '../../components/ui/useDialogo'
import { TextosDeInterfazProvider, type TraductorDeCodigos } from '../../components/ui/useTextoUi'
import { mensajeDeError } from '../../utils/mensajeDeError'
import { Button, Pulsable } from '../../components/ui'
import { Timer, Map as MapIcon, Headphones, FlaskConical, Receipt } from 'lucide-react'
import './portalClientContext.css'

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
// Instancia propia: el portal de clientes tiene su propia sesión y su propio
// manejo de 401 (no debe disparar el refresco de la sesión de empleado).
export const CLIENT_API = crearClienteDeApi({ withCredentials: true })  // base y límite comunes (19-11-2026)

// Desenvuelve los dos sobres del servidor, como el cliente de la aplicación
// (services/api/_core.ts). Auditoría 2026-11: solo desenvolvía las listas, y
// desde julio el login del portal responde `{data, meta}`; `res.data.client`
// salía vacío y el portal volvía a la pantalla de entrada sin decir nada.
// Nadie podía entrar.
CLIENT_API.interceptors.response.use((res: AxiosResponse<unknown>) => {
  const body = res?.data
  if (isApiListBody(body)) {
    return {
      ...res,
      data: body.items,
      meta: body.meta,
    } as AxiosResponse<unknown[]> & { meta: Record<string, unknown> }
  }
  // Sobre de objeto (APIResponse): exactamente {data, meta}, para no tocar un
  // payload que casualmente tenga una clave `data`.
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const claves = Object.keys(body)
    if (claves.length === 2 && 'data' in body && 'meta' in body) {
      const sobre = body as { data: unknown; meta: Record<string, unknown> }
      return { ...res, data: sobre.data, meta: sobre.meta } as AxiosResponse<unknown> & { meta: Record<string, unknown> }
    }
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
/** Revisión 2026-11: las traducciones que personaliza el administrador llegan
 *  con la marca del portal (`/portal/branding`). Antes se leían del
 *  localStorage, que solo existía en el navegador del administrador. */
export type TraduccionesDelPortal = Record<string, Record<string, string>>
export const PortalCustomContext = createContext<TraduccionesDelPortal>({})

/** `T` con el tipo que el codigo ya usa: se indexa por codigo de idioma, que
 *  viene de la configuracion del usuario y no de la lista literal de hoy. El
 *  respaldo a espanol de mas abajo es justo el caso «no esta». */
const TRADUCCIONES = T as unknown as Record<string, Record<string, string> | undefined>

/** Código del idioma de la pantalla del portal (traducción en tiempo real, 16-11-2026):
 *  se manda como `?lang=` a la KB para recibir la versión publicada en ese idioma. */
export function useIdiomaDelPortal(): string {
  return useContext(LangContext)
}

/** Rellena los `{{x}}` de un texto del portal (16-11-2026). */
export function rellenar(texto: string, vars: Record<string, string | number | null | undefined> = {}): string {
  return texto.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => String(vars[k] ?? ''))
}

/** Variables de un texto del portal: `t(<clave>, { n: 3 })` rellena `{{n}}`. */
export type VariablesDelPortal = Record<string, string | number | null | undefined>
/** El traductor del portal (8 idiomas). */
export type TraductorDelPortal = (key: string, vars?: VariablesDelPortal) => string

/** Texto de `key` en `lang` con las personalizaciones del administrador; sin hooks. */
export function textoDelPortal(lang: string, key: string, custom: TraduccionesDelPortal = {}): string {
  if (custom[lang]?.[key]) return custom[lang][key]
  if (custom['es']?.[key] && !TRADUCCIONES[lang]?.[key]) return custom['es'][key]
  return TRADUCCIONES[lang]?.[key] || TRADUCCIONES['es']?.[key] || key
}

/** Traductor del portal de clientes: lee los diccionarios `i18n/portal/*` (8
 *  idiomas). Todo texto visible del portal pasa por aquí, nunca por el
 *  traductor de operador (`useAppLang`/`useAppT`, solo es/en/zh). 16-11-2026:
 *  acepta variables (`{{x}}`) como segundo argumento. */
export function useLang(): TraductorDelPortal {
  const lang = useContext(LangContext)
  const custom = useContext(PortalCustomContext)
  return (key: string, vars?: VariablesDelPortal): string => {
    const texto = textoDelPortal(lang, key, custom)
    return vars ? rellenar(texto, vars) : texto
  }
}

/** Error del servidor con código estable (`err_srv.<code>`, 16-11-2026) en el
 *  idioma del portal; null si el portal no tiene ese código (se enseña `detail`). */
export function traductorDeCodigosDelPortal(lang: string, custom: TraduccionesDelPortal = {}): TraductorDeCodigos {
  return (codigo, params) => {
    const clave = `err_srv.${codigo}`
    const texto = textoDelPortal(lang, clave, custom)
    if (!texto || texto === clave) return null
    return params ? rellenar(texto, params as VariablesDelPortal) : texto
  }
}

/** Mensaje de un error del servidor para el cliente: el código traducido a su
 *  idioma o, si no lo hay, `fallback` (y antes el `detail`). Sustituye a
 *  `extractErr` en el portal (16-11-2026). */
export function useErrorDelPortal(): (e: unknown, fallback: string) => string {
  const lang = useContext(LangContext)
  const custom = useContext(PortalCustomContext)
  const traducirCodigo = traductorDeCodigosDelPortal(lang, custom)
  return (e, fallback) => mensajeDeError(e, traducirCodigo, fallback)
}

/** Da al kit (Spinner, Modal, Pagination, Confirm…) y al aviso global los
 *  textos del portal, en sus 8 idiomas (16-11-2026). Fuera de esto, el kit usa
 *  el traductor de operador (es/en/zh). */
export function TextosDeInterfazDelPortal({ children }: { children?: React.ReactNode }) {
  const lang = useContext(LangContext)
  const custom = useContext(PortalCustomContext)
  const t = useLang()
  return (
    <TextosDeInterfazProvider t={(clave, params) => t(clave, params)} lang={lang}
      errorDelServidor={traductorDeCodigosDelPortal(lang, custom)}>
      {children}
    </TextosDeInterfazProvider>
  )
}

// ── Client Auth Context ───────────────────────────────────────────────────────
export const ClientAuthContext = createContext<SesionDeCliente | null>(null)
export function useClientAuth() { return useContext(ClientAuthContext) }

/** Las traducciones que personaliza el administrador (`/portal/branding`) para
 *  todo el portal. 16-11-2026: va por ENCIMA de `TextosDeInterfazDelPortal`
 *  para que el kit (Spinner, Pagination, Confirm…) y el aviso global también
 *  las usen; antes se daban dentro de la aplicación y el proveedor del kit,
 *  montado más arriba, no las veía. */
export function PersonalizacionesDelPortal({ children }: { children?: React.ReactNode }) {
  const client = useClientAuth()?.client ?? null
  const { data: marca } = useQuery({
    queryKey: ['portal-branding'],
    queryFn: () => CLIENT_API.get('/portal/branding').then(r => r.data),
    enabled: !!client,
  })
  return (
    <PortalCustomContext.Provider value={(marca as { translations?: Record<string, Record<string, string>> } | undefined)?.translations ?? {}}>
      {children}
    </PortalCustomContext.Provider>
  )
}

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
    phone,
    job_title,
  } = client as ClienteDelPortal & { phone?: string | null; job_title?: string | null }
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
    // Auditoría 2026-11: sin estos dos, el perfil se abría vacío y al guardar
    // los borraba.
    phone: phone ?? null,
    job_title: job_title ?? null,
  }
}

export function ClientAuthProvider({ children }: { children?: React.ReactNode }) {
  const traducir = useLang()
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
  // Auditoria 2026-11 (#41): trampa de foco y Esc (= continuar sesion).
  const avisoRef = useDialogo<HTMLDivElement>(showWarning, dismiss)

  return (
    <ClientAuthContext.Provider value={{ client, login, logout, isReady }}>
      {children}
      {showWarning && (
        <div role="presentation" className="portalcl-sx1">
          <div ref={avisoRef} role="alertdialog" aria-modal="true" aria-labelledby="aviso-portal-titulo" aria-describedby="aviso-portal-texto" tabIndex={-1} className="portalcl-sx2">
            <div aria-hidden="true" className="poclco-box-1"><Timer size={28} /></div>
            <h3 id="aviso-portal-titulo" className="poclco-box-2">
              {traducir('portalclientcontext.sesion_a_punto_de_expirar')}
            </h3>
            <p id="aviso-portal-texto" className="poclco-box-3">
              {traducir('portalclientcontext.tu_sesion_del_portal_se_cerrara_por')}{' '}
              <strong className={`${secondsLeft <= 15 ? 'portal-client-context-m1' : 'portal-client-context-m2'}`}>
                {secondsLeft}s
              </strong>.
            </p>
            <div className="poclco-row-1">
              <Button onClick={dismiss}>
                {traducir('portalclientcontext.continuar_sesion')}
              </Button>
              <Button variant="secondary" onClick={logout}>
                {traducir('portalclientcontext.cerrar_sesion')}
              </Button>
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
  card: { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4) var(--space-5)' },
  btn: { background: 'var(--accent)', border: 'none', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--portal-bg)', fontSize: "var(--text-md)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' },
  btnSec: { background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit' },
  input: { background: 'var(--surface-4)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: "var(--text-md)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' },
  label: { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 },
}

// ── Shared components ─────────────────────────────────────────────────────────
/** Nombre visible de un estado que manda el servidor (`in_progress`…), en el
 *  idioma del portal (`st_<código>`); nunca el código crudo (16-11-2026). */
export function useEtiquetaEstado() {
  const t = useLang()
  return (status?: string | null): string => {
    if (!status) return ''
    const clave = `st_${status}`
    const v = t(clave)
    if (v && v !== clave) return v
    // 16-11-2026: ya no se cae a `STATUS_CFG[status].label`, que está en
    // castellano; un estado nuevo sin clave sale con su código legible.
    const texto = String(status).replace(/_/g, ' ')
    return texto.charAt(0).toUpperCase() + texto.slice(1)
  }
}

export function Badge({ status }: { status?: string }) {
  const etiqueta = useEtiquetaEstado()
  const cfg = (status && STATUS_CFG[status]) || { label: status, color: 'var(--text-2)' }
  return <StatusBadge color={cfg.color}>{etiqueta(status)}</StatusBadge>
}

interface LangSelectorProps {
  onChange: (code: string) => void
  current?: string
  /** Variante para fondos oscuros. */
  dark?: boolean
}

export function LangSelector({ onChange, current, dark = false }: LangSelectorProps) {
  return (
    <div className="u-row-6">
      {LANGUAGES.map(l => (
        <Pulsable className="poclco-box-12 portalcl-sx3 portal-client-context-e3" key={l.code} onClick={() => onChange(l.code)}
          title={l.label}
          style={{ '--portal-client-context-background': current === l.code ? (dark ? 'var(--surface-4)' : 'var(--accent-glow)') : 'transparent', '--portal-client-context-border': `1px solid ${current === l.code ? 'var(--accent-glow)' : (dark ? 'var(--surface-4)' : 'rgba(255,255,255,0.12)')}` } as CSSProperties}>
          {l.code.toUpperCase()}
        </Pulsable>
      ))}
    </div>
  )
}

export function LoginScreen({ _changeLang, _currentLang }: { _changeLang?: (code: string) => void; _currentLang?: string }) {
  const traducir = useLang()
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


  return (
    <div className="poclco-row-2">
      {/* Brand panel (oculto en pantallas pequeñas) */}
      <div className="portal-login-brand poclco-stack-1">
        <div className="poclco-row-3">
          <div className="poclco-row-5">◈</div>
          <div>
            <div className="poclco-txt-1">{PRODUCT_NAME}</div>
            <div className="poclco-txt-2">{traducir('wiki.vis_portal_cliente')}</div>
          </div>
        </div>
        <div>
          <h1 className="poclco-box-6">
            {t('login_title')}
          </h1>
          <p className="poclco-box-7">
            {t('login_subtitle')}
          </p>
          <div className="poclco-grid-1">
            {[
              { n: 1, Icono: MapIcon },
              { n: 2, Icono: Headphones },
              { n: 3, Icono: FlaskConical },
              { n: 4, Icono: Receipt },
            ].map(({ n, Icono }) => (
              <div key={n} className="poclco-box-8">
                <div className="u-sm-700 poclco-feat"><Icono size={14} aria-hidden="true" />{t(`login_feat_${n}_title`)}</div>
                <div className="u-text3-xs-mt2">{t(`login_feat_${n}_desc`)}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="u-text3-xs">
          © {new Date().getFullYear()} {PRODUCT_FULL_NAME} {traducir('portalclientcontext.portal_cliente')}
        </div>
      </div>

      {/* Form panel */}
      <div className="poclco-row-4">
        <div className="poclco-box-9">
          <h2 className="poclco-box-10">{traducir('portalclientcontext.acceder_al_portal')}</h2>
          <p className="poclco-box-11">
            {traducir('portalclientcontext.usa_tu_correo_corporativo_para_acceder')}
          </p>
          <form onSubmit={e => { e.preventDefault(); handleLogin() }} className="u-stack-14">
            <div>
              <label htmlFor={`${idPrefix}-email`} id={`${idPrefix}-email-etiqueta`} className="poclco-labelstyle">{t('login_email')}</label>
              <input id={`${idPrefix}-email`} aria-labelledby={`${idPrefix}-email-etiqueta`} type="email" autoComplete="email"
                value={email} onChange={e => setEmail(e.target.value)}
                className="poclco-fieldstyle" placeholder={t('login_email_placeholder')} />
            </div>
            <div>
              <label htmlFor={`${idPrefix}-password`} id={`${idPrefix}-password-etiqueta`} className="poclco-labelstyle">{t('login_password')}</label>
              <input id={`${idPrefix}-password`} aria-labelledby={`${idPrefix}-password-etiqueta`} type="password" autoComplete="current-password"
                value={password} onChange={e => setPassword(e.target.value)}
                className="poclco-fieldstyle" placeholder="••••••••" />
            </div>
            {error && (
              <div className="poclco-box-14">{error}</div>
            )}
            <Button className="poclco-box-13" size="lg" type="submit" loading={loading} disabled={!email || !password}>
              {loading ? t('login_loading') : t('login_btn')}
            </Button>
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