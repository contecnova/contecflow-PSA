import { PRODUCT_NAME } from '../constants/brand'
import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import type { Role, User } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import LangSelector from '../components/LangSelector'
import { authApi } from '../services/api'
import type { ConfiguracionDeEntrada, LoginResponse } from '../services/api/auth'
import { resolveLoginResponse } from '../utils/loginFlow'
import type { OrganizacionElegible } from '../utils/loginFlow'
import { startAuthentication, webauthnSupported } from '../lib/webauthn'
import { paginaDeInicio } from '../permisos/navegacion'
import { tomarDestinoTrasLogin } from '../utils/destinoTrasLogin'
import { tieneCapacidad } from '../permisos/capacidades'
import { extractErr } from '../utils/helpers'
import './LoginPage.css'
import { Pulsable, Input, Checkbox } from '../components/ui'

// ── helpers ──────────────────────────────────────────────────────────────────

function extractUser(data: LoginResponse): User {
  // `UserPublic.role` llega como texto; el contexto lo estrecha a `Role`.
  return { ...data.user, role: data.user.role as Role }
}

function extractErrorMsg(
  e: unknown,
  fallback: string,
): string {
  const raw = (e as { response?: { data?: { detail?: string | Array<{ msg: string }> } } })
    ?.response?.data?.detail
  return Array.isArray(raw)
    ? raw.map(d => d.msg).join(', ')
    : (raw as string | undefined) ?? fallback
}

// ── styles (inline, using Contecflow CSS vars) ────────────────────────────────

// Proveedor SSO elegido, para canjear el código cuando el IdP vuelva a /login.
const SSO_CONFIG_KEY = 'cf_sso_config'

const st: Record<string, CSSProperties> = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--surface-0)',
    padding: '24px 16px',
    position: 'relative',
  },
  langWrap: { position: 'absolute', top: 20, right: 24, zIndex: 'calc(var(--z-content) + 9)' },
  card: {
    width: '100%',
    maxWidth: 400,
    background: 'var(--surface-1)',
    border: '1px solid var(--surface-4)',
    borderRadius: 20,
    padding: '36px 32px',
    boxShadow: 'var(--shadow-lg)',
  },
  logo: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    gap: 10, marginBottom: 32,
  },
  logoIcon: {
    width: 40, height: 40, background: 'var(--accent)', borderRadius: 12,
    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  logoText: { fontSize: 'var(--text-xl-em)', fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-0.03em' },
  label: {
    display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-3)',
    marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em',
  },
  input: {
    width: '100%', height: 44, padding: '0 14px',
    background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
    borderRadius: 12, color: 'var(--text-1)', fontSize: 'var(--text-md)',
    fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
    transition: 'border-color 0.15s',
  },
  inputTracked: {
    width: '100%', height: 44, padding: '0 14px',
    background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
    borderRadius: 12, color: 'var(--text-1)', fontSize: 'var(--text-lg-em)',
    fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
    textAlign: 'center', letterSpacing: '0.3em', transition: 'border-color 0.15s',
  },
  btnPrimary: {
    width: '100%', height: 44,
    background: 'var(--accent)', color: 'var(--on-accent)', border: 'none',
    borderRadius: 12, fontWeight: 700, fontSize: 'var(--text-md)', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    transition: 'opacity 0.15s', fontFamily: 'inherit',
  },
  btnSecondary: {
    width: '100%', height: 44,
    background: 'transparent', color: 'var(--text-2)',
    border: '1px solid var(--surface-4)', borderRadius: 12,
    fontWeight: 600, fontSize: 'var(--text-md)', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    transition: 'background 0.15s, border-color 0.15s', fontFamily: 'inherit',
  },
  errorBanner: {
    background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
    borderRadius: 'var(--radius-md)', padding: '10px 14px', color: 'var(--danger)',
    fontSize: 'var(--text-base)', display: 'flex', alignItems: 'flex-start', gap: 8,
  },
  successBanner: {
    background: 'var(--success-bg)', border: '1px solid var(--success-border)',
    borderRadius: 'var(--radius-md)', padding: '10px 14px', color: 'var(--success)',
    fontSize: 'var(--text-base)', display: 'flex', alignItems: 'flex-start', gap: 8,
  },
  warningBanner: {
    background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
    borderRadius: 'var(--radius-md)', padding: '10px 14px', color: 'var(--warning)',
    fontSize: 'var(--text-base)', display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 16,
  },
  divider: { display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0' },
  dividerLine: { flex: 1, height: 1, background: 'var(--surface-4)' },
  dividerText: {
    fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-4)',
    textTransform: 'uppercase', letterSpacing: '0.1em',
  },
  footer: {
    marginTop: 24, paddingTop: 20,
    borderTop: '1px solid var(--surface-4)',
    textAlign: 'center', fontSize: 'var(--text-sm)', color: 'var(--text-4)',
  },
  linkBtn: {
    background: 'none', border: 'none', color: 'var(--accent)',
    fontSize: 'var(--text-base)', cursor: 'pointer', padding: 0, fontFamily: 'inherit', fontWeight: 500,
  },
  form: { display: 'flex', flexDirection: 'column', gap: 16 },
}

