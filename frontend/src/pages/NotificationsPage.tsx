/**
 * NotificationsPage — Bandeja de entrada de notificaciones
 * Lista cronológica, marcar como leído, filtrar por tipo, WebSocket badge en tiempo real
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { alertsApi, apiWsUrl } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bell } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { DEFAULT_PAGE_SIZE } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

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

type AlertItem = {
  id: string | number
  alert_type?: string
  title?: string
  description?: string
  is_read?: boolean
  created_at?: string | Date | { toISOString?: () => string }
}

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
  budget_overrun:     { icon:'💰', color:'var(--danger)',  label:'Presupuesto excedido' },
  overdue_tasks:      { icon:'⏰', color:'var(--danger)',  label:'Tareas vencidas' },
  capacity_risk:      { icon:'⚡', color:'var(--warning)', label:'Riesgo de capacidad' },
  sla_breach:         { icon:'🚨', color:'var(--danger)',  label:'SLA incumplido' },
  sla_risk:           { icon:'⚠',  color:'var(--warning)', label:'Riesgo SLA' },
  low_margin:         { icon:'📉', color:'var(--warning)', label:'Margen bajo' },
  overbudget:         { icon:'💸', color:'var(--danger)',  label:'Fuera de presupuesto' },
  high_utilization:   { icon:'🔥', color:'var(--warning)', label:'Utilización alta' },
  stalled_project:    { icon:'🛑', color:'var(--warning)', label:'Proyecto parado' },
}

const TYPE_CFG_NOTIF: Record<string, TypeCfg> = {
  task_assigned:       { icon:'▦',  color:'var(--success)',  label:'Tarea asignada' },
  task_mentioned:      { icon:'@',  color:'var(--accent)',   label:'Mención' },
  task_due_soon:       { icon:'⏰', color:'var(--warning)',  label:'Vence pronto' },
  task_overdue:        { icon:'⚠',  color:'var(--danger)',   label:'Vencida' },
  sprint_started:      { icon:'🔄', color:'var(--accent)',   label:'Sprint iniciado' },
  sprint_ending:       { icon:'🏁', color:'var(--warning)',  label:'Sprint termina' },
  expense_approved:    { icon:'✅', color:'var(--success)',  label:'Gasto aprobado' },
  expense_rejected:    { icon:'✗',  color:'var(--danger)',   label:'Gasto rechazado' },
  ticket_assigned:     { icon:'🎫', color:'var(--purple)',   label:'Ticket asignado' },
  ticket_replied:      { icon:'💬', color:'var(--accent)',   label:'Respuesta ticket' },
  ticket_resolved:     { icon:'✓',  color:'var(--success)',  label:'Ticket resuelto' },
  approval_requested:  { icon:'⏳', color:'var(--warning)',  label:'Aprobación pendiente' },
  approval_done:       { icon:'✅', color:'var(--success)',  label:'Aprobación completada' },
  mention:             { icon:'@',  color:'var(--accent)',   label:'Mención' },
  budget_alert:        { icon:'💰', color:'var(--danger)',   label:'Alerta presupuesto' },
  risk_escalated:      { icon:'🛡', color:'var(--danger)',   label:'Riesgo escalado' },
  contract_expiring:   { icon:'📄', color:'var(--warning)',  label:'Contrato por vencer' },
}

function NotifItem({ notif, onMarkRead }: { notif: NotificationItem; onMarkRead: (id: string | number) => void }) {
  const baseCfg = notif._isAlert
    ? (ALERT_TYPE_CFG[notif.type || ''] || { icon:'🔔', color:'var(--danger)', label:'Alerta' })
    : (TYPE_CFG_NOTIF[notif.type || ''] || { icon:'🔔', color:'var(--text-2)', label:'Notificación' })
  const cfg = baseCfg
  const isUnread = !notif.is_read

  if (isUnread) {
    return (
      <button type="button" onClick={() => onMarkRead(notif.id)}
        style={{ display:'flex', gap:12, padding:'12px 16px',
          background: 'var(--surface-2)',
          border:`1px solid ${alpha(cfg.color, '25')}`,
          borderRadius:10, cursor:'pointer',
          transition:'all .15s', marginBottom:4, width:'100%', textAlign:'left', fontFamily:'inherit' }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = alpha(cfg.color, '50') }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = alpha(cfg.color, '25') }}>
        <div style={{ width:8, height:8, borderRadius:'50%',
          background: cfg.color,
          flexShrink:0, marginTop:8, alignSelf:'flex-start' }} />
        <div style={{ width:36, height:36, borderRadius:10, flexShrink:0,
          background:alpha(cfg.color, '20'), border:`1px solid ${alpha(cfg.color, '30')}`,
          display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--text-lg)" }}>
          {cfg.icon}
        </div>
        <div className="u-flex1-min0">
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight:700,
              color:'var(--text-1)', lineHeight:1.4, overflow:'hidden', textOverflow:'ellipsis' }}>
              {notif.title}
            </div>
          </div>
          <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginTop:4 }}>{cfg.label}</div>
          {notif.body && <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginTop:6, lineHeight:1.45 }}>{notif.body}</div>}
          <div style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', marginTop:7 }}>{notif.created_at?.replace('T', ' ').slice(0, 16)}</div>
        </div>
      </button>
    )
  }

  return (
    <div
      style={{ display:'flex', gap:12, padding:'12px 16px',
        background: isUnread ? 'var(--surface-2)' : 'transparent',
        border:`1px solid ${isUnread ? alpha(cfg.color, '25') : 'transparent'}`,
        borderRadius:10, cursor: isUnread ? 'pointer' : 'default',
        transition:'all .15s', marginBottom:4 }}
      >
      {/* Badge indicador de no leído */}
      <div style={{ width:8, height:8, borderRadius:'50',
        background: isUnread ? cfg.color : 'transparent',
        flexShrink:0, marginTop:8, alignSelf:'flex-start' }} />
      {/* Icono tipo */}
      <div style={{ width:36, height:36, borderRadius:10, flexShrink:0,
        background:alpha(cfg.color, '20'), border:`1px solid ${alpha(cfg.color, '30')}`,
        display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--text-lg)" }}>
        {cfg.icon}
      </div>
      {/* Contenido */}
      <div className="u-flex1-min0">
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: isUnread ? 700 : 400,
            color:'var(--text-1)' }}>{notif.title}</div>
          <div style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', whiteSpace:'nowrap', flexShrink:0 }}>
            {notif.created_at?.slice(0,16).replace('T',' ') || ''}
          </div>
        </div>
        {notif.body && (
          <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginTop:2, lineHeight:1.4 }}>
            {notif.body}
          </div>
        )}
        <div style={{ fontSize: "var(--text-2xs)", color:cfg.color, marginTop:3, fontWeight:600 }}>
          {cfg.label}
        </div>
      </div>
    </div>
  )
}

