import { useState, Suspense, lazy } from 'react'
import { Clock, Timer, ListChecks } from 'lucide-react'
import { Spinner, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const ImputarPage      = lazy(() => import('./ImputarPage'))
const TimerPageContent = lazy(() => import('./TimerPage'))
const TimesheetsPage   = lazy(() => import('./TimesheetsPage'))

function TabFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 280 }}>
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
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <div
        style={{
          padding: 'var(--page-pad-y) var(--page-pad-x) 0',
          flexShrink: 0,
        }}
      >
        <Tabs
          items={TABS}
          active={tab}
          onChange={setTab}
          ariaLabel={t('time_page.aria_label')}
          style={{ marginBottom: 0 }}
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