// ── SVG icons (inline, no external dependency) ────────────────────────────────

function IconEye() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  )
}

function IconEyeOff() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  )
}

function IconPasskey() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="4"/>
      <path d="M12 8h4M18 6v4"/>
      <path d="M12 8v12a1 1 0 001 1h2"/>
    </svg>
  )
}

function IconShield() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function LoginPage(): JSX.Element {
  const { acceptSession, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const t = useAppT()

  // credentials
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [trap, setTrap] = useState('') // honeypot

  // feedback
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // busy states
  const [loading, setLoading] = useState(false)
  const [passkeyLoading, setPasskeyLoading] = useState(false)
  const [ssoLoading, setSsoLoading] = useState(false)
  const [forgotLoading, setForgotLoading] = useState(false)

  // MFA challenge
  const [mfaChallengeToken, setMfaChallengeToken] = useState<string | null>(null)
  const [mfaMethods, setMfaMethods] = useState<string[]>([])
  const [mfaCode, setMfaCode] = useState('')
  const [recordarDispositivo, setRecordarDispositivo] = useState(false)

  // Empresa (revisión multitenant 2026-11): modo de entrada del despliegue,
  // código de empresa (modo org_field) y selector si pertenece a varias.
  const [entrada, setEntrada] = useState<ConfiguracionDeEntrada | null>(null)
  const [orgCode, setOrgCode] = useState('')
  const [eleccion, setEleccion] = useState<{ token: string; organizations: OrganizacionElegible[] } | null>(null)

  // SSO providers
  const [ssoProviders, setSsoProviders] = useState<Array<{ id: string; provider: string; name: string; icon?: string }>>([])

  // forgot password inline mode
  const [forgotMode, setForgotMode] = useState(false)
  const [forgotInput, setForgotInput] = useState('')

  const logoutReason = searchParams.get('reason') || ''
  const showSessionBanner = sessionExpired
    || logoutReason === 'inactivity_timeout'
    || logoutReason === 'token_reuse'
    || logoutReason === 'backend_refresh_failed'

  // ── Vuelta del ACS SAML (?saml_ticket=… o ?saml_error=…) ──────────────────
  // 23-11-2026: el backend valida la respuesta del IdP y deja la identidad tras
  // un ticket de un solo uso; aquí se canjea por la sesión (o el reto MFA).
  useEffect(() => {
    const ticket = searchParams.get('saml_ticket')
    const fallo = searchParams.get('saml_error')
    if (!ticket && !fallo) return
    window.history.replaceState({}, '', '/login')
    if (fallo) { setError(t('login.saml_rechazado', { codigo: fallo })); return }
    setSsoLoading(true); setError('')
    authApi.samlCanjear(ticket as string)
      .then(({ data }) => procesar(data))
      .catch(e => setError(extractErrorMsg(e, t('login.sso_error'))))
      .finally(() => setSsoLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Vuelta del proveedor SSO (?code=…&state=…) ─────────────────────────────
  // Auditoría 2026-11: el proveedor redirigía aquí y nada canjeaba el código.
  useEffect(() => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const configId = sessionStorage.getItem(SSO_CONFIG_KEY)
    if (!code || !state || !configId) return
    sessionStorage.removeItem(SSO_CONFIG_KEY)
    window.history.replaceState({}, '', '/login')
    setSsoLoading(true); setError('')
    authApi.ssoCallback(configId, { code, state, redirect_uri: `${window.location.origin}/login` })
      .then(({ data }) => procesar(data))
      .catch(e => setError(extractErrorMsg(e, t('login.sso_error'))))
      .finally(() => setSsoLoading(false))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    authApi.entryConfig().then(({ data }) => setEntrada(data)).catch(() => { /* accesorio: sin la configuración de entrada se muestra el login estándar */ })
  }, [])

  // Segunda auditoría 2026-11 (#11): en modo email_selector los botones SSO
  // dependen del dominio del correo escrito; se piden de nuevo al cambiarlo.
  const dominioDelCorreo = username.includes('@') ? username.split('@').pop()?.trim().toLowerCase() ?? '' : ''
  useEffect(() => {
    let mounted = true
    const temporizador = setTimeout(() => {
      authApi.listSsoProviders(dominioDelCorreo ? `@${dominioDelCorreo}` : undefined)
        .then(({ data }) => { if (mounted) setSsoProviders(Array.isArray(data) ? data : []) })
        .catch(() => { /* accesorio: sin proveedores SSO se muestra solo usuario y contraseña */ })
    }, dominioDelCorreo ? 300 : 0)
    return () => { mounted = false; clearTimeout(temporizador) }
  }, [dominioDelCorreo])

  // ── navigation helper ──────────────────────────────────────────────────────
  function navAfterLogin(user: User) {
    // 19-11-2026: la misma página de inicio que la raíz (`paginaDeInicio`, por capacidades).
    // Auditoría 22-11-2026 (M1 del 04): primero el enlace profundo que trajo hasta aquí.
    navigate(tomarDestinoTrasLogin() ?? paginaDeInicio(c => tieneCapacidad(user.capacidades, c)), { replace: true })
  }

  /** Una respuesta de login (contraseña, SSO, passkey o empresa elegida): sesión, segundo factor o selector. */
  function procesar(data: LoginResponse) {
    const parsed = resolveLoginResponse({ ...data })
    if (parsed.kind === 'error') { setError(parsed.message); return }
    if (parsed.kind === 'org') {
      setEleccion({ token: parsed.selectionToken, organizations: parsed.organizations })
      setError('')
      return
    }
    if (parsed.kind === 'mfa') {
      setEleccion(null)
      setMfaChallengeToken(parsed.mfaChallengeToken)
      setMfaMethods(parsed.mfaMethods)
      setError('')
      return
    }
    const user = extractUser(data)
    acceptSession(user)
    navAfterLogin(user)
  }

  async function elegirEmpresa(organizationId: string) {
    if (!eleccion) return
    setLoading(true); setError('')
    try {
      const { data } = await authApi.selectOrganization({ selection_token: eleccion.token, organization_id: organizationId })
      procesar(data)
    } catch (e) {
      setEleccion(null)
      setError(extractErrorMsg(e, t('login.credentials_error')))
    } finally {
      setLoading(false)
    }
  }

  // ── normal submit ──────────────────────────────────────────────────────────
  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (trap.trim()) return
    if (!username || !password) { setError(t('login.input_error')); return }
    const pideEmpresa = entrada?.mode === 'org_field'
    if (pideEmpresa && !orgCode.trim()) { setError(t('login.org_required')); return }
    setLoading(true); setError('')
    try {
      const { data } = await authApi.login({
        username, password, ...(pideEmpresa ? { organization: orgCode.trim() } : {}),
      })
      procesar(data)
    } catch (e) {
      setError(extractErrorMsg(e, t('login.credentials_error')))
    } finally {
      setLoading(false)
    }
  }

  // ── MFA verify ────────────────────────────────────────────────────────────
  async function handleMfaVerify(e: FormEvent) {
    e.preventDefault()
    if (!mfaChallengeToken || mfaCode.trim().length < 6) {
      setError(t('login.mfa_code_error')); return
    }
    setLoading(true); setError('')
    try {
      const { data } = await authApi.validateMfa({
        mfa_challenge_token: mfaChallengeToken,
        code: mfaCode.trim(),
        remember_device: recordarDispositivo,
      })
      const user = extractUser(data)
      acceptSession(user)
      navAfterLogin(user)
    } catch (e) {
      setError(extractErrorMsg(e, t('login.mfa_code_error')))
    } finally {
      setLoading(false)
    }
  }

  function cancelMfa() {
    setMfaChallengeToken(null); setMfaMethods([]); setMfaCode(''); setError('')
  }

  // ── SSO ───────────────────────────────────────────────────────────────────
  async function handleSso(provider: { id: string; name: string; provider?: string }) {
    setSsoLoading(true); setError('')
    try {
      // SAML (23-11-2026): el IdP vuelve al ACS del backend, no a esta página.
      const esSaml = provider.provider === 'saml'
      if (!esSaml) sessionStorage.setItem(SSO_CONFIG_KEY, provider.id)
      const { data } = esSaml
        ? await authApi.authorizeSaml(provider.id)
        : await authApi.authorizeSso(provider.id, `${window.location.origin}/login`)
      const url = (data as { authorization_url?: string }).authorization_url
      if (url) { window.location.assign(url); return }
      setError(t('login.sso_error'))
    } catch (e) {
      setError(extractErrorMsg(e, t('login.sso_error')))
    } finally {
      setSsoLoading(false)
    }
  }

  // ── Passkey ───────────────────────────────────────────────────────────────
  // Auditoría 2026-11: antes llamaba a /auth/login con la contraseña vacía (401
  // y un intento fallido más en la cuenta). Ahora: passkey sola, sin usuario.
  async function handlePasskeyLogin() {
    if (!webauthnSupported()) { setError(t('login.passkey_not_supported')); return }
    setPasskeyLoading(true); setError('')
    try {
      const { data: startData } = await authApi.passkeyLoginStart()
      const credential = await startAuthentication(startData.options)
      const { data } = await authApi.passkeyLoginFinish({
        webauthn_challenge_token: startData.webauthn_challenge_token, credential,
      })
      procesar(data)
    } catch (e) {
      setError(extractErrorMsg(e, t('login.passkey_error')))
    } finally {
      setPasskeyLoading(false)
    }
  }

  // Passkey como segundo factor (después de la contraseña o del SSO).
  async function handleMfaPasskey() {
    if (!mfaChallengeToken) return
    if (!webauthnSupported()) { setError(t('login.passkey_not_supported')); return }
    setPasskeyLoading(true); setError('')
    try {
      const { data: startData } = await authApi.startPasskeyAuth({ mfa_challenge_token: mfaChallengeToken })
      const credential = await startAuthentication(startData.options)
      const { data } = await authApi.finishPasskeyAuth({
        mfa_challenge_token: mfaChallengeToken,
        webauthn_challenge_token: startData.webauthn_challenge_token,
        credential,
      })
      const user = extractUser(data)
      acceptSession(user)
      navAfterLogin(user)
    } catch (e) {
      setError(extractErrorMsg(e, t('login.passkey_error')))
    } finally {
      setPasskeyLoading(false)
    }
  }

  // ── Forgot password ───────────────────────────────────────────────────────
  async function handleForgotPassword(e: FormEvent) {
    e.preventDefault()
    if (!forgotInput.trim()) { setError(t('login.forgot_fill_field')); return }
    setForgotLoading(true); setError(''); setMessage('')
    try {
      await authApi.forgotPassword({
        email_or_username: forgotInput.trim(),
      } as import('../services/api').ForgotPasswordPayload)
      // 23-11-2026: el aviso en el idioma del operador (el servidor responde en castellano).
      setMessage(t('login.forgot_email_sent'))
    } catch (e) {
      setError(extractErr(e, t('login.forgot_error')))
    } finally {
      setForgotLoading(false)
    }
  }

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div style={st.page}>
      <div style={st.langWrap}><LangSelector /></div>

      <div style={st.card}>
        {/* Logo */}
        <div style={st.logo}>
          <div style={st.logoIcon}>
            <svg viewBox="0 0 32 32" width="22" height="22" fill="none">
              <circle cx="16" cy="16" r="14" fill="var(--on-dark-faint-xs)" />
              <path d="M8 16C8 11.58 11.58 8 16 8C20.42 8 24 11.58 24 16C24 20.42 20.42 24 16 24C11.58 24 8 20.42 8 16Z" fill="white" />
              <path d="M16 12V20M12 16H20" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
          </div>
          <span style={st.logoText}>{entrada?.organization?.name || PRODUCT_NAME}</span>
        </div>

        {/* Session expired banner */}
        {showSessionBanner && (
          <div style={st.warningBanner} role="alert">
            <span>⚠</span>
            <span>{t('login.session_expired_message')}</span>
          </div>
        )}

        {/* ── Selector de empresa (pertenece a varias) ──────────── */}
        {eleccion ? (
          <div style={st.form}>
            <p className="lgn-text">
              {t('login.choose_org')}
            </p>
            <div role="list" className="u-stack-8">
              {eleccion.organizations.map(o => (
                <div key={o.id} role="listitem">
                <Pulsable type="button" disabled={loading}
                  onClick={() => { void elegirEmpresa(o.id) }}
                  className="login-page-e1">
                  {o.logo_url
                    ? <img src={o.logo_url} alt="" className="lgn-box" />
                    : <span aria-hidden="true" className="lgn-row">{o.name.slice(0, 1)}</span>}
                  <span>{o.name}</span>
                </Pulsable>
                </div>
              ))}
            </div>
            {error && (
              <div style={st.errorBanner} role="alert"><span>⚠</span><span>{error}</span></div>
            )}
            <Pulsable type="button" onClick={() => { setEleccion(null); setError('') }}
              className="login-page-e2">
              {t('login.mfa_cancel')}
            </Pulsable>
          </div>

        ) : mfaChallengeToken ? (
          <form onSubmit={handleMfaVerify} style={st.form} noValidate>
            <p className="lgn-text">
              {t('login.mfa_prompt')}
            </p>
            <div>
              <Input label={t('login.mfa_code_placeholder')}
                id="mfa_code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                value={mfaCode}
                onChange={e => setMfaCode(e.target.value.replace(/[^0-9a-fA-F]/g, '').toUpperCase().slice(0, 8))}
              />
              <p className="lgn-text-2">
                {t('login.mfa_backup_hint')}
              </p>
              {/* 23-11-2026: solo surte efecto si la empresa lo permite (MFA_REMEMBER_DEVICE_DAYS). */}
              <Checkbox checked={recordarDispositivo} onChange={setRecordarDispositivo} label={t('login.mfa_remember_device')} />
            </div>
            {mfaMethods.includes('webauthn') && (
              <Pulsable type="button" onClick={() => { void handleMfaPasskey() }} disabled={passkeyLoading}
                className="login-page-e3">
                {passkeyLoading ? t('login.passkey_busy') : t('login.mfa_use_passkey')}
              </Pulsable>
            )}
            {error && (
              <div style={st.errorBanner} role="alert">
                <span>⚠</span><span>{error}</span>
              </div>
            )}
            <Pulsable
              type="submit"
              disabled={loading || mfaCode.trim().length < 6}
              className={`login-page-e4 ${loading || mfaCode.trim().length < 6 ? 'login-page-m5' : 'login-page-m6'}`}
            >
              {loading ? t('login.mfa_verifying') : t('login.mfa_verify_button')}
            </Pulsable>
            <Pulsable
              type="button"
              onClick={cancelMfa}
              className="login-page-e2"
            >
              {t('login.mfa_cancel')}
            </Pulsable>
          </form>

        ) : forgotMode ? (

          /* ── Forgot password step ────────────────────────────── */
          <form onSubmit={handleForgotPassword} style={st.form} noValidate>
            <Input label={t('login.username_label')}
                id="forgot_input"
                type="text"
                autoFocus
                autoComplete="email"
                value={forgotInput}
                onChange={e => setForgotInput(e.target.value)}
                placeholder={t('login.username_placeholder')}
              />
            {error && (
              <div style={st.errorBanner} role="alert"><span>⚠</span><span>{error}</span></div>
            )}
            {message && (
              <div style={st.successBanner} role="status"><span>✓</span><span>{message}</span></div>
            )}
            <Pulsable
              type="submit"
              disabled={forgotLoading}
              className={`login-page-e4 ${forgotLoading ? 'login-page-m5' : 'login-page-m6'}`}
            >
              {forgotLoading ? t('login.forgot_sending') : t('login.forgot_send_button')}
            </Pulsable>
            <Pulsable
              type="button"
              onClick={() => { setForgotMode(false); setError(''); setMessage('') }}
              className="login-page-e2"
            >
              {t('login.forgot_back')}
            </Pulsable>
          </form>

        ) : (

          /* ── Main credentials form ───────────────────────────── */
          <>
            {ssoProviders.length > 0 && (
              <>
                <div className="lgn-stack">
                  {ssoProviders.map(p => (
                    <Pulsable
                      key={p.id}
                      type="button"
                      onClick={() => { void handleSso(p) }}
                      disabled={ssoLoading}
                      className={`login-page-e7 ${ssoLoading ? 'login-page-m5' : 'login-page-m6'}`}
                    >
                      <IconShield />
                      <span>
                        {ssoLoading
                          ? t('login.sso_redirecting')
                          : t('login.sso_continue_with', { name: p.name })}
                      </span>
                    </Pulsable>
                  ))}
                </div>
                <div style={st.divider}>
                  <div style={st.dividerLine} />
                  <span style={st.dividerText}>{t('login.or_credentials')}</span>
                  <div style={st.dividerLine} />
                </div>
              </>
            )}

            <form onSubmit={handleSubmit} style={st.form} noValidate>
              {/* Honeypot — hidden from humans, catches bots */}
              <div aria-hidden="true" className="lgn-box-2">
                <Input aria-label={t('pagina_lgn.no_rellenar')} tabIndex={-1} autoComplete="off" data-1p-ignore="true" data-lpignore="true" data-bwignore="true" value={trap} onChange={e => setTrap(e.target.value)} />
              </div>

              {/* Empresa (modo org_field) */}
              {entrada?.mode === 'org_field' && (
                <Input label={t('login.org_label')}
                    id="login_org"
                    type="text"
                    autoComplete="organization"
                    value={orgCode}
                    onChange={e => setOrgCode(e.target.value)}
                    placeholder={t('login.org_placeholder')}
                  />
              )}

              {/* Username */}
              <Input label={t('login.username_label')}
                  id="login_username"
                  type="text"
                  autoFocus
                  autoComplete="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  placeholder={t('login.username_placeholder')}
                />

              {/* Password */}
              <div>
                <div className="lgn-row-2">
                  <label id="login_password-et" className="login-page-e8" htmlFor="login_password">
                    {t('login.password_label')}
                  </label>
                  <Pulsable
                    type="button"
                    onClick={() => { setForgotMode(true); setError(''); setMessage('') }}
                    style={st.linkBtn}
                  >
                    {t('login.forgot_password')}
                  </Pulsable>
                </div>
                <div className="lgn-box-3">
                  <Input
                    id="login_password" aria-labelledby="login_password-et"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder={t('login.password_placeholder')}
                    inputClassName="login-page-pw"
                  />
                  <Pulsable
                    type="button"
                    onClick={() => setShowPassword(v => !v)}
                    aria-label={showPassword ? t('login.hide_password_aria') : t('login.show_password_aria')}
                    className="lgn-btn"
                  >
                    {showPassword ? <IconEyeOff /> : <IconEye />}
                  </Pulsable>
                </div>
              </div>

              {/* Error */}
              {error && (
                <div style={st.errorBanner} role="alert">
                  <span>⚠</span><span>{error}</span>
                </div>
              )}

              {/* Submit */}
              <Pulsable
                type="submit"
                disabled={loading}
                className={`login-page-e4 ${loading ? 'login-page-m5' : 'login-page-m6'}`}
              >
                {loading ? t('login.loading_button') : t('login.login_button')}
              </Pulsable>

              {/* Passkey */}
              <Pulsable
                type="button"
                onClick={() => { void handlePasskeyLogin() }}
                disabled={passkeyLoading}
                className={`login-page-e7 ${passkeyLoading ? 'login-page-m5' : 'login-page-m6'}`}
              >
                <IconPasskey />
                <span>{passkeyLoading ? t('login.passkey_busy') : t('login.passkey_button')}</span>
              </Pulsable>
            </form>
          </>
        )}

        {/* Footer */}
        <div style={st.footer}>{t('login.footer')}</div>
      </div>
    </div>
  )
}
