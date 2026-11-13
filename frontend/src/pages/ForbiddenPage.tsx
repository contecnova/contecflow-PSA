import { Link, useLocation } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'

export default function ForbiddenPage(): JSX.Element {
  const t = useAppT()
  const location = useLocation() as { state?: { from?: string } }
  const from = location.state?.from || t('forbidden.unknown_route')

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--surface-0)',
      color: 'var(--text-1)',
      padding: 24,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 640,
        background: 'var(--surface-1)',
        border: '1px solid var(--surface-4)',
        borderRadius: 'var(--radius-lg)',
        padding: 28,
        boxShadow: '0 12px 28px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: "var(--text-4xl)", marginBottom: 8 }}>403</div>
        <h1 style={{ margin: '0 0 10px', fontSize: "var(--text-xl-em)", color: 'var(--danger)' }}>
          {t('forbidden.title')}
        </h1>
        <p style={{ margin: '0 0 8px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          {t('forbidden.message')}
        </p>
        <p style={{ margin: '0 0 18px', color: 'var(--text-2)', lineHeight: 1.6 }}>
          {t('forbidden.requested_route')} <strong className="u-text1">{from}</strong>
        </p>
        <p style={{ margin: '0 0 22px', color: 'var(--text-3)', fontSize: "var(--text-base)" }}>
          {t('forbidden.contact_admin')}
        </p>
        <div className="u-wrap-10">
          <Link
            to="/"
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              border: 'none',
              textDecoration: 'none',
              background: 'var(--accent)',
              color: 'white',
              fontWeight: 600,
            }}
          >
            {t('forbidden.go_home')}
          </Link>
          <Link
            to="/imputar"
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              border: '1px solid var(--surface-4)',
              textDecoration: 'none',
              background: 'transparent',
              color: 'var(--text-1)',
              fontWeight: 600,
            }}
          >
            {t('forbidden.go_timesheets')}
          </Link>
        </div>
      </div>
    </div>
  )
}
