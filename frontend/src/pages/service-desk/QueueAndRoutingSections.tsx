/**
 * QueueAndRoutingSections — lista de tickets («Mi cola» y «Todos»), incidentes
 * mayores y reglas de enrutado (estas se ven en Configuración).
 *
 * 16-11-2026 (pasada de diseño): filtros en una barra con `ds-input` e icono de
 * búsqueda; tablas en tarjeta con la tabla común; vacíos con `EmptyState` e
 * icono lucide (eran emojis 🎫 ⚡ y, en incidentes mayores, una tabla vacía);
 * fechas con el formateador del idioma; «Declarar incidente mayor» es un
 * `Button` normal con icono (llevaba 🚨 y colores propios); severidad y estado
 * con `StatusBadge`; en las reglas, condiciones y acciones con su nombre y su
 * valor legibles (antes `ticket_type: incident`, `assign_group: <uuid>`) y las
 * etiquetas de acción corregidas («Asignar al grupo» salía como «Acción»).
 */
import { useEffect, useMemo, useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertOctagon, AlertTriangle, Pencil, Plus, Route, Search, Ticket, Trash2, X } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { sdRoutingApi, sdGroupsApi, sdSlaPoliciesApi, usersApi, ticketsApi } from '../../services/api'
import type { SdIncidenteMayor, SdReglaDeEnrutado, SdTicket } from '../../services/api/tipos-sd'
import type { AxiosResponse } from 'axios'
import { Button, IconButton, Pulsable, Select, TablaSimple, Spinner, EmptyState, Modal, useSort, SortableTH, ariaSort, useErroresDeCampo } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import Pagination from '../../components/ui/Pagination'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { PBadge, PRIORITY_LABEL, SBadge, etiquetaSd, fmtDate } from './sdUtils'
import { POLL_DEFAULT_MS, POLL_FREQUENT_MS, SEARCH_DEBOUNCE_MS, STALE_NEAR_LIVE_MS } from '../../constants/timings'
import './QueueAndRoutingSections.css'

// PBadge y SBadge vienen de sdUtils. Auditoría 2026-11: aquí había una copia
// local de los dos (y de sus mapas de color), y por eso la lista seguía
// pintando el estado como código cuando se tradujo el compartido.

type Ticket = SdTicket

// Etiqueta traducida de cada estado de ticket (las mismas claves que SBadge).
const TICKET_STATUS_KEY: Record<string, string> = {
  new: 'status_new', assigned: 'status_assigned', in_progress: 'status_in_progress',
  pending_client: 'status_waiting_client', pending_third: 'status_pending_third',
  resolved: 'status_resolved', closed: 'status_closed', cancelled: 'status_cancelled',
}

function TRow({ t: ticket, onClick }: { t: Ticket; onClick: () => void }) {
  const tr = useAppT()
  const now = new Date()
  const due = ticket.sla_resolution_due ? new Date(ticket.sla_resolution_due) : null
  const overdue = due && due < now && !['resolved', 'closed'].includes(ticket.status || '')
  return (
    <tr onClick={onClick} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }} aria-label={`${ticket.number} ${ticket.title}`}
      className="sdqr-row">
      <td className="sdqr-td--number">{ticket.number}</td>
      <td className="sdqr-td--title">
        <div className="sdqr-title">{ticket.title}</div>
        {ticket.requester_name && <div className="u-text3-xs">{ticket.requester_name}</div>}
      </td>
      <td><PBadge v={ticket.priority} /></td>
      <td><SBadge v={ticket.status} /></td>
      <td className="sdqr-td--muted">{ticket.type_label || etiquetaSd('type', ticket.ticket_type)}</td>
      <td className={overdue ? 'sdqr-td--muted sdqr-td--overdue' : 'sdqr-td--muted'}>
        {due ? (
          <span className="sdqr-due">
            {overdue && <AlertTriangle size={12} aria-label={tr('queueandrouting.sla_vencido')} />}
            {fmtDate(due)}
          </span>
        ) : '—'}
      </td>
      <td className="sdqr-td--muted">
        {ticket.assigned_to_name || <span className="sdqr-unassigned">{tr('service_desk.unassigned')}</span>}
      </td>
    </tr>
  )
}

const TICKETS_POR_PAGINA = 50

