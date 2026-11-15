/**
 * NotificationsPage — Bandeja de entrada de notificaciones
 * Lista cronológica, marcar como leído, filtrar por tipo, WebSocket badge en tiempo real
 */
import { useAppLang } from '../i18n/AppLangContext'
import { type CSSProperties, useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { alertsApi, apiWsUrl } from '../services/api'
import type { Alerta } from '../services/api/tipos-documentos'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bell } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { DEFAULT_PAGE_SIZE, POLL_DEFAULT_MS, WS_PING_INTERVAL_MS } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import './NotificationsPage.css'

type NotificationType = string

type NotificationItem = {
  id: string | number
  _alertId?: string | number
  _isAlert?: boolean
  type?: NotificationType
  title?: string
  body?: string
  is_read?: boolean
  created_at?: string
}

type AlertItem = Alerta

type NotificationsResponse = {
  notifications: NotificationItem[]
  unread_count: number
}

type FilterType = 'all' | 'unread' | 'read'

type TypeCfg = {
  icon: string
  color: string
  label: string
}

const ALERT_TYPE_CFG: Record<string, TypeCfg> = {
  budget_overrun:     { icon:'💰', color:'var(--danger)',  label:'pagina_notif.presupuesto_excedido' },
  overdue_tasks:      { icon:'⏰', color:'var(--danger)',  label:'pagina_notif.tareas_vencidas' },
  capacity_risk:      { icon:'⚡', color:'var(--warning)', label:'pagina_notif.riesgo_de_capacidad' },
  sla_breach:         { icon:'🚨', color:'var(--danger)',  label:'pagina_notif.sla_incumplido' },
  sla_risk:           { icon:'⚠',  color:'var(--warning)', label:'pagina_notif.riesgo_sla' },
  low_margin:         { icon:'📉', color:'var(--warning)', label:'pagina_notif.margen_bajo' },
  overbudget:         { icon:'💸', color:'var(--danger)',  label:'pagina_notif.fuera_de_presupuesto' },
  high_utilization:   { icon:'🔥', color:'var(--warning)', label:'pagina_notif.utilizacion_alta' },
  stalled_project:    { icon:'🛑', color:'var(--warning)', label:'pagina_notif.proyecto_parado' },
}

const TYPE_CFG_NOTIF: Record<string, TypeCfg> = {
  task_assigned:       { icon:'▦',  color:'var(--success)',  label:'pagina_notif.tarea_asignada' },
  task_mentioned:      { icon:'@',  color:'var(--accent)',   label:'pagina_notif.mencion' },
  task_due_soon:       { icon:'⏰', color:'var(--warning)',  label:'pagina_notif.vence_pronto' },
  task_overdue:        { icon:'⚠',  color:'var(--danger)',   label:'pagina_notif.vencida' },
  sprint_started:      { icon:'🔄', color:'var(--accent)',   label:'pagina_notif.sprint_iniciado' },
  sprint_ending:       { icon:'🏁', color:'var(--warning)',  label:'pagina_notif.sprint_termina' },
  expense_approved:    { icon:'✅', color:'var(--success)',  label:'pagina_notif.gasto_aprobado' },
  expense_rejected:    { icon:'✗',  color:'var(--danger)',   label:'pagina_notif.gasto_rechazado' },
  ticket_assigned:     { icon:'🎫', color:'var(--purple)',   label:'pagina_notif.ticket_asignado' },
  ticket_replied:      { icon:'💬', color:'var(--accent)',   label:'pagina_notif.respuesta_ticket' },
  ticket_resolved:     { icon:'✓',  color:'var(--success)',  label:'pagina_notif.ticket_resuelto' },
  approval_requested:  { icon:'⏳', color:'var(--warning)',  label:'pagina_notif.aprobacion_pendiente' },
  approval_done:       { icon:'✅', color:'var(--success)',  label:'pagina_notif.aprobacion_completada' },
  mention:             { icon:'@',  color:'var(--accent)',   label:'pagina_notif.mencion' },
  budget_alert:        { icon:'💰', color:'var(--danger)',   label:'pagina_notif.alerta_presupuesto' },
  risk_escalated:      { icon:'🛡', color:'var(--danger)',   label:'pagina_notif.riesgo_escalado' },
  contract_expiring:   { icon:'📄', color:'var(--warning)',  label:'pagina_notif.contrato_por_vencer' },
}

