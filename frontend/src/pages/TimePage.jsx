import { useState, Suspense, lazy } from 'react'
import { Clock, Timer, ListChecks } from 'lucide-react'
import { Spinner } from '../components/ui'

const ImputarPage      = lazy(() => import('./ImputarPage'))
const TimerPageContent = lazy(() => import('./TimerPage'))
const TimesheetsPage   = lazy(() => import('./TimesheetsPage'))

const TABS = [
  { id: 'log',   label: 'Registrar',   icon: Clock },
  { id: 'timer', label: 'Cronómetro',  icon: Timer },
  { id: 'week',  label: 'Semana',      icon: ListChecks },
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
      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 0, paddingLeft: 24,
        borderBottom: '2px solid var(--surface-4)',
        background: 'var(--surface-1)',
        flexShrink: 0,
      }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 7,
              padding: '12px 20px',
              border: 'none',
              borderBottom: `2px solid ${tab === id ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -2,
              background: 'transparent',
              color: tab === id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13,
              fontWeight: tab === id ? 700 : 500,
              cursor: 'pointer',
              fontFamily: 'inherit',
              transition: 'color 0.1s, border-color 0.1s',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => { if (tab !== id) e.currentTarget.style.color = 'var(--text-1)' }}
            onMouseLeave={e => { if (tab !== id) e.currentTarget.style.color = 'var(--text-2)' }}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
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
