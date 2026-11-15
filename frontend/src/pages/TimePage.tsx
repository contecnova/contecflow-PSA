import { useState, Suspense, lazy } from 'react'
import { Clock, Timer, ListChecks } from 'lucide-react'
import { Spinner, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import './TimePage.css'

const ImputarPage      = lazy(() => import('./ImputarPage'))
const TimerPageContent = lazy(() => import('./TimerPage'))
const TimesheetsPage   = lazy(() => import('./TimesheetsPage'))

function TabFallback() {
  return (
    <div className="tmp-fallback" role="status" aria-busy="true">
      <Spinner size={24} />
    </div>
  )
}

export default function TimePage() {
  const t = useAppT()
  const [tab, setTab] = useState('log')

  const TABS = [
    { id: 'log',   label: t('time_page.tab_log'),   icon: <Clock size={13} /> },
    { id: 'timer', label: t('time_page.tab_timer'), icon: <Timer size={13} /> },
    { id: 'week',  label: t('time_page.tab_week'),  icon: <ListChecks size={13} /> },
  ]

  return (
    <div className="tmp-page">
      <div className="tmp-tabs">
        <Tabs
          items={TABS}
          active={tab}
          onChange={setTab}
          ariaLabel={t('time_page.aria_label')} className="timepage-sx1"
        />
      </div>

      <div className="u-flex1">
        <Suspense fallback={<TabFallback />}>
          {tab === 'log'   && <ImputarPage />}
          {tab === 'timer' && <TimerPageContent />}
          {tab === 'week'  && <TimesheetsPage />}
        </Suspense>
      </div>
    </div>
  )
}
