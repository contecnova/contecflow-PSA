/**
 * NotificationsPage — Bandeja de entrada de notificaciones
 * Lista cronológica, marcar como leído, filtrar por tipo, WebSocket badge en tiempo real
 */
import { useAppLang } from '../i18n/AppLangContext'
import { type CSSProperties, useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { alertsApi } from '../services/api'
import type { Alerta } from '../services/api/tipos-documentos'
import { Button, Spinner, EmptyState, KpiCard, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bell, Check } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { DEFAULT_PAGE_SIZE, POLL_DEFAULT_MS } from '../constants/timings'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import useAvisosEnVivo, { type MensajeDeAvisos } from '../hooks/useAvisosEnVivo'
import { COLOR_DE_TONO, estiloDeAviso, sinEmojis } from '../components/avisos/iconosDeAviso'
import { refrescarAvisos } from '../components/layout/CampanaDeAvisos'
import { avisosApi } from '../services/api/avisos'
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

/** Etiqueta (clave) de cada tipo. El icono y el color salen de
 *  `iconosDeAviso` (lucide, por tipo): 16-11-2026, antes eran emojis. */
const ALERT_LABEL: Record<string, string> = {
  budget_overrun:   'pagina_notif.presupuesto_excedido',
  overdue_tasks:    'pagina_notif.tareas_vencidas',
  capacity_risk:    'pagina_notif.riesgo_de_capacidad',
  sla_breach:       'pagina_notif.sla_incumplido',
  sla_risk:         'pagina_notif.riesgo_sla',
  low_margin:       'pagina_notif.margen_bajo',
  overbudget:       'pagina_notif.fuera_de_presupuesto',
  high_utilization: 'pagina_notif.utilizacion_alta',
  stalled_project:  'pagina_notif.proyecto_parado',
}

const NOTIF_LABEL: Record<string, string> = {
  task_assigned:      'pagina_notif.tarea_asignada',
  task_mentioned:     'pagina_notif.mencion',
  task_due_soon:      'pagina_notif.vence_pronto',
  task_overdue:       'pagina_notif.vencida',
  sprint_started:     'pagina_notif.sprint_iniciado',
  sprint_ending:      'pagina_notif.sprint_termina',
  expense_approved:   'pagina_notif.gasto_aprobado',
  expense_rejected:   'pagina_notif.gasto_rechazado',
  ticket_assigned:    'pagina_notif.ticket_asignado',
  ticket_replied:     'pagina_notif.respuesta_ticket',
  ticket_resolved:    'pagina_notif.ticket_resuelto',
  approval_requested: 'pagina_notif.aprobacion_pendiente',
  approval_done:      'pagina_notif.aprobacion_completada',
  mention:            'pagina_notif.mencion',
  budget_alert:       'pagina_notif.alerta_presupuesto',
  risk_escalated:     'pagina_notif.riesgo_escalado',
  contract_expiring:  'pagina_notif.contrato_por_vencer',
}

/** Icono, color y etiqueta de un aviso o de una alerta. */
function configDe(type: string | undefined, isAlert: boolean) {
  const { Icono, tono } = estiloDeAviso(type, isAlert)
  const label = isAlert
    ? (ALERT_LABEL[type || ''] || 'pagina_notif.alerta')
    : (NOTIF_LABEL[type || ''] || 'pagina_notif.notificacion')
  return { Icono, color: COLOR_DE_TONO[tono], label }
}

function NotifItem({ notif, onMarkRead }: { notif: NotificationItem; onMarkRead: (id: string | number) => void }) {
  const { t } = useAppLang()
  const cfg = configDe(notif.type, !!notif._isAlert)
  const Icono = cfg.Icono
  const titulo = sinEmojis(notif.title)
  const isUnread = !notif.is_read

  if (isUnread) {
    return (
      <button type="button" onClick={() => onMarkRead(notif.id)}
        className="notif-btn notifica-sx1 notifications-page-e1" style={{ '--notifications-page-border': `1px solid ${alpha(cfg.color, '25')}` } as CSSProperties}
        onMouseEnter={e => { e.currentTarget.style.borderColor = alpha(cfg.color, '50') }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = alpha(cfg.color, '25') }}>
        <div className="notif-box notifications-page-e2" style={{ '--notifications-page-background': cfg.color } as CSSProperties} />
        <div className="notif-row notifica-sx1 notifications-page-e3 notifications-page-e4" aria-hidden style={{ '--notifications-page-background': alpha(cfg.color, '20'), '--notifications-page-border': `1px solid ${alpha(cfg.color, '30')}`, '--notifications-page-color': cfg.color } as CSSProperties}>
          <Icono size={16} />
        </div>
        <div className="u-flex1-min0">
          <div className="notif-row-2">
            <div className="notif-box-2">
              {titulo}
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
      <div className="notif-row notifica-sx1 notifications-page-e3 notifications-page-e4" aria-hidden style={{ '--notifications-page-background': alpha(cfg.color, '20'), '--notifications-page-border': `1px solid ${alpha(cfg.color, '30')}`, '--notifications-page-color': cfg.color } as CSSProperties}>
        <Icono size={16} />
      </div>
      {/* Contenido */}
      <div className="u-flex1-min0">
        <div className="notif-row-2">
          <div className={`notif-box-7 ${isUnread ? 'notifica-sx4' : 'notifica-sx5'}`}>{titulo}</div>
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
        const cfg = configDe(baseKey, isAlertGroup)
        const Icono = cfg.Icono
        const unread = notifs.filter(n => !n.is_read).length
        return (
          <div key={type} className="u-mb-20">
            <div className="notif-row-4">
              <span className="notif-label notifications-page-e4" aria-hidden style={{ '--notifications-page-color': cfg.color } as CSSProperties}><Icono size={14} /></span>
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

/** `embedded`: dentro de la Bandeja de entrada (/inbox), que ya pinta la cabecera de página. */
export default function NotificationsPage({ embedded = false }: { embedded?: boolean } = {}) {
  const t = useAppT()
  const { user, hasRole } = useAuth()
  const toast = useToast()
  const toastRef = useRef(toast)
  const qc = useQueryClient()
  const [filter, setFilter] = useState<FilterType>('all')
  const lastWsNotifRef = useRef<{ count: number | null; firstId: string | number | null }>({ count: null, firstId: null })

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
    // La campana y la pestaña cuentan lo mismo: se refrescan con la bandeja.
    onSuccess: () => refrescarAvisos(qc),
  })
  const { mutate: markAll } = useMutation({
    // «Sin leer» suma avisos y alertas: marcar todas marca las dos cosas.
    mutationFn: () => avisosApi.marcarTodoLeido(alertsRaw),
    onSuccess: () => { refrescarAvisos(qc); toast.success(t('pagina_notif.todas_marcadas_como_leidas')) },
  })

  const handleMarkRead = (id: string | number) => {
    if (String(id).startsWith('alert_')) {
      const alertId = String(id).replace('alert_', '')
      alertsApi.read(alertId).then(() => refrescarAvisos(qc))
    } else {
      markRead(id)
    }
  }

  // Tiempo real (16-11-2026): el WebSocket de avisos es uno por pestaña y lo
  // comparte con la campana de la barra superior (`useAvisosEnVivo`).
  const alRecibir = useCallback((msg: MensajeDeAvisos) => {
    if (msg.type !== 'notifications') return
    const firstId = msg.items?.[0]?.id || null
    const changed =
      lastWsNotifRef.current.count !== msg.count ||
      lastWsNotifRef.current.firstId !== firstId
    if (!changed) return
    lastWsNotifRef.current = { count: msg.count ?? null, firstId }
    refrescarAvisos(qc)
    if (!((msg.count ?? 0) > 0 || firstId)) return
    toastRef.current?.info?.(t((msg.count ?? 0) > 1 ? 'pagina_notif.nuevas_otros' : 'pagina_notif.nuevas_uno', { n: msg.count ?? 0 }))
  }, [qc, t])
  const wsConnected = useAvisosEnVivo(!!user, alRecibir)

  const FILTERS = [
    { id:'all',    label:t('pagina_notif.todas') },
    { id:'unread', label:t('pagina_notif.sin_leer'), count: unreadCount > 0 ? unreadCount : undefined },
    { id:'read',   label:t('pagina_notif.leidas') },
  ] as Array<{ id: FilterType; label: string; count?: number }>

  const filtered = filter === 'unread'
    ? allNotifications.filter(n => !n.is_read)
    : filter === 'read'
    ? allNotifications.filter(n => n.is_read)
    : allNotifications

  const acciones = (
          <div className="u-row-center-8">
            <div className={`notif-row-5 ${wsConnected ? 'notifica-sx6' : 'notifica-sx7'}`}>
              <div className={`notif-box-12 ${wsConnected ? 'notifica-sx8' : 'notifica-sx9'}`} />
              {wsConnected ? t('pagina_notif.tiempo_real_activo') : t('pagina_notif.desconectado')}
            </div>
            {unreadCount > 0 && (
              <Button variant="secondary" icon={<Check size={14} aria-hidden />} onClick={() => markAll()}>
                {t('notifications.mark_all_read')}
              </Button>
            )}
          </div>
  )

  // 16-11-2026 (pasada de diseño): incrustada en /inbox no pinta una segunda
  // cabecera de página; sus acciones van en una barra sobre el contenido.
  const contenido = (
    <>
      {/* Cifras (KpiCard del kit, 16-11-2026) */}
      <div className="ds-grid-stats">
        <KpiCard label={t('pagina_notif.sin_leer')} value={unreadCount} warning={unreadCount > 0} />
        <KpiCard label={t('pagina_notif.total_hoy')} value={allNotifications.filter(n => n.created_at?.startsWith(new Date().toISOString().slice(0,10))).length} accent />
        <KpiCard label={t('pagina_notif.total_recientes')} value={allNotifications.length} />
      </div>

      {/* Filtros (Tabs del kit) */}
      <Tabs items={FILTERS} active={filter} onChange={id => setFilter(id as FilterType)} ariaLabel={t('notifications.title')} />

      {(isLoading && alertsLoading) ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState icon={<Bell size={28} strokeWidth={1.5} aria-hidden />} title={t('notifications.sin_notificaciones')}
          description={filter === 'unread' ? t('pagina_notif.todo_al_dia_no_tienes_notificaciones') : t('pagina_notif.sin_notificaciones_en_este_filtro')} />
      ) : (
        <GroupedNotifList notifications={filtered} onMarkRead={handleMarkRead} />
      )}
    </>
  )

  if (embedded) {
    return (
      <div className="ds-stack">
        <div className="ds-toolbar"><span className="ds-toolbar__spacer" />{acciones}</div>
        {contenido}
      </div>
    )
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Bell size={18} />}
        title={t('notifications.title')}
        subtitle={t('notifications.subtitle')}
        actions={acciones}
        showListExport={filtered.length > 0}
        exportTargetSelector='[data-export-table="notifications-list"]'
        exportFilePrefix='notifications'
      />
      {contenido}
    </PageShell>
  )
}
