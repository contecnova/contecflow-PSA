/**
 * NotificationsPage — Bandeja de entrada de notificaciones
 * Lista cronológica, marcar como leído, filtrar por tipo, WebSocket badge en tiempo real
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bell } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'

const TYPE_CFG = {
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

function NotifItem({ notif, onMarkRead }) {
  const cfg = TYPE_CFG[notif.type] || { icon:'🔔', color:'var(--text-2)', label:'Notificación' }
  const isUnread = !notif.is_read

  if (isUnread) {
    return (
      <button type="button" onClick={() => onMarkRead(notif.id)}
        style={{ display:'flex', gap:12, padding:'12px 16px',
          background: 'var(--surface-2)',
          border:`1px solid ${cfg.color + '25'}`,
          borderRadius:10, cursor:'pointer',
          transition:'all .15s', marginBottom:4, width:'100%', textAlign:'left', fontFamily:'inherit' }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = cfg.color + '50' }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = cfg.color + '25' }}>
        <div style={{ width:8, height:8, borderRadius:'50%',
          background: cfg.color,
          flexShrink:0, marginTop:8, alignSelf:'flex-start' }} />
        <div style={{ width:36, height:36, borderRadius:10, flexShrink:0,
          background:`${cfg.color}20`, border:`1px solid ${cfg.color}30`,
          display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--text-lg)" }}>
          {cfg.icon}
        </div>
        <div style={{ flex:1, minWidth:0 }}>
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
        border:`1px solid ${isUnread ? cfg.color + '25' : 'transparent'}`,
        borderRadius:10, cursor: isUnread ? 'pointer' : 'default',
        transition:'all .15s', marginBottom:4 }}
      >
      {/* Badge indicador de no leído */}
      <div style={{ width:8, height:8, borderRadius:'50',
        background: isUnread ? cfg.color : 'transparent',
        flexShrink:0, marginTop:8, alignSelf:'flex-start' }} />
      {/* Icono tipo */}
      <div style={{ width:36, height:36, borderRadius:10, flexShrink:0,
        background:`${cfg.color}20`, border:`1px solid ${cfg.color}30`,
        display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--text-lg)" }}>
        {cfg.icon}
      </div>
      {/* Contenido */}
      <div style={{ flex:1, minWidth:0 }}>
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

function GroupedNotifList({ notifications, onMarkRead }) {
  const groups = notifications.reduce((acc, n) => {
    const key = n.type || 'other'
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
    <div>
      {sortedGroups.map(([type, notifs]) => {
        const cfg = TYPE_CFG[type] || { icon: '🔔', color: 'var(--text-2)', label: 'Notificación' }
        const unread = notifs.filter(n => !n.is_read).length
        return (
          <div key={type} style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, padding: '0 4px' }}>
              <span style={{ fontSize: "var(--text-md)" }}>{cfg.icon}</span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{cfg.label}</span>
              {unread > 0 && (
                <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, background: cfg.color, color: '#fff', borderRadius: 10, padding: '1px 7px', marginLeft: 2 }}>{unread}</span>
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
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [filter, setFilter] = useState('all')
  const wsRef = useRef(null)
  const [wsConnected, setWsConnected] = useState(false)

  const { data, isLoading, _refetch } = useQuery({
    queryKey: ['notifications-page', filter],
    queryFn: () => api.get('/enterprise/notifications', {
      params: { page_size: 50, ...(filter !== 'all' && { is_read: filter === 'read' }) }
    }).then(r => r.data).catch(() => ({ notifications:[], unread_count:0 })),
    refetchInterval: 60000,
  })

  const notifications = data?.notifications || []
  const unreadCount   = data?.unread_count || 0

  const { mutate: markRead } = useMutation({
    mutationFn: id => api.post(`/enterprise/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications-page'] }),
  })
  const { mutate: markAll } = useMutation({
    mutationFn: () => api.post('/enterprise/notifications/read-all'),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notifications-page'] }); toast.success('Todas marcadas como leídas') },
  })

  // Conectar WebSocket usando one-shot ticket (httpOnly-cookie safe)
  useEffect(() => {
    if (!user) return
    let cancelled = false
    let shouldCloseOnOpen = false
    let ws = null
    let ping = null
    api.get('/ws/ticket').then(r => {
      if (cancelled) return
      const ticket = r.data?.ticket
      if (!ticket) return
      const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const wsUrl = `${wsProto}://${window.location.host}/api/v1/ws/notifications?ticket=${ticket}`
      ws = new WebSocket(wsUrl)
      wsRef.current = ws
      ws.onopen = () => {
        if (shouldCloseOnOpen) {
          ws.close()
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
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'notifications' && msg.count > 0) {
            qc.invalidateQueries({ queryKey: ['notifications-page'] })
            qc.invalidateQueries({ queryKey: ['notifications'] })
            toast.info(`🔔 ${msg.count} notificación${msg.count > 1 ? 'es' : ''} nueva${msg.count > 1 ? 's' : ''}`)
          }
        } catch { /* noop */ }
      }
      ping = setInterval(() => ws.readyState === 1 && ws.send(JSON.stringify({ type:'ping' })), 30000)
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
  }, [user, qc, toast])

  const FILTERS = [
    { id:'all',    label:'Todas' },
    { id:'unread', label:`Sin leer${unreadCount > 0 ? ` (${unreadCount})` : ''}` },
    { id:'read',   label:'Leídas' },
  ]

  const filtered = filter === 'unread'
    ? notifications.filter(n => !n.is_read)
    : filter === 'read'
    ? notifications.filter(n => n.is_read)
    : notifications

  return (
    <PageShell>
      <PageHeader
        icon={<Bell size={18} />}
        title={t('notifications.title')}
        subtitle={t('notifications.subtitle')}
        actions={
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <div style={{ display:'flex', alignItems:'center', gap:5, fontSize: "var(--text-xs)",
              color: wsConnected ? 'var(--success)' : 'var(--text-3)' }}>
              <div style={{ width:6, height:6, borderRadius:'50%',
                background: wsConnected ? 'var(--success)' : 'var(--text-3)' }} />
              {wsConnected ? 'Tiempo real activo' : 'Desconectado'}
            </div>
            {unreadCount > 0 && (
              <Button variant="secondary" onClick={() => markAll()}>
                ✓ Marcar todas como leídas
              </Button>
            )}
          </div>
        }
      />

      {/* KPI row */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:24 }}>
        {[
          { label:'Sin leer', value:unreadCount, color: unreadCount > 0 ? 'var(--warning)' : 'var(--text-3)' },
          { label:'Total hoy', value:notifications.filter(n => n.created_at?.startsWith(new Date().toISOString().slice(0,10))).length, color:'var(--accent)' },
          { label:'Total recientes', value:notifications.length, color:'var(--text-2)' },
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

      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon="🔔" title="Sin notificaciones"
          description={filter === 'unread' ? 'Todo al día — no tienes notificaciones sin leer' : 'Sin notificaciones en este filtro'} />
      ) : (
        <GroupedNotifList notifications={filtered} onMarkRead={id => markRead(id)} />
      )}
    </PageShell>
  )
}
