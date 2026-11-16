/*
 * 16-11-2026: la cabecera de la página ("Tiempo", como el menú) va arriba y a
 * todo el ancho, con las pestañas debajo. Antes las pestañas salían encima de
 * la cabecera de cada subpágina y "Registrar" quedaba en una columna estrecha
 * centrada. Las subpáginas (ImputarPage, TimerPage, TimesheetsPage) siguen
 * pintando su propia PageHeader; aquí se presenta como cabecera de la pestaña
 * (ver TimePage.css).
 */
import { useState, Suspense, lazy } from 'react'
import { Clock, Timer, ListChecks } from 'lucide-react'
import { Spinner, Tabs } from '../components/ui'
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
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
    { id: 'log',   label: t('time_page.tab_log'),   icon: <Clock size={14} /> },
    { id: 'timer', label: t('time_page.tab_timer'), icon: <Timer size={14} /> },
    { id: 'week',  label: t('time_page.tab_week'),  icon: <ListChecks size={14} /> },
  ]

  return (
    <PageShell className="tmp-page">
      <PageHeader
        icon={<Clock size={18} />}
        title={t('nav.time')}
        subtitle={t('time_page.subtitle')}
        showListExport={false}
      />
      <div className="ds-page">
        <Tabs
          items={TABS}
          active={tab}
          onChange={setTab}
          ariaLabel={t('time_page.aria_label')}
        />

        <div className="tmp-body">
          <Suspense fallback={<TabFallback />}>
            {tab === 'log'   && <ImputarPage />}
            {tab === 'timer' && <TimerPageContent />}
            {tab === 'week'  && <TimesheetsPage />}
          </Suspense>
        </div>
      </div>
    </PageShell>
  )
}
