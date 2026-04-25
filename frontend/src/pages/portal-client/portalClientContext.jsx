/**
 * Shared context, auth, API client, and styles for the client portal.
 * Import from here in all portal-client sub-pages.
 */
import { createContext, useContext, useState, useEffect, useId } from 'react'
import axios from 'axios'
import { PORTAL_TRANSLATIONS as T, PORTAL_LANGUAGES as LANGUAGES } from '../../i18n/portalTranslations'
import { STATUS_CFG } from '../../constants/sharedStatus'

// ── API client ────────────────────────────────────────────────────────────────
export const CLIENT_API = axios.create({ baseURL: '/api/v1', withCredentials: true, timeout: 30000 })

// ── Language Context ──────────────────────────────────────────────────────────
export const LangContext = createContext('es')
export const PORTAL_CUSTOM_KEY = 'clarive_portal_custom'

export function useLang() {
  const lang = useContext(LangContext)
  return (key) => {
    try {
      const custom = JSON.parse(localStorage.getItem(PORTAL_CUSTOM_KEY) || '{}')
      if (custom[lang]?.[key]) return custom[lang][key]
      if (custom['es']?.[key] && !T[lang]?.[key]) return custom['es'][key]
    } catch { /* noop */ }
    return T[lang]?.[key] || T['es']?.[key] || key
  }
}

// ── Client Auth Context ───────────────────────────────────────────────────────
export const ClientAuthContext = createContext(null)
export function useClientAuth() { return useContext(ClientAuthContext) }

function _pickClientUiFields(client) {
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

export function ClientAuthProvider({ children }) {
  const [client, setClient] = useState(() => {
    try { return JSON.parse(localStorage.getItem('client_user') || 'null') } catch { return null }
  })
  const [isReady, setIsReady] = useState(false)
  useEffect(() => {
    let mounted = true
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
  const login = async (email, password) => {
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
  return <ClientAuthContext.Provider value={{ client, login, logout, isReady }}>{children}</ClientAuthContext.Provider>
}

// ── Shared styles ─────────────────────────────────────────────────────────────
export const S = {
  page: { minHeight: '100vh', background: 'var(--surface-0)', color: 'var(--text-1)', fontFamily: "'Inter', system-ui, sans-serif" },
  card: { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: 'var(--space-4) var(--space-5)' },
  badge: (color) => ({ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: color + '20', color, border: `1px solid ${color}40`, textTransform: 'uppercase' }),
  btn: { background: 'var(--accent)', border: 'none', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--portal-bg)', fontSize: 14, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' },
  btnSec: { background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' },
  input: { background: 'var(--surface-4)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 'var(--space-3) var(--space-4)', color: 'var(--text-1)', fontSize: 14, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' },
  label: { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 },
}

// ── Shared components ─────────────────────────────────────────────────────────
export function Badge({ status }) {
  const cfg = STATUS_CFG[status] || { label: status, color: 'var(--text-2)' }
  return <span style={S.badge(cfg.color)}>{cfg.label}</span>
}

export function LangSelector({ onChange, current, dark = false }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      {LANGUAGES.map(l => (
        <button key={l.code} onClick={() => onChange(l.code)}
          title={l.label}
          style={{
            background: current === l.code ? (dark ? 'var(--surface-4)' : 'var(--accent-glow)') : 'transparent',
            border: `1px solid ${current === l.code ? 'var(--accent-glow)' : (dark ? 'var(--surface-4)' : 'rgba(255,255,255,0.12)')}`,
            borderRadius: 8, padding: '5px 9px', cursor: 'pointer',
            fontSize: 16, lineHeight: 1, fontFamily: 'inherit',
            transition: 'all 0.15s',
          }}>
          {l.flag}
        </button>
      ))}
    </div>
  )
}

export function LoginScreen({ _changeLang, _currentLang }) {
  const { login } = useClientAuth()
  const t = useLang()
  const idPrefix = useId()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setError(''); setLoading(true)
    try { await login(email, password) }
    catch { setError(t('login_error')) }
    finally { setLoading(false) }
  }

  return (
    <div style={{ ...S.page, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 420 }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ width: 56, height: 56, background: 'linear-gradient(135deg, #00d4ff, #7c3aed)', borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, margin: '0 auto 16px', fontWeight: 800 }}>◈</div>
          <h1 style={{ fontSize: 26, fontWeight: 800, margin: '0 0 6px' }}>{t('login_title')}</h1>
          <p style={{ color: 'var(--text-2)', margin: 0 }}>{t('login_subtitle')}</p>
        </div>
        <div style={{ ...S.card, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div><label htmlFor={`${idPrefix}-email`} style={S.label}>{t('login_email')}</label><input id={`${idPrefix}-email`} type="email" value={email} onChange={e => setEmail(e.target.value)} style={S.input} placeholder={t('login_email')} onKeyDown={e => e.key === 'Enter' && handleLogin()} /></div>
          <div><label htmlFor={`${idPrefix}-password`} style={S.label}>{t('login_password')}</label><input id={`${idPrefix}-password`} type="password" value={password} onChange={e => setPassword(e.target.value)} style={S.input} placeholder={t('login_password')} onKeyDown={e => e.key === 'Enter' && handleLogin()} /></div>
          {error && <div style={{ fontSize: 13, color: 'var(--danger)', background: 'var(--danger-bg)', borderRadius: 8, padding: '8px 12px' }}>{error}</div>}
          <button onClick={handleLogin} disabled={loading || !email || !password} style={{ ...S.btn, width: '100%', padding: '13px', fontSize: 15, opacity: loading ? 0.6 : 1 }}>
            {loading ? t('login_loading') : t('login_btn')}
          </button>
        </div>
      </div>
    </div>
  )
}