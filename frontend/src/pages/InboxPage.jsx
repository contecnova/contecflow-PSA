/**
 * InboxPage — Bandeja unificada de Notificaciones, Menciones y Aprobaciones.
 * Sustituye las 3 páginas separadas (/notifications, /mentions, /approvals).
 * Las rutas antiguas siguen funcionando por compatibilidad pero apuntan al
 * mismo destino con la pestaña correspondiente preseleccionada.
 */
import { lazy, Suspense, useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Inbox } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Tabs, Spinner } from '../components/ui'
import useNotificationBadges from '../hooks/useNotificationBadges'
import { useAppT } from '../i18n/AppLangContext'

const NotificationsPage = lazy(() => import('./NotificationsPage'))
const MentionsPage = lazy(() => import('./MentionsPage'))
const ApprovalsPage = lazy(() => import('./ApprovalsPage'))

const Loading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
    <Spinner />
  </div>
)

const VALID_TABS = new Set(['notifications', 'mentions', 'approvals'])

export default function InboxPage() {
  const t = useAppT()
  const [params, setParams] = useSearchParams()
  const initial = params.get('tab')
  const [tab, setTab] = useState(VALID_TABS.has(initial) ? initial : 'notifications')

  useEffect(() => {
    const cur = params.get('tab')
    if (cur !== tab) {
      const next = new URLSearchParams(params)
      next.set('tab', tab)
      setParams(next, { replace: true })
    }
  }, [tab, params, setParams])

  const { alertCount, mentionCount, approvalCount } = useNotificationBadges()

  const items = [
    { id: 'notifications', label: t('inbox.tab_notifications'), count: alertCount || undefined },
    { id: 'mentions',      label: t('inbox.tab_mentions'),      count: mentionCount || undefined },
    { id: 'approvals',     label: t('inbox.tab_approvals'),     count: approvalCount || undefined },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<Inbox size={18} />}
        title={t('inbox.title')}
        subtitle={t('inbox.subtitle')}
      />
      <Tabs
        items={items}
        active={tab}
        onChange={setTab}
        ariaLabel={t('inbox.title')}
        style={{ marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--surface-4)' }}
      />
      <Suspense fallback={<Loading />}>
        {tab === 'notifications' && <NotificationsPage embedded />}
        {tab === 'mentions'      && <MentionsPage embedded />}
        {tab === 'approvals'     && <ApprovalsPage embedded />}
      </Suspense>
    </PageShell>
  )
}
