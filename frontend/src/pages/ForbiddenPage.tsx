import { Link, useLocation } from 'react-router-dom'
import { useAppT } from '../i18n/AppLangContext'
import './ForbiddenPage.css'

export default function ForbiddenPage(): JSX.Element {
  const t = useAppT()
  const location = useLocation() as { state?: { from?: string } }
  const from = location.state?.from || t('forbidden.unknown_route')

  return (
    <div className="forb-row">
      <div className="forb-dialog">
        <div className="forb-box">403</div>
        <h1 className="forb-title">
          {t('forbidden.title')}
        </h1>
        <p className="forb-text">
          {t('forbidden.message')}
        </p>
        <p className="forb-text-2">
          {t('forbidden.requested_route')} <strong className="u-text1">{from}</strong>
        </p>
        <p className="forb-text-3">
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
