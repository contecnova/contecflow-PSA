import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAppT } from '../i18n/AppLangContext'

function strengthScore(password) {
  let score = 0
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (/[A-Z]/.test(password)) score += 1
  if (/[a-z]/.test(password)) score += 1
  if (/[0-9]/.test(password)) score += 1
  if (/[^A-Za-z0-9]/.test(password)) score += 1
  return Math.min(score, 5)
}

export default function ResetPasswordPage() {
  const t = useAppT()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
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
  const strengthLabel = strengthLabels[score]

  const submit = async () => {
    if (!token) {
      setError(t('reset_password.invalid_token_error'))
      return
    }
    if (!password) {
      setError(t('reset_password.new_password_required'))
      return
    }
    if (password !== confirmPassword) {
      setError(t('reset_password.passwords_dont_match'))
      return
    }

    setLoading(true)
    setError('')
    setSuccess('')
    try {
      const { data } = await authApi.resetPassword({ token, new_password: password })
      setSuccess((data as { ok: boolean; message?: string })?.message || t('reset_password.success_message'))
      setTimeout(() => navigate('/login'), 1200)
    } catch (e) {
      const raw = e.response?.data?.detail
      setError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || t('reset_password.generic_error')))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-layout">
      <div className="login-brand-panel">
        <div style={{ position: 'relative', zIndex: 1 }}>
          <h2 style={{ fontSize: "var(--text-3xl)", fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.2, color: 'var(--text-1)', marginBottom: 12 }}>
            {t('reset_password.brand_title_line1')}
            <br />
            <span style={{ color: 'var(--accent)' }}>{t('reset_password.brand_title_line2')}</span>
          </h2>
          <p style={{ color: 'var(--text-2)', fontSize: "var(--text-md)", lineHeight: 1.6, marginBottom: 20, maxWidth: 320 }}>
            {t('reset_password.brand_subtitle')}
          </p>
          <Link to="/login" style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: "var(--text-base)" }}>
            {t('reset_password.back_to_login')}
          </Link>
        </div>
      </div>

      <div className="login-form-panel">
        <div style={{ width: '100%', maxWidth: 380 }}>
          <h3 style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-1)', marginBottom: 8 }}>
            {t('reset_password.form_title')}
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('reset_password.new_password_placeholder')}
              autoComplete="new-password"
              style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: "var(--text-md)", outline: 'none', boxSizing: 'border-box' }}
            />

            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t('reset_password.confirm_password_placeholder')}
              autoComplete="new-password"
              style={{ width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-5)', borderRadius: 8, padding: '11px 14px', color: 'var(--text-1)', fontSize: "var(--text-md)", outline: 'none', boxSizing: 'border-box' }}
            />

            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>
              {t('reset_password.strength_label')}: <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{strengthLabel}</span>
            </div>

            {error && (
              <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.25)', borderRadius: 8, padding: '10px 14px', color: 'var(--danger)', fontSize: "var(--text-base)" }}>
                {error}
              </div>
            )}

            {success && (
              <div style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, padding: '10px 14px', color: 'var(--success)', fontSize: "var(--text-base)" }}>
                {success}
              </div>
            )}

            <button
              type="button"
              onClick={submit}
              disabled={loading}
              className="btn-primary"
              style={{ width: '100%', padding: '12px', marginTop: 4, fontSize: "var(--text-md)", fontWeight: 700 }}
            >
              {loading ? t('reset_password.updating') : t('reset_password.submit_button')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
