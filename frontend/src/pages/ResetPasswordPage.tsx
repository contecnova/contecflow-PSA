import type { CSSProperties } from 'react'
import { PRODUCT_NAME } from '../constants/brand'
import { useEffect, useMemo, useState, useId } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../services/api'
import type { PoliticaDeContrasena } from '../services/api/seguridadDeCuentas'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import LangSelector from '../components/LangSelector'
import { REDIRECT_AFTER_SUCCESS_MS } from '../constants/timings'
import { Pulsable, Input } from '../components/ui'
import './ResetPasswordPage.css'

function strengthScore(password: string): number {
  let score = 0
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (/[A-Z]/.test(password)) score += 1
  if (/[a-z]/.test(password)) score += 1
  if (/[0-9]/.test(password)) score += 1
  if (/[^A-Za-z0-9]/.test(password)) score += 1
  return Math.min(score, 5)
}

const STRENGTH_COLORS = ['var(--danger)', 'var(--orange)', 'var(--warning)', 'var(--success)', 'color-mix(in srgb, var(--success) 85%, var(--surface-0))', 'color-mix(in srgb, var(--success) 70%, var(--surface-0))']

export default function ResetPasswordPage() {
  const idCampo = useId()
  const t = useAppT()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // 23-11-2026: el token se lee una vez y se quita de la barra de direcciones
  // (historial, capturas, cabecera Referer).
  const [token] = useState(() => searchParams.get('token') || '')
  const [politica, setPolitica] = useState<PoliticaDeContrasena | null>(null)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) return
    window.history.replaceState(null, '', window.location.pathname)
    // Reglas de la empresa del enlace; un token no válido se avisa ya, no al final.
    authApi.resetPasswordPolicy(token)
      .then(r => setPolitica(r.data))
      .catch(e => setError(extractErr(e, t('reset_password.invalid_token_error'))))
  }, [token])  // eslint-disable-line react-hooks/exhaustive-deps

  const score = useMemo(() => strengthScore(password), [password])
  const strengthLabels = [
    t('reset_password.strength_very_weak'),
    t('reset_password.strength_weak'),
    t('reset_password.strength_acceptable'),
    t('reset_password.strength_good'),
    t('reset_password.strength_strong'),
    t('reset_password.strength_excellent'),
  ]

  const submit = async () => {
    if (!token) { setError(t('reset_password.invalid_token_error')); return }
    if (!password) { setError(t('reset_password.new_password_required')); return }
    if (password !== confirmPassword) { setError(t('reset_password.passwords_dont_match')); return }
    if (politica && (password.length < politica.MIN_PASSWORD_LENGTH || password.length > politica.PASSWORD_MAX_LENGTH)) {
      setError(t('seguridad_cuentas.regla_longitud', { min: politica.MIN_PASSWORD_LENGTH, max: politica.PASSWORD_MAX_LENGTH })); return
    }
    setLoading(true); setError(''); setSuccess('')
    try {
      await authApi.resetPassword({ token, new_password: password })
      setSuccess(t('reset_password.success_message'))
      setTimeout(() => navigate('/login'), REDIRECT_AFTER_SUCCESS_MS)
    } catch (e: unknown) {
      setError(extractErr(e, t('reset_password.generic_error')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rpw-stack">
      <div className="rpw-box">
        <LangSelector />
      </div>

      <div className="rpw-card">
        {/* Logo */}
        <div className="rpw-row">
          <div className="rpw-row-2">
            <svg viewBox="0 0 32 32" width="22" height="22" fill="none">
              <circle cx="16" cy="16" r="14" fill="color-mix(in srgb, var(--text-1) 12%, transparent)" />
              <path d="M8 16C8 11.58 11.58 8 16 8C20.42 8 24 11.58 24 16C24 20.42 20.42 24 16 24C11.58 24 8 20.42 8 16Z" fill="white" />
              <path d="M16 12V20M12 16H20" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
          </div>
          <span className="rpw-text-strong">{PRODUCT_NAME}</span>
        </div>

        <h2 className="rpw-title-strong">
          {t('reset_password.form_title')}
        </h2>
        <p className="rpw-text-muted">
          {t('reset_password.brand_subtitle')}
        </p>

        {politica && (
          <ul className="rpw-reglas">
            <li>{t('seguridad_cuentas.regla_longitud', { min: politica.MIN_PASSWORD_LENGTH, max: politica.PASSWORD_MAX_LENGTH })}</li>
            {(politica.PASSWORD_REQUIRE_UPPERCASE || politica.PASSWORD_REQUIRE_LOWERCASE || politica.PASSWORD_REQUIRE_DIGIT || politica.PASSWORD_REQUIRE_SPECIAL)
              && <li>{t('seguridad_cuentas.regla_composicion')}</li>}
            {politica.PASSWORD_BLOCK_COMMON && <li>{t('seguridad_cuentas.regla_comunes')}</li>}
            {politica.PASSWORD_BLOCK_PERSONAL && <li>{t('seguridad_cuentas.regla_personales')}</li>}
            {politica.PASSWORD_HISTORY_COUNT > 0 && <li>{t('seguridad_cuentas.regla_historial', { n: politica.PASSWORD_HISTORY_COUNT })}</li>}
          </ul>
        )}

        <div className="u-stack-16">
          {/* New password */}
          <div>
            <label className="rpw-label-muted" id={`${idCampo}-etpwd`} htmlFor={`${idCampo}-pwd`}>
              {t('reset_password.new_password_placeholder')}
            </label>
            <div className="rpw-box-2">
              <Input inputClassName="rpw-input"
                id={`${idCampo}-pwd`}
                aria-labelledby={`${idCampo}-etpwd`}
                type={showPwd ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="new-password"
                onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
                onBlur={e => { e.target.style.borderColor = 'var(--surface-4)' }}
              />
              <Pulsable className="rpw-btn"
                type="button"
                onClick={() => setShowPwd(v => !v)}
                aria-label={showPwd ? t('login.hide_password_aria') : t('login.show_password_aria')}
              >
                {showPwd ? (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </Pulsable>
            </div>
            {/* Strength bar */}
            {password && (
              <div className="rpw-text">
                <div className="rpw-row-3">
                  {[1, 2, 3, 4, 5].map(i => (
                    <div className="rpw-box-3 rpw-box-5" key={i} style={{ '--rpw-box-5-background': i <= score ? STRENGTH_COLORS[score] : 'var(--surface-4)' } as CSSProperties} />
                  ))}
                </div>
                <span className="rpw-text-2 rpw-text-3" style={{ '--rpw-text-3-color': STRENGTH_COLORS[score] } as CSSProperties}>{strengthLabels[score]}</span>
              </div>
            )}
          </div>

          {/* Confirm */}
          <div>
            <label className="rpw-label-muted" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>
              {t('reset_password.confirm_password_placeholder')}
            </label>
            <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} autoComplete="new-password" onFocus={e => { e.target.style.borderColor = 'var(--accent)' }} onBlur={e => { e.target.style.borderColor = 'var(--surface-4)' }} inputClassName="rpw-input-2" />
          </div>

          {error && (
            <div className="rpw-row-danger" role="alert">
              <span>⚠</span><span>{error}</span>
            </div>
          )}

          {success && (
            <div className="rpw-row-success" role="status">
              <span>✓</span><span>{success}</span>
            </div>
          )}

          <Pulsable className="rpw-btn-2"
            type="button"
            onClick={submit}
            disabled={loading}
            style={{ '--rpw-btn-2-cursor': loading ? 'not-allowed' : 'pointer', '--rpw-btn-2-opacity': loading ? '0.6' : '1' } as CSSProperties}
          >
            {loading ? t('reset_password.updating') : t('reset_password.submit_button')}
          </Pulsable>

          <Link
            to="/login"
            className="rpw-enlace-login"
          >
            {t('reset_password.back_to_login')}
          </Link>
        </div>

        <div className="rpw-box-4">
          {t('login.footer')}
        </div>
      </div>
    </div>
  )
}


