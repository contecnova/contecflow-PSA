import { Link, useLocation } from 'react-router-dom'
// TODO type: i18n/AppLangContext still JS — useAppT returns a translator function
import { useAppT } from '../i18n/AppLangContext'
import './NotFoundPage.css'

export default function NotFoundPage(): JSX.Element {
  const t = useAppT()
  const location = useLocation()

  return (
    <div className="nf-row">
      <div className="nf-dialog">
        <div className="nf-box">404</div>
        <h1 className="nf-title">
          {t('not_found_page.title')}
        </h1>
        <p className="nf-text">
          {t('not_found_page.message')}
        </p>
        <p className="nf-text-2">
          {t('not_found_page.requested_route')} <strong className="u-text1">{location.pathname}</strong>
        </p>
        <div className="u-wrap-10">
          <Link
            to="/"
            className="nf-card"
          >
            {t('not_found_page.go_home')}
          </Link>
          <Link
            to="/tasks"
            className="nf-card-2"
          >
            {t('not_found_page.go_tasks')}
          </Link>
        </div>
      </div>
    </div>
  )
}