function GroupedNotifList({ notifications, onMarkRead }: { notifications: NotificationItem[]; onMarkRead: (id: string | number) => void }) {
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
          ? (ALERT_TYPE_CFG[baseKey] || { icon: '🔔', color: 'var(--danger)', label: 'Alerta' })
          : (TYPE_CFG_NOTIF[baseKey] || { icon: '🔔', color: 'var(--text-2)', label: 'Notificación' })
        const unread = notifs.filter(n => !n.is_read).length
        return (
          <div key={type} className="u-mb-20">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, padding: '0 4px' }}>
              <span style={{ fontSize: "var(--text-md)" }}>{cfg.icon}</span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{cfg.label}</span>
              {unread > 0 && (
                <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, background: cfg.color, color: 'var(--on-accent-light)', borderRadius: 10, padding: '1px 7px', marginLeft: 2 }}>{unread}</span>
              )}
              <div style={{ flex: 1, height: 1, background: 'var(--surface-4)', marginLeft: 4 }} />
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
    refetchInterval: 60000,
  })

  const { data: alertsRaw = [], isLoading: alertsLoading } = useQuery<AlertItem[]>({
    queryKey: ['alerts-count'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => r.data?.items ?? r.data ?? []).catch(() => []),
    refetchInterval: 60000,
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
    created_at: typeof a.created_at === 'string' ? a.created_at : (a.created_at?.toISOString?.() || ''),
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notifications-page'] }); qc.invalidateQueries({ queryKey: ['alerts-count'] }); toast.success('Todas marcadas como leídas') },
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
            toastRef.current?.info?.(`🔔 ${msg.count ?? 0} notificación${(msg.count ?? 0) > 1 ? 'es' : ''} nueva${(msg.count ?? 0) > 1 ? 's' : ''}`)
          }
        } catch { /* noop */ }
      }
      ping = setInterval(() => socket.readyState === 1 && socket.send(JSON.stringify({ type:'ping' })), 30000)
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
  }, [user, qc])

  const FILTERS = [
    { id:'all',    label:'Todas' },
    { id:'unread', label:`Sin leer${unreadCount > 0 ? ` (${unreadCount})` : ''}` },
    { id:'read',   label:'Leídas' },
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
            <div style={{ display:'flex', alignItems:'center', gap:5, fontSize: "var(--text-xs)",
              color: wsConnected ? 'var(--success)' : 'var(--text-3)' }}>
              <div style={{ width:6, height:6, borderRadius:'50%',
                background: wsConnected ? 'var(--success)' : 'var(--text-3)' }} />
              {wsConnected ? 'Tiempo real activo' : 'Desconectado'}
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
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:24 }}>
        {[
          { label:'Sin leer', value:unreadCount, color: unreadCount > 0 ? 'var(--warning)' : 'var(--text-3)' },
          { label:'Total hoy', value:allNotifications.filter(n => n.created_at?.startsWith(new Date().toISOString().slice(0,10))).length, color:'var(--accent)' },
          { label:'Total recientes', value:allNotifications.length, color:'var(--text-2)' },
        ].map(kpi => (
          <div key={kpi.label} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:'14px 18px' }}>
            <div style={{ fontSize: "var(--text-2xl-em)", fontWeight:800, color:kpi.color,
              fontFamily: 'var(--font-mono)' }}>{kpi.value}</div>
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginTop:2 }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{ display:'flex', gap:6, marginBottom:20 }}>
        {FILTERS.map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            style={{ padding:'7px 14px', borderRadius:8, fontSize: "var(--text-sm)", fontWeight:600,
              border:`1px solid ${filter===f.id?'rgba(79,142,247,.4)':'var(--surface-4)'}`,
              background:filter===f.id?'var(--accent-muted)':'transparent',
              color:filter===f.id?'var(--accent)':'var(--text-2)',
              cursor:'pointer', fontFamily:'inherit' }}>
            {f.label}
          </button>
        ))}
      </div>

      {(isLoading && alertsLoading) ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🔔" title={t('notifications.sin_notificaciones')}
          description={filter === 'unread' ? 'Todo al día — no tienes notificaciones sin leer' : 'Sin notificaciones en este filtro'} />
      ) : (
        <GroupedNotifList notifications={filtered} onMarkRead={handleMarkRead} />
      )}
    </PageShell>
  )
}
