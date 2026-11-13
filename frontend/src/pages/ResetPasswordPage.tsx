import { PRODUCT_NAME } from '../constants/brand'
import { useMemo, useState, useId } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAppT } from '../i18n/AppLangContext'
import LangSelector from '../components/LangSelector'
import { REDIRECT_AFTER_SUCCESS_MS } from '../constants/timings'

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

const STRENGTH_COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#16a34a', '#15803d']

export default function ResetPasswordPage() {
  const idCampo = useId()
  const t = useAppT()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

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
    setLoading(true); setError(''); setSuccess('')
    try {
      const { data } = await authApi.resetPassword({ token, new_password: password })
      setSuccess((data as { ok: boolean; message?: string })?.message || t('reset_password.success_message'))
      setTimeout(() => navigate('/login'), REDIRECT_AFTER_SUCCESS_MS)
    } catch (e: unknown) {
      const raw = (e as { response?: { data?: { detail?: string | Array<{ msg: string }> } } })?.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : ((raw as string) || t('reset_password.generic_error')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      background: 'var(--surface-0)', padding: '24px 16px', position: 'relative',
    }}>
      <div style={{ position: 'absolute', top: 20, right: 24, zIndex: 10 }}>
        <LangSelector />
      </div>

      <div style={{
        width: '100%', maxWidth: 400,
        background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
        borderRadius: 20, padding: '36px 32px',
        boxShadow: '0 8px 40px rgba(0,0,0,0.35)',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 32 }}>
          <div style={{
            width: 40, height: 40, background: 'var(--accent)', borderRadius: 12,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <svg viewBox="0 0 32 32" width="22" height="22" fill="none">
              <circle cx="16" cy="16" r="14" fill="rgba(255,255,255,0.12)" />
              <path d="M8 16C8 11.58 11.58 8 16 8C20.42 8 24 11.58 24 16C24 20.42 20.42 24 16 24C11.58 24 8 20.42 8 16Z" fill="white" />
              <path d="M16 12V20M12 16H20" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
          </div>
          <span style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-0.03em' }}>{PRODUCT_NAME}</span>
        </div>

        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-1)', marginBottom: 6, textAlign: 'center' }}>
          {t('reset_password.form_title')}
        </h2>
        <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 24, textAlign: 'center' }}>
          {t('reset_password.brand_subtitle')}
        </p>

        <div className="u-stack-16">
          {/* New password */}
          <div>
            <label id={`${idCampo}-etpwd`} htmlFor={`${idCampo}-pwd`} style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {t('reset_password.new_password_placeholder')}
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id={`${idCampo}-pwd`}
                aria-labelledby={`${idCampo}-etpwd`}
                type={showPwd ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="new-password"
                style={{
                  width: '100%', height: 44, padding: '0 44px 0 14px',
                  background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                  borderRadius: 12, color: 'var(--text-1)', fontSize: 14,
                  fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
                }}
                onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
                onBlur={e => { e.target.style.borderColor = 'var(--surface-4)' }}
              />
              <button
                type="button"
                onClick={() => setShowPwd(v => !v)}
                style={{
                  position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', padding: 4,
                }}
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
              </button>
            </div>
            {/* Strength bar */}
            {password && (
              <div style={{ marginTop: 8 }}>
                <div style={{ display: 'flex', gap: 3, marginBottom: 4 }}>
                  {[1, 2, 3, 4, 5].map(i => (
                    <div key={i} style={{
                      flex: 1, height: 3, borderRadius: 2,
                      background: i <= score ? STRENGTH_COLORS[score] : 'var(--surface-4)',
                      transition: 'background 0.2s',
                    }} />
                  ))}
                </div>
                <span style={{ fontSize: 11, color: STRENGTH_COLORS[score] }}>{strengthLabels[score]}</span>
              </div>
            )}
          </div>

          {/* Confirm */}
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {t('reset_password.confirm_password_placeholder')}
            </label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              style={{
                width: '100%', height: 44, padding: '0 14px',
                background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                borderRadius: 12, color: 'var(--text-1)', fontSize: 14,
                fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
              }}
              onFocus={e => { e.target.style.borderColor = 'var(--accent)' }}
              onBlur={e => { e.target.style.borderColor = 'var(--surface-4)' }}
            />
          </div>

          {error && (
            <div role="alert" style={{
              background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
              borderRadius: 'var(--radius-md)', padding: '10px 14px', color: 'var(--danger)', fontSize: 13,
              display: 'flex', gap: 8,
            }}>
              <span>⚠</span><span>{error}</span>
            </div>
          )}

          {success && (
            <div role="status" style={{
              background: 'var(--success-bg)', border: '1px solid var(--success-border)',
              borderRadius: 'var(--radius-md)', padding: '10px 14px', color: 'var(--success)', fontSize: 13,
              display: 'flex', gap: 8,
            }}>
              <span>✓</span><span>{success}</span>
            </div>
          )}

          <button
            type="button"
            onClick={submit}
            disabled={loading}
            style={{
              width: '100%', height: 44, background: 'var(--accent)', color: 'var(--on-accent)',
              border: 'none', borderRadius: 12, fontWeight: 700, fontSize: 14,
              cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1,
              fontFamily: 'inherit', transition: 'opacity 0.15s',
            }}
          >
            {loading ? t('reset_password.updating') : t('reset_password.submit_button')}
          </button>

          <Link
            to="/login"
            style={{ textAlign: 'center', fontSize: 13, color: 'var(--accent)', textDecoration: 'none' }}
          >
            {t('reset_password.back_to_login')}
          </Link>
        </div>

        <div style={{
          marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--surface-4)',
          textAlign: 'center', fontSize: 12, color: 'var(--text-4)',
        }}>
          {t('login.footer')}
        </div>
      </div>
    </div>
  )
}