function NotifItem({ notif, onMarkRead }: { notif: NotificationItem; onMarkRead: (id: string | number) => void }) {
  const { t } = useAppLang()
  const baseCfg = notif._isAlert
    ? (ALERT_TYPE_CFG[notif.type || ''] || { icon:'🔔', color:'var(--danger)', label: 'pagina_notif.alerta' })
    : (TYPE_CFG_NOTIF[notif.type || ''] || { icon:'🔔', color:'var(--text-2)', label: 'pagina_notif.notificacion' })
  const cfg = baseCfg
  const isUnread = !notif.is_read

  if (isUnread) {
    return (
      <button type="button" onClick={() => onMarkRead(notif.id)}
        className="notif-btn notifica-sx1 notifications-page-e1" style={{ '--notifications-page-border': `1px solid ${alpha(cfg.color, '25')}` } as CSSProperties}
        onMouseEnter={e => { e.currentTarget.style.borderColor = alpha(cfg.color, '50') }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = alpha(cfg.color, '25') }}>
        <div className="notif-box notifications-page-e2" style={{ '--notifications-page-background': cfg.color } as CSSProperties} />
        <div className="notif-row notifica-sx1 notifications-page-e3" style={{ '--notifications-page-background': alpha(cfg.color, '20'), '--notifications-page-border': `1px solid ${alpha(cfg.color, '30')}` } as CSSProperties}>
          {cfg.icon}
        </div>
        <div className="u-flex1-min0">
          <div className="notif-row-2">
            <div className="notif-box-2">
              {notif.title}
            </div>
          </div>
          <div className="notif-box-3">{t(cfg.label)}</div>
          {notif.body && <div className="notif-box-4">{notif.body}</div>}
          <div className="notif-box-5">{notif.created_at?.replace('T', ' ').slice(0, 16)}</div>
        </div>
      </button>
    )
  }

  return (
    <div
      className={`notif-row-3 notifica-sx1 ${isUnread ? 'notifica-sx2' : 'notifica-sx3'} notifications-page-e1`} style={{ '--notifications-page-border': `1px solid ${isUnread ? alpha(cfg.color, '25') : 'transparent'}` } as CSSProperties}
      >
      {/* Badge indicador de no leído */}
      <div className="notif-box-6 notifications-page-e2" style={{ '--notifications-page-background': isUnread ? cfg.color : 'transparent' } as CSSProperties} />
      {/* Icono tipo */}
      <div className="notif-row notifica-sx1 notifications-page-e3" style={{ '--notifications-page-background': alpha(cfg.color, '20'), '--notifications-page-border': `1px solid ${alpha(cfg.color, '30')}` } as CSSProperties}>
        {cfg.icon}
      </div>
      {/* Contenido */}
      <div className="u-flex1-min0">
        <div className="notif-row-2">
          <div className={`notif-box-7 ${isUnread ? 'notifica-sx4' : 'notifica-sx5'}`}>{notif.title}</div>
          <div className="notif-box-8">
            {notif.created_at?.slice(0,16).replace('T',' ') || ''}
          </div>
        </div>
        {notif.body && (
          <div className="notif-box-9">
            {notif.body}
          </div>
        )}
        <div className="notif-box-10 notifications-page-e4" style={{ '--notifications-page-color': cfg.color } as CSSProperties}>
          {t(cfg.label)}
        </div>
      </div>
    </div>
  )
}

function GroupedNotifList({ notifications, onMarkRead }: { notifications: NotificationItem[]; onMarkRead: (id: string | number) => void }) {
  const { t } = useAppLang()
  const groups = notifications.reduce((acc: Record<string, NotificationItem[]>, n) => {
    const key = (n._isAlert ? 'alert_' : '') + (n.type || 'other')
    if (!acc[key]) acc[key] = []
    acc[key].push(n)
    return acc
  }, {})

  const sortedGroups = Object.entries(groups).sort(([, a], [, b]) => {
    const unreadA = a.filter(n => !n.is_read).length
    const unreadB = b.filter(n => !n.is_read).length
    return unreadB - unreadA
  })

  return (
    <div data-export-table="notifications-list">
      {sortedGroups.map(([type, notifs]) => {
        const isAlertGroup = type.startsWith('alert_')
        const baseKey = isAlertGroup ? type.replace('alert_', '') : type
        const cfg = isAlertGroup
          ? (ALERT_TYPE_CFG[baseKey] || { icon: '🔔', color: 'var(--danger)', label: 'pagina_notif.alerta' })
          : (TYPE_CFG_NOTIF[baseKey] || { icon: '🔔', color: 'var(--text-2)', label: 'pagina_notif.notificacion' })
        const unread = notifs.filter(n => !n.is_read).length
        return (
          <div key={type} className="u-mb-20">
            <div className="notif-row-4">
              <span className="notif-label">{cfg.icon}</span>
              <span className="notif-label-2">{t(cfg.label)}</span>
              {unread > 0 && (
                <span className="notif-label-3 notifications-page-e2" style={{ '--notifications-page-background': cfg.color } as CSSProperties}>{unread}</span>
              )}
              <div className="notif-box-11" />
            </div>
            {notifs.map(n => (
              <NotifItem key={n.id} notif={n} onMarkRead={onMarkRead} />
            ))}
          </div>
        )
      })}
    </div>
  )
}