export function TicketList({ queueOnly, onSelect }: { queueOnly?: boolean; onSelect: (tk: Ticket) => void }) {
  const t = useAppT()
  const [search, setSearch] = useState('')
  const [filterPrio, setFilterPrio] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')
  // Auditoria 2026-11: «Mi cola» se quedaba en 25 y «Todos» en 100, y la
  // busqueda solo miraba esos 100. Ahora se pagina en el servidor y, en
  // «Todos», la busqueda va al servidor.
  const [page, setPage] = useState(1)
  const [busqueda, setBusqueda] = useState('')
  useEffect(() => {
    const espera = setTimeout(() => { setBusqueda(search.trim()); setPage(1) }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(espera)
  }, [search])
  useEffect(() => { setPage(1) }, [filterPrio, filterStatus, filterType])

  const { data: pagina, isLoading } = useQuery<{ items: Ticket[]; total: number }>({
    queryKey: ['sd-tickets', queueOnly, filterPrio, filterStatus, filterType, queueOnly ? '' : busqueda, page],
    queryFn: () => {
      // El interceptor deja la lista en `data` y la paginación en `meta`.
      const leer = (r: AxiosResponse<Ticket[]> & { meta?: { total?: number } }) =>
        ({ items: r.data, total: Number(r.meta?.total ?? r.data.length) })
      if (queueOnly) {
        return ticketsApi.myQueue({ page, page_size: TICKETS_POR_PAGINA }).then(leer)
      }
      return ticketsApi.list({
        priority: filterPrio || undefined,
        status: filterStatus || undefined,
        ticket_type: filterType || undefined,
        search: busqueda || undefined,
        page,
        page_size: TICKETS_POR_PAGINA,
      }).then(leer)
    },
    staleTime: STALE_NEAR_LIVE_MS,
    refetchInterval: POLL_DEFAULT_MS,
  })
  const tickets = useMemo(() => pagina?.items ?? [], [pagina])
  const total = pagina?.total ?? 0
  const paginas = Math.max(1, Math.ceil(total / TICKETS_POR_PAGINA))

  const filtered = useMemo(() => {
    const list = Array.isArray(tickets) ? tickets : []
    // «Todos» ya viene filtrado por el servidor; «Mi cola» no tiene busqueda en
    // la API y se filtra la pagina cargada.
    if (!search || !queueOnly) return list
    const q = search.toLowerCase()
    return list.filter(tk =>
      tk.title?.toLowerCase().includes(q) ||
      tk.number?.toLowerCase().includes(q) ||
      tk.requester_name?.toLowerCase().includes(q)
    )
  }, [tickets, search, queueOnly])

  const { sort: ticketSort, setSort: setTicketSort, sortedData: sortedTickets } = useSort(filtered, 'number')
  const hayFiltro = !!(search.trim() || filterPrio || filterStatus || filterType)

  return (
    <div>
      <div className="ds-toolbar sdqr-filters">
        <div className="sdqr-search">
          <Search size={14} aria-hidden className="sdqr-search__icon" />
          <input placeholder={t('service_desk.search_tickets')} value={search}
            aria-label={t('service_desk.search_tickets')} onChange={e => setSearch(e.target.value)} className="ds-input sdqr-search__input" />
        </div>
        <Select suelto placeholder={false} aria-label={t('service_desk.filter_all_priorities')} value={filterPrio} onChange={e => setFilterPrio(e.target.value)} className="sdqr-filter">
          <option value="">{t('service_desk.filter_all_priorities')}</option>
          {['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p =>
            <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('service_desk.filter_all_statuses')} value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="sdqr-filter">
          <option value="">{t('service_desk.filter_all_statuses')}</option>
          {['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved', 'closed', 'cancelled'].map(s =>
            <option key={s} value={s}>{t(`service_desk.${TICKET_STATUS_KEY[s]}`)}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={t('service_desk.filter_all_types')} value={filterType} onChange={e => setFilterType(e.target.value)} className="sdqr-filter">
          <option value="">{t('service_desk.filter_all_types')}</option>
          {['incident', 'service_request', 'change', 'problem', 'question'].map(tk =>
            <option key={tk} value={tk}>{etiquetaSd('type', tk)}</option>)}
        </Select>
      </div>

      {isLoading ? <div className="sdqr-loading"><Spinner /></div> :
       filtered.length === 0 ? (
        <EmptyState icon={<Ticket size={28} />} title={t('service_desk.no_tickets')}
          description={hayFiltro ? t('service_desk.no_matching') : queueOnly ? t('sd_mercado.cola_vacia') : t('queueandrouting.sin_tickets_desc')} />
       ) :
      <div data-export-table="service-desk-export" className="ds-card sdqr-card">
        <div className="u-scroll-x">
          <TablaSimple>
            <thead>
              <tr aria-label={t('queueandrouting.columnas')}>
                <th aria-sort={ariaSort(ticketSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_number')}</SortableTH></th>
                <th aria-sort={ariaSort(ticketSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_title')}</SortableTH></th>
                <th aria-sort={ariaSort(ticketSort, 'priority')} className="u-cell-nowrap"><SortableTH col="priority" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_priority')}</SortableTH></th>
                <th aria-sort={ariaSort(ticketSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_status')}</SortableTH></th>
                <th aria-sort={ariaSort(ticketSort, 'ticket_type')} className="u-cell-nowrap"><SortableTH col="ticket_type" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.ticket_type')}</SortableTH></th>
                <th aria-sort={ariaSort(ticketSort, 'sla_due')} className="u-cell-nowrap"><SortableTH col="sla_due" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.col_sla_deadline')}</SortableTH></th>
                <th aria-sort={ariaSort(ticketSort, 'assignee_name')} className="u-cell-nowrap"><SortableTH col="assignee_name" sort={ticketSort} onSort={setTicketSort}>{t('service_desk.assigned_to')}</SortableTH></th>
              </tr>
            </thead>
            <tbody>
              {sortedTickets.map(tk => <TRow key={tk.id} t={tk} onClick={() => onSelect(tk)} />)}
            </tbody>
          </TablaSimple>
        </div>
        <div className="sdqr-footer">
          <span>{t('queueandrouting.n_tickets', { n: total })}</span>
          {paginas > 1 && <Pagination page={page} totalPages={paginas} onChange={setPage} total={total} pageSize={TICKETS_POR_PAGINA} />}
        </div>
      </div>}
    </div>
  )
}

export function MajorIncidents() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showDeclare, setShowDeclare] = useState(false)

  type MI = SdIncidenteMayor
  const { data: mis = [], isLoading } = useQuery({
    queryKey: ['sd-major-incidents'],
    queryFn: () => sdRoutingApi.majorIncidents().then(r => r.data),
    refetchInterval: POLL_FREQUENT_MS,
  })

  const activeMis = mis.filter(m => m.status === 'active')
  const { sort: miSort, setSort: setMiSort, sortedData: sortedMis } = useSort<MI>(mis, 'declared_at', 'desc')
  const declarar = <Button icon={<Plus size={14} />} onClick={() => setShowDeclare(true)}>{t('service_desk.mi_declare_btn')}</Button>

  return (
    <div className="u-stack-16">
      {activeMis.length > 0 && (
        <div className="sdqr-mi-banner" role="status">
          <div className="sdqr-mi-banner__title">
            <AlertOctagon size={16} aria-hidden="true" /> {t('queueandrouting.mi_activos', { n: activeMis.length })}
          </div>
          {activeMis.map(m => (
            <div key={m.id} className="sdqr-mi-banner__row">
              <div className="u-flex1-min0">
                <span className="sdqr-mi-banner__number">{m.number}</span>
                <span className="sdqr-mi-banner__text">{m.title}</span>
              </div>
              <div className="u-text2-xs">{t('service_desk.mi_declared_at')} {fmtDate(m.declared_at)}</div>
            </div>
          ))}
        </div>
      )}

      {isLoading ? <div className="sdqr-loading"><Spinner /></div> : mis.length === 0 ? (
        <EmptyState icon={<AlertOctagon size={28} />} title={t('queueandrouting.mi_vacio')}
          description={t('queueandrouting.mi_vacio_desc')} action={declarar} />
      ) : (
        <>
          <div className="ds-toolbar">
            <div className="u-text2-sm">{t('queueandrouting.mi_registrados', { n: mis.length })}</div>
            <span className="ds-toolbar__spacer" />
            {declarar}
          </div>
          <div data-export-table="service-desk-export" className="ds-card sdqr-card">
            <div className="u-scroll-x">
              <TablaSimple>
                <thead>
                  <tr aria-label={t('queueandrouting.columnas')}>
                    <th aria-sort={ariaSort(miSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={miSort} onSort={setMiSort}>{t('service_desk.col_number')}</SortableTH></th>
                    <th aria-sort={ariaSort(miSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_title')}</SortableTH></th>
                    <th aria-sort={ariaSort(miSort, 'severity')} className="u-cell-nowrap"><SortableTH col="severity" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_severity')}</SortableTH></th>
                    <th aria-sort={ariaSort(miSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={miSort} onSort={setMiSort}>{t('service_desk.ticket_status')}</SortableTH></th>
                    <th aria-sort={ariaSort(miSort, 'commander')} className="u-cell-nowrap"><SortableTH col="commander" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_commander')}</SortableTH></th>
                    <th aria-sort={ariaSort(miSort, 'declared_at')} className="u-cell-nowrap"><SortableTH col="declared_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_declared_at')}</SortableTH></th>
                    <th aria-sort={ariaSort(miSort, 'resolved_at')} className="u-cell-nowrap"><SortableTH col="resolved_at" sort={miSort} onSort={setMiSort}>{t('service_desk.mi_resolved_at')}</SortableTH></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedMis.map(m => (
                    <tr key={m.id}>
                      <td className="sdqr-td--number sdqr-td--danger">{m.number}</td>
                      <td className="sdqr-td--title"><div className="sdqr-title">{m.title}</div></td>
                      <td><StatusBadge kind={m.severity === 'P1' ? 'danger' : 'orange'} caps={false}>{m.severity}</StatusBadge></td>
                      <td><StatusBadge kind={m.status === 'active' ? 'danger' : 'success'} caps={false}>{etiquetaSd('mi_st', m.status)}</StatusBadge></td>
                      <td className="sdqr-td--muted">{m.commander || '—'}</td>
                      <td className="sdqr-td--muted">{fmtDate(m.declared_at)}</td>
                      <td className="sdqr-td--muted">{m.resolved_at ? fmtDate(m.resolved_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple>
            </div>
          </div>
        </>
      )}

      {showDeclare && (
        <DeclareMIModal onClose={() => setShowDeclare(false)} onSaved={() => {
          qc.invalidateQueries({ queryKey: ['sd-major-incidents'] })
          setShowDeclare(false)
          toast.success(t('service_desk.mi_declared_success'))
        }} />
      )}
    </div>
  )
}

function DeclareMIModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const idPrefix = useId()
  const [form, setForm] = useState({ title: '', severity: 'P1', impact_statement: '' })
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (data: Record<string, unknown>) => sdRoutingApi.createMajorIncident(data),
    onSuccess: onSaved,
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  const set = (k: string) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <Modal open title={t('service_desk.mi_declare_btn')} onClose={onClose}>
      <div className="u-stack-16">
        <div>
          <label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} className="campo-etiqueta">{t('service_desk.mi_title_lbl')} *</label>
          <input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} className="campo-form" />{msg('title')}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-severity`} className="campo-etiqueta">{t('service_desk.mi_severity_lbl')}</label>
          <Select suelto placeholder={false} id={`${idPrefix}-severity`} value={form.severity} onChange={set('severity')} className="campo-form">
            <option value="P1">{t('service_desk.priority_p1')}</option>
            <option value="P2">{t('service_desk.priority_p2')}</option>
          </Select>{msg('severity')}
        </div>
        <div>
          <label id={`${idPrefix}-impact-et`} htmlFor={`${idPrefix}-impact`} className="campo-etiqueta">{t('service_desk.mi_impact_lbl')}</label>
          <textarea id={`${idPrefix}-impact`} aria-labelledby={`${idPrefix}-impact-et`} value={form.impact_statement} onChange={set('impact_statement')} rows={3}
            className="campo-form sdqr-textarea" />{msg('impact_statement')}
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>
            {t('service_desk.mi_declare_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

type Rule = SdReglaDeEnrutado

/** Nombres legibles de las condiciones y acciones de una regla. */
function useEtiquetasDeRegla() {
  const t = useAppT()
  const COND_TYPES = [
    { key: 'ticket_type', label: t('service_desk.ticket_type') },
    { key: 'priority', label: t('service_desk.ticket_priority') },
    { key: 'keyword_in_title', label: t('service_desk.ticket_title') },
    { key: 'requester_domain', label: t('queueandrouting.cond_domain') },
    { key: 'tag_contains', label: t('queueandrouting.cond_tag') },
    { key: 'time_of_day', label: t('queueandrouting.cond_time') },
    { key: 'day_of_week', label: t('queueandrouting.cond_day') },
    { key: 'sla_policy_id', label: t('queueandrouting.cond_sla') },
  ]
  const ACT_TYPES = [
    { key: 'assign_group', label: t('queueandrouting.act_assign_group') },
    { key: 'assign_user', label: t('queueandrouting.act_assign_user') },
    { key: 'set_support_level', label: t('queueandrouting.act_set_level') },
    { key: 'set_priority', label: t('queueandrouting.act_set_priority') },
  ]
  return { COND_TYPES, ACT_TYPES }
}

export function RoutingRules() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editingRule, setEditingRule] = useState<Rule | null>(null)
  const { COND_TYPES, ACT_TYPES } = useEtiquetasDeRegla()

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['sd-routing-rules'],
    queryFn: () => sdRoutingApi.list().then(r => r.data),
  })
  // Para enseñar el nombre del grupo, del agente y de la política, no su id.
  const { data: groups = [] } = useQuery<Array<{ id?: string; name?: string }>>({
    queryKey: ['sd-groups'],
    queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery<Array<{ id?: string; full_name?: string }>>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const { data: slaPolicies = [] } = useQuery<Array<{ id?: string; name?: string }>>({
    queryKey: ['sd-sla-policies'],
    queryFn: () => sdSlaPoliciesApi.list().then(r => r.data).catch(() => []),
  })

  const { mutate: toggleRule } = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => sdRoutingApi.update(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: (id: string) => sdRoutingApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-routing-rules'] }); toast.success(t('service_desk.routing_rule_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const nombreDe = (lista: Array<{ id?: string; name?: string; full_name?: string }>, id: string) => {
    const x = lista.find(e => e.id === id)
    return x?.name || x?.full_name || id
  }
  const valorLegible = (k: string, v: unknown): string => {
    const lista = Array.isArray(v) ? v.map(String) : String(v).split(',')
    const uno = (x: string) => {
      if (k === 'ticket_type') return etiquetaSd('type', x)
      if (k === 'priority' || k === 'set_priority') return PRIORITY_LABEL[x] || x
      if (k === 'assign_group') return nombreDe(groups, x)
      if (k === 'assign_user') return nombreDe(users, x)
      if (k === 'sla_policy_id') return nombreDe(slaPolicies, x)
      if (k === 'set_support_level') return t(`queueandrouting.level_${x}`)
      return x
    }
    return lista.map(x => uno(x.trim())).join(', ')
  }
  const etiquetaCond = (k: string) => COND_TYPES.find(c => c.key === k)?.label ?? k
  const etiquetaAcc = (k: string) => ACT_TYPES.find(c => c.key === k)?.label ?? k
  const nueva = <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('service_desk.routing_new_title')}</Button>

  return (
    <div className="u-stack-16">
      {isLoading ? <div className="sdqr-loading"><Spinner /></div> :
       rules.length === 0 ? <EmptyState icon={<Route size={28} />} title={t('service_desk.routing_no_rules')} description={t('service_desk.routing_no_rules_desc')} action={nueva} /> :
      <>
        <div className="ds-toolbar">
          <div className="u-text3-sm sdqr-flex">{t('service_desk.routing_no_rules_desc')}</div>
          {nueva}
        </div>
        <div className="u-stack-8">
          {rules.map(rule => {
            const conds = rule.conditions ?? {}, acts = rule.actions ?? {}
            return (
              <div key={rule.id} className={rule.is_active ? 'ds-card sdqr-rule' : 'ds-card sdqr-rule sdqr-rule--off'}>
                <div className="sdqr-rule__head">
                  <div className="sdqr-rule__name-wrap">
                    <span className="sdqr-rule__prio">{t('queueandrouting.orden_n', { n: rule.priority })}</span>
                    <span className="sdqr-rule__name">{rule.name}</span>
                  </div>
                  <div className="u-wrap-center-8">
                    <Pulsable onClick={() => toggleRule({ id: rule.id, is_active: !rule.is_active })}
                      aria-pressed={rule.is_active}
                      aria-label={t(rule.is_active ? 'queueandrouting.desactivar_regla' : 'queueandrouting.activar_regla', { name: rule.name })}
                      className="sdqr-toggle">
                      <StatusBadge kind={rule.is_active ? 'success' : 'neutral'} dot caps={false}>
                        {rule.is_active ? t('service_desk.routing_active') : t('service_desk.routing_inactive')}
                      </StatusBadge>
                    </Pulsable>
                    <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditingRule(rule)}>{t('common.edit')}</Button>
                    <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => deleteRule(rule.id)}>{t('common.delete')}</Button>
                  </div>
                </div>
                <div className="sdqr-rule__body">
                  <div className="sdqr-rule__line">
                    <span className="ds-eyebrow">{t('queueandrouting.si')}</span>
                    {Object.keys(conds).length === 0
                      ? <span className="u-text3-xs">{t('queueandrouting.sin_condiciones')}</span>
                      : Object.entries(conds).map(([k, v]) => (
                        <StatusBadge key={k} caps={false}>{etiquetaCond(k)}: {valorLegible(k, v)}</StatusBadge>
                      ))}
                  </div>
                  <div className="sdqr-rule__line">
                    <span className="ds-eyebrow">{t('queueandrouting.entonces')}</span>
                    {Object.entries(acts).map(([k, v]) => (
                      <StatusBadge key={k} kind="accent" caps={false}>{etiquetaAcc(k)}: {valorLegible(k, v)}</StatusBadge>
                    ))}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </>}

      {showNew && <NewRoutingRuleModal onClose={() => setShowNew(false)} onSaved={() => {
        qc.invalidateQueries({ queryKey: ['sd-routing-rules'] })
        setShowNew(false)
        toast.success(t('service_desk.routing_rule_created'))
      }} />}
      {editingRule && <NewRoutingRuleModal rule={editingRule} onClose={() => setEditingRule(null)} onSaved={() => {
        qc.invalidateQueries({ queryKey: ['sd-routing-rules'] })
        setEditingRule(null)
        toast.success(t('service_desk.routing_rule_updated'))
      }} />}
    </div>
  )
}

type Entry = { key: string; value: string }
function NewRoutingRuleModal({ onClose, onSaved, rule }: { onClose: () => void; onSaved: () => void; rule?: Rule }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const isEdit = !!rule
  const { COND_TYPES, ACT_TYPES } = useEtiquetasDeRegla()

  const parseEntries = (obj: Record<string, unknown> | undefined): Entry[] =>
    Object.entries(obj ?? {}).map(([key, value]) => ({ key, value: Array.isArray(value) ? value.join(',') : String(value) }))

  const [form, setForm] = useState<{ name: string; priority: number | string }>(isEdit ? { name: rule!.name || '', priority: rule!.priority ?? 100 } : { name: '', priority: 100 })
  const [conditions, setConditions] = useState<Entry[]>(isEdit ? parseEntries(rule!.conditions) : [])
  const [actions, setActions] = useState<Entry[]>(isEdit ? parseEntries(rule!.actions) : [{ key: 'assign_group', value: '' }])

  const { data: groups = [] } = useQuery<Array<{ id?: string; name?: string }>>({
    queryKey: ['sd-groups'],
    queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery<Array<{ id?: string; full_name?: string }>>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const { data: slaPolices = [] } = useQuery<Array<{ id?: string; name?: string }>>({
    queryKey: ['sd-sla-policies'],
    queryFn: () => sdSlaPoliciesApi.list().then(r => r.data).catch(() => []),
  })

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (data: Record<string, unknown>): Promise<unknown> => isEdit
      ? sdRoutingApi.update(rule!.id, data)
      : sdRoutingApi.create(data),
    onSuccess: onSaved,
    onError: (e: unknown) => { camposB.recoger(e); toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const IS = 'campo-form'
  const LS = 'campo-etiqueta'

  const usedCondKeys = conditions.map(c => c.key)
  const availCondTypes = COND_TYPES.filter(type => !usedCondKeys.includes(type.key))

  const addCondition = () => {
    const next = availCondTypes[0]
    if (next) setConditions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeCondition = (i: number) => setConditions(prev => prev.filter((_, idx) => idx !== i))
  const updateCond = (i: number, patch: Partial<Entry>) => setConditions(prev => prev.map((c, idx) => idx === i ? { ...c, ...patch } : c))

  const addAction = () => {
    const usedActKeys = actions.map(a => a.key)
    const next = ACT_TYPES.find(type => !usedActKeys.includes(type.key))
    if (next) setActions(prev => [...prev, { key: next.key, value: '' }])
  }
  const removeAction = (i: number) => setActions(prev => prev.filter((_, idx) => idx !== i))
  const updateAct = (i: number, patch: Partial<Entry>) => setActions(prev => prev.map((a, idx) => idx === i ? { ...a, ...patch } : a))

  const renderCondValue = (cond: Entry, i: number) => {
    const upd = (v: string) => updateCond(i, { value: v })
    if (cond.key === 'ticket_type') return (
      <Select suelto placeholder={false} id={`${idCampo}-cv-${i}`} value={cond.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('service_desk.cond_any_type')}</option>
        {['incident', 'service_request', 'change', 'problem'].map(v =>
          <option key={v} value={v}>{etiquetaSd('type', v)}</option>)}
      </Select>
    )
    if (cond.key === 'priority') return (
      <Select suelto placeholder={false} id={`${idCampo}-cv-${i}`} value={cond.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('service_desk.cond_any_priority')}</option>
        {Object.entries(PRIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </Select>
    )
    if (cond.key === 'sla_policy_id') return (
      <Select suelto placeholder={false} id={`${idCampo}-cv-${i}`} value={cond.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('service_desk.cond_any_policy')}</option>
        {slaPolices.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </Select>
    )
    if (cond.key === 'day_of_week') {
      // Nombre corto del dia en el idioma activo: el 1-1-2024 fue lunes.
      const diaCorto = new Intl.DateTimeFormat(localeActivo(), { weekday: 'short' })
      const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        .map((v, n) => [v, diaCorto.format(new Date(2024, 0, 1 + n))])
      const selected = cond.value ? cond.value.split(',') : []
      return (
        <div id={`${idCampo}-cv-${i}`} role="group" aria-labelledby={`${idCampo}-cv-${i}-et`} className="sdqr-days">
          {DAYS.map(([v, l]) => (
            <Pulsable key={v} aria-pressed={selected.includes(v)}
              onClick={() => {
                const next = selected.includes(v) ? selected.filter(d => d !== v) : [...selected, v]
                upd(next.join(','))
              }}
              className="sdqr-day">
              {l}
            </Pulsable>
          ))}
        </div>
      )
    }
    return (
      <input id={`${idCampo}-cv-${i}`} aria-labelledby={`${idCampo}-cv-${i}-et`} value={cond.value} onChange={e => upd(e.target.value)} className={IS}
        placeholder={
          cond.key === 'keyword_in_title' ? t('queueandrouting.ph_keyword') :
          cond.key === 'requester_domain' ? t('queueandrouting.ph_domain') :
          cond.key === 'tag_contains' ? t('queueandrouting.ph_tag') :
          cond.key === 'time_of_day' ? '08:00-17:00' : ''
        }
      />
    )
  }

  const renderActValue = (act: Entry, i: number) => {
    const upd = (v: string) => updateAct(i, { value: v })
    if (act.key === 'assign_group') return (
      <Select suelto placeholder={false} id={`${idCampo}-av-${i}`} value={act.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('service_desk.act_no_group')}</option>
        {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
      </Select>
    )
    if (act.key === 'assign_user') return (
      <Select suelto placeholder={false} id={`${idCampo}-av-${i}`} value={act.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('service_desk.act_no_agent')}</option>
        {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
      </Select>
    )
    if (act.key === 'set_support_level') return (
      <Select suelto placeholder={false} id={`${idCampo}-av-${i}`} value={act.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('service_desk.act_no_change')}</option>
        {['l1', 'l2', 'l3'].map(v => <option key={v} value={v}>{t(`queueandrouting.level_${v}`)}</option>)}
      </Select>
    )
    if (act.key === 'set_priority') return (
      <Select suelto placeholder={false} id={`${idCampo}-av-${i}`} value={act.value} onChange={e => upd(e.target.value)} className={IS}>
        <option value="">{t('queueandrouting.no_cambiar')}</option>
        {Object.entries(PRIORITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </Select>
    )
    return <input id={`${idCampo}-av-${i}`} aria-labelledby={`${idCampo}-av-${i}-et`} value={act.value} onChange={e => upd(e.target.value)} className={IS} />
  }

  const handleSave = () => {
    if (!form.name.trim()) { toast.error(t('service_desk.routing_name_required')); return }
    const condObj: Record<string, string | string[]> = {}
    for (const c of conditions) {
      if (!c.value) continue
      if (c.key === 'priority' || c.key === 'day_of_week') {
        condObj[c.key] = c.value.includes(',') ? c.value.split(',') : c.value
      } else {
        condObj[c.key] = c.value
      }
    }
    const actObj: Record<string, string> = {}
    for (const a of actions) {
      if (a.value) actObj[a.key] = a.value
    }
    if (Object.keys(actObj).length === 0) { toast.error(t('service_desk.routing_needs_action')); return }
    mutate({
      name: form.name.trim(),
      priority: Number(form.priority),
      conditions: condObj,
      actions: actObj,
      is_active: true,
    })
  }

  return (
    <Modal open size="lg" title={isEdit ? t('queueandrouting.editar_regla', { name: rule.name }) : t('service_desk.routing_new_title')} onClose={onClose}>
      <div className="sdqr-modal-body">
        <div className="sdqr-name-row">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('service_desk.routing_name_lbl')} *</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => { camposB.limpiar('name'); setForm(f => ({ ...f, name: e.target.value })) }}
              className={IS} autoFocus />{msgB('name')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('service_desk.routing_order_lbl')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={form.priority}
              onChange={e => { camposB.limpiar('priority'); setForm(f => ({ ...f, priority: e.target.value })) }}
              className={IS} />{msgB('priority')}
          </div>
        </div>

        <div className="sdqr-box">
          <div className="sdqr-box__head">
            <span className="sdqr-box__title">{t('queueandrouting.condiciones')}</span>
            <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={addCondition} disabled={availCondTypes.length === 0}>
              {t('queueandrouting.condicion')}
            </Button>
          </div>
          {conditions.length === 0 && (
            <div className="sdqr-empty">{t('queueandrouting.sin_condiciones')}</div>
          )}
          {conditions.map((cond, i) => (
            <div key={i} className="sdqr-entry">
              <div>
                <label htmlFor={`${idCampo}-ck-${i}`} className={LS}>{t('service_desk.cond_field')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-ck-${i}`} value={cond.key}
                  onChange={e => updateCond(i, { key: e.target.value, value: '' })}
                  className={IS}>
                  {COND_TYPES.filter(type => type.key === cond.key || !usedCondKeys.filter((_, idx) => idx !== i).includes(type.key)).map(type =>
                    <option key={type.key} value={type.key}>{type.label}</option>
                  )}
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-cv-${i}-et`} htmlFor={`${idCampo}-cv-${i}`} className={LS}>{t('service_desk.cond_value')}</label>
                {renderCondValue(cond, i)}
              </div>
              <div className="sdqr-entry__remove-cell">
                <IconButton onClick={() => removeCondition(i)} ariaLabel={t('queueandrouting.quitar_condicion')}
                  title={t('queueandrouting.quitar_condicion')} className="sdqr-remove">
                  <X size={14} aria-hidden="true" />
                </IconButton>
              </div>
            </div>
          ))}
        </div>

        <div className="sdqr-box">
          <div className="sdqr-box__head">
            <span className="sdqr-box__title">{t('queueandrouting.acciones')}</span>
            <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={addAction} disabled={actions.length >= ACT_TYPES.length}>
              {t('queueandrouting.accion')}
            </Button>
          </div>
          {actions.map((act, i) => (
            <div key={i} className="sdqr-entry">
              <div>
                <label htmlFor={`${idCampo}-ak-${i}`} className={LS}>{t('service_desk.act_label')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-ak-${i}`} value={act.key}
                  onChange={e => updateAct(i, { key: e.target.value, value: '' })}
                  className={IS}>
                  {ACT_TYPES.filter(type => type.key === act.key || !actions.filter((_, idx) => idx !== i).map(a => a.key).includes(type.key)).map(type =>
                    <option key={type.key} value={type.key}>{type.label}</option>
                  )}
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-av-${i}-et`} htmlFor={`${idCampo}-av-${i}`} className={LS}>{t('service_desk.cond_value')}</label>
                {renderActValue(act, i)}
              </div>
              <div className="sdqr-entry__remove-cell">
                <IconButton onClick={() => removeAction(i)} ariaLabel={t('queueandrouting.quitar_accion')}
                  title={t('queueandrouting.quitar_accion')} className="sdqr-remove">
                  <X size={14} aria-hidden="true" />
                </IconButton>
              </div>
            </div>
          ))}
        </div>

        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={handleSave} disabled={isPending || !form.name} loading={isPending}>{isEdit ? t('common.save') : t('queueandrouting.crear_regla')}</Button>
        </div>
      </div>
    </Modal>
  )
}
