/**
 * InboxPage — Bandeja unificada de Notificaciones, Menciones y Aprobaciones.
 * Sustituye las 3 páginas separadas (/notifications, /mentions, /approvals).
 * Las rutas antiguas siguen funcionando por compatibilidad pero apuntan al
 * mismo destino con la pestaña correspondiente preseleccionada.
 *
 * Revisión BPM 2026-11-16: pestaña «Procesos» con los pasos de procesos BPM
 * que le tocan al usuario. RRHH y empleados no entran en /bpm, y las tareas de
 * las calles «RRHH» o «Empleado» no tenían dónde completarse.
 */
import { lazy, Suspense, useState, useEffect } from 'react'
import type { ComponentType } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AtSign, Bell, CheckCircle, Inbox, Workflow } from 'lucide-react'
import { Page, Tabs, Spinner } from '../components/ui'
import useNotificationBadges from '../hooks/useNotificationBadges'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import './InboxPage.css'

const NotificationsPage = lazy(() => import('./NotificationsPage'))
const MentionsPage = lazy(() => import('./MentionsPage'))
const ApprovalsPage = lazy(() => import('./ApprovalsPage'))
const BpmInbox = lazy(() => import('./bpm/BpmRunPanel').then(m => ({ default: m.BpmInbox })))

const NotificationsEmbedded = NotificationsPage as ComponentType<{ embedded?: boolean }>
const MentionsEmbedded = MentionsPage as ComponentType<{ embedded?: boolean }>
const ApprovalsEmbedded = ApprovalsPage as ComponentType<{ embedded?: boolean }>

const Loading = () => (
  <div className="inbox-row">
    <Spinner />
  </div>
)

const VALID_TABS = new Set(['notifications', 'mentions', 'approvals', 'processes'])

type InboxTab = 'notifications' | 'mentions' | 'approvals' | 'processes'

export default function InboxPage(): JSX.Element {
  const t = useAppT()
  const { hasRole } = useAuth()
  // Los pasos BPM son de usuarios internos (la API exige `require_internal_user`).
  const veProcesos = hasRole('admin', 'pm', 'team_lead', 'hr', 'employee')
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
    { id: 'notifications', label: t('inbox.tab_notifications'), icon: <Bell size={14} />, count: (alertCount + notifUnreadCount) || undefined },
    { id: 'mentions',      label: t('inbox.tab_mentions'),      icon: <AtSign size={14} />, count: mentionCount || undefined },
    { id: 'approvals',     label: t('inbox.tab_approvals'),     icon: <CheckCircle size={14} />, count: approvalCount || undefined },
    ...(veProcesos ? [{ id: 'processes', label: t('inbox.tab_processes'), icon: <Workflow size={14} /> }] : []),
  ]

  return (
    <Page icon={<Inbox size={18} />} title={t('nav.inbox')} subtitle={t('inbox.subtitle')}>
      <Tabs
        items={items}
        active={tab}
        onChange={(value) => setTab(value as InboxTab)}
        ariaLabel={t('nav.inbox')}
      />
      <Suspense fallback={<Loading />}>
        {tab === 'notifications' && <NotificationsEmbedded embedded />}
        {tab === 'mentions'      && <MentionsEmbedded embedded />}
        {tab === 'approvals'     && <ApprovalsEmbedded embedded />}
        {tab === 'processes'     && veProcesos && <BpmInbox />}
      </Suspense>
    </Page>
  )
}