export default function NotificationsPage() {
  const t = useAppT()
  const { user, hasRole } = useAuth()
  const toast = useToast()
  const toastRef = useRef(toast)
  const qc = useQueryClient()
  const [filter, setFilter] = useState<FilterType>('all')
  const wsRef = useRef<WebSocket | null>(null)
  const lastWsNotifRef = useRef<{ count: number | null; firstId: string | number | null }>({ count: null, firstId: null })
  const [wsConnected, setWsConnected] = useState(false)

  useEffect(() => {
    toastRef.current = toast
  }, [toast])

  const { data, isLoading } = useQuery<NotificationsResponse>({
    queryKey: ['notifications-page', filter],
    queryFn: () => api.get('/enterprise/notifications', {
      params: { page_size: DEFAULT_PAGE_SIZE, ...(filter !== 'all' && { is_read: filter === 'read' }) }
    }).then(r => r.data).catch(() => ({ notifications:[], unread_count:0 })),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { data: alertsRaw = [], isLoading: alertsLoading } = useQuery({
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data).catch((): AlertItem[] => []),
    refetchInterval: POLL_DEFAULT_MS,
    enabled: hasRole('admin', 'pm', 'hr'),
  })

  // Normalize alerts to notification shape for unified display
  const alertsAsNotifs: NotificationItem[] = alertsRaw.map((a: AlertItem) => ({
    id: 'alert_' + a.id,
    _alertId: a.id,
    _isAlert: true,
    type: a.alert_type,
    title: a.title,
    body: a.description,
    is_read: a.is_read,
    created_at: a.created_at,
  }))

  const notifications = data?.notifications || []
  const allNotifications = [...notifications, ...alertsAsNotifs]
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))

  const unreadCount = (data?.unread_count || 0) + alertsRaw.filter((a: AlertItem) => !a.is_read).length

  const { mutate: markRead } = useMutation({
    mutationFn: (id: string | number) => api.post(`/enterprise/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications-page'] }),
  })
  const { mutate: markAll } = useMutation({
    mutationFn: () => api.post('/enterprise/notifications/read-all'),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notifications-page'] }); qc.invalidateQueries({ queryKey: ['alerts-count'] }); toast.success(t('pagina_notif.todas_marcadas_como_leidas')) },
  })

  const handleMarkRead = (id: string | number) => {
    if (String(id).startsWith('alert_')) {
      const alertId = String(id).replace('alert_', '')
      alertsApi.read(alertId).then(() => qc.invalidateQueries({ queryKey: ['alerts-count'] }))
    } else {
      markRead(id)
    }
  }

  // Conectar WebSocket usando one-shot ticket (httpOnly-cookie safe)
  useEffect(() => {
    if (!user) return
    let cancelled = false
    let shouldCloseOnOpen = false
    let ws: WebSocket | null = null
    let ping: ReturnType<typeof setInterval> | null = null
    api.get('/ws/ticket').then(r => {
      if (cancelled) return
      const ticket = r.data?.ticket
      if (!ticket) return
      const wsUrl = apiWsUrl(`/ws/notifications?ticket=${ticket}`)
      const socket = new WebSocket(wsUrl)
      ws = socket
      wsRef.current = socket
      socket.onopen = () => {
        if (shouldCloseOnOpen) {
          socket.close()
          return
        }
        if (!cancelled) setWsConnected(true)
      }
      ws.onclose = () => {
        if (!cancelled) setWsConnected(false)
      }
      ws.onerror = () => {
        if (!cancelled) setWsConnected(false)
      }
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(ev.data) as { type?: string; items?: Array<{ id?: string | number }>; count?: number }
          if (msg.type === 'notifications') {
            const firstId = msg.items?.[0]?.id || null
            const changed =
              lastWsNotifRef.current.count !== msg.count ||
              lastWsNotifRef.current.firstId !== firstId
            if (!changed) return
            lastWsNotifRef.current = { count: msg.count ?? null, firstId }

            if (!((msg.count ?? 0) > 0 || firstId)) return
            qc.invalidateQueries({ queryKey: ['notifications-page'] })
            qc.invalidateQueries({ queryKey: ['notifications'] })
            toastRef.current?.info?.(t((msg.count ?? 0) > 1 ? 'pagina_notif.nuevas_otros' : 'pagina_notif.nuevas_uno', { n: msg.count ?? 0 }))
          }
        } catch { /* noop */ }
      }
      ping = setInterval(() => socket.readyState === 1 && socket.send(JSON.stringify({ type:'ping' })), WS_PING_INTERVAL_MS)
    }).catch(() => { /* WS optional; polling fallback already active */ })
    return () => {
      cancelled = true
      if (ping) clearInterval(ping)
      if (ws) {
        ws.onmessage = null
        ws.onerror = null
        ws.onclose = null
        if (ws.readyState === WebSocket.OPEN) {
          ws.close()
        } else if (ws.readyState === WebSocket.CONNECTING) {
          // Avoid browser warning "WebSocket is closed before the connection is established"
          shouldCloseOnOpen = true
        }
      }
    }
  }, [user, qc, t])

  const FILTERS = [
    { id:'all',    label:t('pagina_notif.todas') },
    { id:'unread', label:`${t('pagina_notif.sin_leer')}${unreadCount > 0 ? ` (${unreadCount})` : ''}` },
    { id:'read',   label:t('pagina_notif.leidas') },
  ] as Array<{ id: FilterType; label: string }>

  const filtered = filter === 'unread'
    ? allNotifications.filter(n => !n.is_read)
    : filter === 'read'
    ? allNotifications.filter(n => n.is_read)
    : allNotifications

  return (
    <PageShell>
      <PageHeader
        icon={<Bell size={18} />}
        title={t('notifications.title')}
        subtitle={t('notifications.subtitle')}
        actions={
          <div className="u-row-center-8">
            <div className={`notif-row-5 ${wsConnected ? 'notifica-sx6' : 'notifica-sx7'}`}>
              <div className={`notif-box-12 ${wsConnected ? 'notifica-sx8' : 'notifica-sx9'}`} />
              {wsConnected ? t('pagina_notif.tiempo_real_activo') : t('pagina_notif.desconectado')}
            </div>
            {unreadCount > 0 && (
              <Button variant="secondary" onClick={() => markAll()}>
                {t('notifications.mark_all_read')}
              </Button>
            )}
          </div>
        }
        showListExport={filtered.length > 0}
        exportTargetSelector='[data-export-table="notifications-list"]'
        exportFilePrefix='notifications'
      />

      {/* KPI row */}
      <div className="notif-grid">
        {[
          { label:t('pagina_notif.sin_leer'), value:unreadCount, color: unreadCount > 0 ? 'var(--warning)' : 'var(--text-3)' },
          { label:t('pagina_notif.total_hoy'), value:allNotifications.filter(n => n.created_at?.startsWith(new Date().toISOString().slice(0,10))).length, color:'var(--accent)' },
          { label:t('pagina_notif.total_recientes'), value:allNotifications.length, color:'var(--text-2)' },
        ].map(kpi => (
          <div key={kpi.label} className="notif-card">
            <div className="notif-box-13 notifications-page-e4" style={{ '--notifications-page-color': kpi.color } as CSSProperties}>{kpi.value}</div>
            <div className="u-text2-sm-mt2">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div className="notif-row-6">
        {FILTERS.map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={`notif-btn-2 notifica-sx10 ${filter===f.id ? 'notifica-sx11' : 'notifica-sx12'} notifications-page-e1`} style={{ '--notifications-page-border': `1px solid ${filter===f.id?'var(--accent-border-strong)':'var(--surface-4)'}` } as CSSProperties}>
            {f.label}
          </button>
        ))}
      </div>

      {(isLoading && alertsLoading) ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🔔" title={t('notifications.sin_notificaciones')}
          description={filter === 'unread' ? t('pagina_notif.todo_al_dia_no_tienes_notificaciones') : t('pagina_notif.sin_notificaciones_en_este_filtro')} />
      ) : (
        <GroupedNotifList notifications={filtered} onMarkRead={handleMarkRead} />
      )}
    </PageShell>
  )
}
