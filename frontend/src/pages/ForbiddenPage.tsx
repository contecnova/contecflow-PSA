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
            className="forb-card"
          >
            {t('forbidden.go_home')}
          </Link>
          <Link
            to="/imputar"
            className="forb-card-2"
          >
            {t('forbidden.go_timesheets')}
          </Link>
        </div>
      </div>
    </div>
  )
}
