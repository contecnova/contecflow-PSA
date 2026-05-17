/**
 * InboxPage — Bandeja unificada de Notificaciones, Menciones y Aprobaciones.
 * Sustituye las 3 páginas separadas (/notifications, /mentions, /approvals).
 * Las rutas antiguas siguen funcionando por compatibilidad pero apuntan al
 * mismo destino con la pestaña correspondiente preseleccionada.
 */
import { lazy, Suspense, useState, useEffect } from 'react'
import type { ComponentType } from 'react'
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

const NotificationsEmbedded = NotificationsPage as ComponentType<{ embedded?: boolean }>
const MentionsEmbedded = MentionsPage as ComponentType<{ embedded?: boolean }>
const ApprovalsEmbedded = ApprovalsPage as ComponentType<{ embedded?: boolean }>

const Loading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
    <Spinner />
  </div>
)

const VALID_TABS = new Set(['notifications', 'mentions', 'approvals'])

type InboxTab = 'notifications' | 'mentions' | 'approvals'

export default function InboxPage(): JSX.Element {
  const t = useAppT()
  const [params, setParams] = useSearchParams()
  const initial = params.get('tab')
  const [tab, setTab] = useState<InboxTab>(
    initial && VALID_TABS.has(initial) ? (initial as InboxTab) : 'notifications'
  )

  useEffect(() => {
    const cur = params.get('tab')
    if (cur !== tab) {
      const next = new URLSearchParams(params)
      next.set('tab', tab)
      setParams(next, { replace: true })
    }
  }, [tab, params, setParams])

  const { alertCount, notifUnreadCount, mentionCount, approvalCount } = useNotificationBadges()

  const items = [
    { id: 'notifications', label: t('inbox.tab_notifications'), count: (alertCount + notifUnreadCount) || undefined },
    { id: 'mentions',      label: t('inbox.tab_mentions'),      count: mentionCount || undefined },
    { id: 'approvals',     label: t('inbox.tab_approvals'),     count: approvalCount || undefined },
  ] as const

  return (
    <PageShell>
      <PageHeader
        icon={<Inbox size={18} />}
        title={t('inbox.title')}
        subtitle={t('inbox.subtitle')}
      showListExport={false}
      />
      <Tabs
        items={items as unknown as { id: string; label: string; count?: number }[]}
        active={tab}
        onChange={(value) => setTab(value as InboxTab)}
        ariaLabel={t('inbox.title')}
        style={{ marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--surface-4)' }}
      />
      <Suspense fallback={<Loading />}>
        {tab === 'notifications' && <NotificationsEmbedded embedded />}
        {tab === 'mentions'      && <MentionsEmbedded embedded />}
        {tab === 'approvals'     && <ApprovalsEmbedded embedded />}
      </Suspense>
    </PageShell>
  )
}
