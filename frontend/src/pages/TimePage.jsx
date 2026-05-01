import { useState, Suspense, lazy } from 'react'
import { Clock, Timer, ListChecks } from 'lucide-react'
import { Spinner, Tabs } from '../components/ui'

const ImputarPage      = lazy(() => import('./ImputarPage'))
const TimerPageContent = lazy(() => import('./TimerPage'))
const TimesheetsPage   = lazy(() => import('./TimesheetsPage'))

const TABS = [
  { id: 'log',   label: 'Registrar',   icon: <Clock size={13} /> },
  { id: 'timer', label: 'Cronómetro',  icon: <Timer size={13} /> },
  { id: 'week',  label: 'Semana',      icon: <ListChecks size={13} /> },
]

function TabFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 280 }}>
      <Spinner size={24} />
    </div>
  )
}

export default function TimePage() {
  const [tab, setTab] = useState('log')

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
          ariaLabel="Tiempo"
          style={{ marginBottom: 0 }}
        />
      </div>

      <div style={{ flex: 1 }}>
        <Suspense fallback={<TabFallback />}>
          {tab === 'log'   && <ImputarPage />}
          {tab === 'timer' && <TimerPageContent />}
          {tab === 'week'  && <TimesheetsPage />}
        </Suspense>
      </div>
    </div>
  )
}
