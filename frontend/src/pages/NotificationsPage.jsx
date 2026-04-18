/**
 * NotificationsPage — Bandeja de entrada de notificaciones
 * Lista cronológica, marcar como leído, filtrar por tipo, WebSocket badge en tiempo real
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
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

  return (
    <div onClick={() => !notif.is_read && onMarkRead(notif.id)}
      style={{ display:'flex', gap:12, padding:'12px 16px',
        background: isUnread ? 'var(--surface-2)' : 'transparent',
        border:`1px solid ${isUnread ? cfg.color + '25' : 'transparent'}`,
        borderRadius:10, cursor: isUnread ? 'pointer' : 'default',
        transition:'all .15s', marginBottom:4 }}
      onMouseEnter={e => { if(isUnread) e.currentTarget.style.borderColor = cfg.color + '50' }}
      onMouseLeave={e => { if(isUnread) e.currentTarget.style.borderColor = cfg.color + '25' }}>
      {/* Badge indicador de no leído */}
      <div style={{ width:8, height:8, borderRadius:'50',
        background: isUnread ? cfg.color : 'transparent',
        flexShrink:0, marginTop:8, alignSelf:'flex-start' }} />
      {/* Icono tipo */}
      <div style={{ width:36, height:36, borderRadius:10, flexShrink:0,
        background:`${cfg.color}20`, border:`1px solid ${cfg.color}30`,
        display:'flex', alignItems:'center', justifyContent:'center', fontSize:16 }}>
        {cfg.icon}
      </div>
      {/* Contenido */}
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8 }}>
          <div style={{ fontSize:13, fontWeight: isUnread ? 700 : 400,
            color:'var(--text-1)' }}>{notif.title}</div>
          <div style={{ fontSize:10, color:'var(--text-3)', whiteSpace:'nowrap', flexShrink:0 }}>
            {notif.created_at?.slice(0,16).replace('T',' ') || ''}
          </div>
        </div>
        {notif.body && (
          <div style={{ fontSize:12, color:'var(--text-2)', marginTop:2, lineHeight:1.4 }}>
            {notif.body}
          </div>
        )}
        <div style={{ fontSize:10, color:cfg.color, marginTop:3, fontWeight:600 }}>
          {cfg.label}
        </div>
      </div>
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
      ws.onopen = () => setWsConnected(true)
      ws.onclose = () => setWsConnected(false)
      ws.onerror = () => setWsConnected(false)
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
      if (ws) ws.close()
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
    <div style={{ padding:32 }}>
      <PageHeader
        title={t('notifications.title')}
        subtitle={t('notifications.subtitle')}
        actions={
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <div style={{ display:'flex', alignItems:'center', gap:5, fontSize:11,
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
          <div key={kpi.label} style={{ background:'var(--surface-2)', border:'1px solid #1e2d45',
            borderRadius:12, padding:'14px 18px' }}>
            <div style={{ fontSize:26, fontWeight:800, color:kpi.color,
              fontFamily:"'Space Mono',monospace" }}>{kpi.value}</div>
            <div style={{ fontSize:12, color:'var(--text-2)', marginTop:2 }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{ display:'flex', gap:6, marginBottom:20 }}>
        {FILTERS.map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            style={{ padding:'7px 14px', borderRadius:8, fontSize:12, fontWeight:600,
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
        <div>
          {filtered.map(n => (
            <NotifItem key={n.id} notif={n} onMarkRead={id => markRead(id)} />
          ))}
        </div>
      )}
    </div>
  )
}
