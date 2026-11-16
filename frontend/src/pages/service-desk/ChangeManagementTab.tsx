/**
 * Gestión de cambios del service desk (pestaña «Cambios»).
 *
 * 16-11-2026 (pasada de diseño): pestañas de vista con <Tabs> del kit (antes
 * botones a mano); estado y riesgo con <StatusBadge> (antes píldoras propias y
 * un «⚠»); botones de fila y del panel con <Button> e iconos lucide (antes
 * «✏» y botones teñidos a mano); vacío con icono lucide y acción; filtro de
 * estado en una barra con `ds-input`; fechas con el formateador de la app;
 * textos sin anglicismos («solicitud de cambio», «responsable», «vuelta atrás»).
 */
import { useId, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, GitPullRequest, List, Package, Pencil, Plus, Snowflake, Users, X } from 'lucide-react'

import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { changesApi, cmdbApi, sdChangePlanningApi } from '../../services/api'
import type { CambioItsm, CambioItsmDetalle, EstadoDeCambio } from '../../services/api/tipos-cambios'
import { CalendarioCambios, Congelaciones, PanelCab, Versiones } from './CambiosPlanificacion'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Spinner, EmptyState, Modal, StatusBadge, Tabs, IconButton, useSort, SortableTH, ariaSort } from '../../components/ui'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { useAppLang } from '../../i18n/AppLangContext'
import { etiquetaSd } from './sdUtils'
import DateInput from '../../components/ui/DateInput'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import './ChangeManagementTab.css'
import AnalisisDelCambio from '../../components/servicedesk/AnalisisDelCambio'
import PanelDelCab from '../../components/servicedesk/PanelDelCab'

type ChangeId = string | number
/** El listado manda `serialize_change`; el detalle, ademas, los textos largos. */
type ChangeItem = CambioItsm & Partial<Omit<CambioItsmDetalle, keyof CambioItsm>>

interface ChangeFormData {
  title: string
  description: string
  change_type: string
  risk: string
  priority: string
  business_justification: string
  implementation_plan: string
  rollback_plan: string
  test_plan: string
  impact_description?: string
  planned_start: string
  planned_end: string
  downtime_minutes?: number
  affected_cis?: string[]
  release_id?: string | null
}

interface StatusAction {
  label: string
  next?: EstadoDeCambio
  action?: 'approve' | 'reject' | 'open'
}

const CHANGE_STATUS_KIND: Record<string, StatusBadgeKind> = {
  draft: 'neutral',
  submitted: 'accent',
  cab_review: 'warning',
  approved: 'success',
  scheduled: 'purple',
  in_progress: 'accent',
  implemented: 'success',
  post_review: 'warning',
  closed_success: 'success',
  closed_failed: 'danger',
  cancelled: 'neutral',
}

const RISK_KIND: Record<string, StatusBadgeKind> = { low: 'success', medium: 'warning', high: 'orange', critical: 'danger' }

const RISKS = ['low', 'medium', 'high', 'critical'] as const
const CHANGE_TYPES = ['standard', 'normal', 'emergency'] as const
const ESTADOS_FILTRO = ['draft', 'submitted', 'cab_review', 'approved', 'scheduled', 'in_progress', 'implemented', 'post_review', 'closed_success', 'closed_failed']

function EstadoBadge({ status }: { status?: string | null }) {
  return <StatusBadge kind={CHANGE_STATUS_KIND[status ?? ''] ?? 'neutral'} caps={false} className="chgm-nowrap">{etiquetaSd('chg_st', status)}</StatusBadge>
}

function RiesgoBadge({ risk }: { risk?: string | null }) {
  const { t } = useAppLang()
  if (!risk) return null
  return <StatusBadge kind={RISK_KIND[risk] ?? 'neutral'} caps={false} className="chgm-nowrap">{t(`changemanagement.risk_${risk}`)}</StatusBadge>
}

function ChangeDetailPanel({
  change,
  onClose,
  onEdit,
  onAction,
  statusActions,
}: {
  change: ChangeItem
  onClose: () => void
  onEdit: () => void
  onAction: (change: ChangeItem, action: StatusAction) => void
  statusActions: Record<string, StatusAction[]>
}) {
  const { t } = useAppLang()
  const { data: detail, isLoading } = useQuery({
    queryKey: ['sd-change-detail', change.id],
    queryFn: () => changesApi.get(change.id).then(r => r.data),
  })

  const c = detail || change

  const Section = ({ title, content: text }: { title: string; content?: string }) => text ? (
    <div className="u-mb-16">
      <div className="chgm-sec__title">{title}</div>
      <div className="chgm-sec__body">{text}</div>
    </div>
  ) : null

  const actions = statusActions[c.status || ''] || []

  return (
    <div className="chgm-panel" role="dialog" aria-label={c.title || c.number}>
      <div className="chgm-panel__head">
        <div className="chgm-panel__top">
          <div className="chgm-panel__titlebox">
            <div className="chgm-panel__meta">
              <span className="chgm-panel__number">{c.number}</span>
              <EstadoBadge status={c.status} />
              <RiesgoBadge risk={c.risk} />
              <span className="u-text3-xs">{etiquetaSd('chg_type', c.change_type)}</span>
            </div>
            <div className="chgm-panel__title">{c.title}</div>
          </div>
          <IconButton ariaLabel={t('changemanagement.cerrar_detalle')} onClick={onClose}><X size={16} aria-hidden /></IconButton>
        </div>
        <div className="chgm-panel__actions">
          <Button size="sm" variant="secondary" icon={<Pencil size={13} />} onClick={onEdit}>{t('changemanagement.editar')}</Button>
          {actions.map(a => (
            <Button size="sm" key={a.label} onClick={() => { onAction(c, a); onClose() }}>{a.label}</Button>
          ))}
        </div>
      </div>

      <div className="chgm-panel__body">
        {isLoading ? <Spinner /> : <>
          {c.rejected_reason && (
            <div role="status" className="chgm-rejected">{c.rejected_reason}</div>
          )}
          <PanelCab changeId={c.id} />
          <AnalisisDelCambio cambio={c} />
          <div className="chgm-facts">
            {[
              ['solicitante', c.requester || '—'],
              ['owner', c.owner || '—'],
              ['inicio_planif', fmtDateTime(c.planned_start)],
              ['fin_planif', fmtDateTime(c.planned_end)],
              ['inicio_real', fmtDateTime(c.actual_start)],
              ['fin_real', fmtDateTime(c.actual_end)],
              ['downtime', c.downtime_minutes ? t('changemanagement.n_min', { n: c.downtime_minutes }) : '—'],
              ['aprobado', fmtDateTime(c.approved_at)],
            ].map(([key, val]) => (
              <div key={key} className="chgm-fact">
                <div className="chgm-fact__label">{t(`changemanagement.${key}`)}</div>
                <div className="chgm-fact__value">{val}</div>
              </div>
            ))}
          </div>
          <Section title={t('changemanagement.descripcion')} content={c.description} />
          <Section title={t('changemanagement.justificacion_de_negocio')} content={c.business_justification} />
          <Section title={t('changemanagement.plan_de_implementacion')} content={c.implementation_plan} />
          <Section title={t('changemanagement.plan_de_rollback')} content={c.rollback_plan} />
          <Section title={t('changemanagement.plan_de_pruebas')} content={c.test_plan} />
          <Section title={t('changemanagement.descripcion_de_impacto')} content={c.impact_description} />
        </>}
      </div>
    </div>
  )
}

const IS = 'ds-input'

function ChangeEditModal({ change, onClose, onSaved }: { change: ChangeItem; onClose: () => void; onSaved: () => void }) {
  const { t } = useAppLang()
  const idPrefix = useId()
  const toast = useToast()
  const [form, setForm] = useState<ChangeFormData>({
    title: change.title || '',
    description: change.description || '',
    change_type: change.change_type || 'normal',
    risk: change.risk || 'medium',
    priority: change.priority || 'p3_medium',
    business_justification: change.business_justification || '',
    implementation_plan: change.implementation_plan || '',
    rollback_plan: change.rollback_plan || '',
    test_plan: change.test_plan || '',
    impact_description: change.impact_description || '',
    planned_start: change.planned_start ? change.planned_start.replace(' ', 'T').slice(0, 16) : '',
    planned_end: change.planned_end ? change.planned_end.replace(' ', 'T').slice(0, 16) : '',
    downtime_minutes: change.downtime_minutes || 0,
    affected_cis: change.affected_cis ?? [],
    release_id: change.release_id ?? null,
  })
  const ts = useAppT()
  const { data: cis = [] } = useQuery<{ id: string; name: string; code?: string }[]>({
    queryKey: ['sd-cmdb-items'], queryFn: () => cmdbApi.sdList({ page_size: SELECTOR_LIST_SIZE }).then(r => r.data),
  })
  const { data: versiones = [] } = useQuery({
    queryKey: ['sd-releases'], queryFn: () => sdChangePlanningApi.releases().then(r => r.data),
  })
  const alternarCi = (id: string) => setForm(f => ({ ...f, affected_cis: (f.affected_cis ?? []).includes(id)
    ? (f.affected_cis ?? []).filter(x => x !== id) : [...(f.affected_cis ?? []), id] }))
  const { mutate, isPending } = useMutation({
    mutationFn: (data: ChangeFormData) => changesApi.update(change.id, data),
    onSuccess: onSaved,
    onError: (e: unknown) => toast.error(extractErr(e, t('changemanagement.error_guardar'))),
  })
  const set = (k: keyof ChangeFormData) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const rawValue = e.target.value
    const nextValue = k === 'downtime_minutes' ? Number(rawValue) : rawValue
    setForm((f) => ({ ...f, [k]: nextValue }))
  }

  return (
    <Modal open title={t('changemanagement.editar_titulo', { number: change.number })} onClose={onClose} size="lg">
      <div className="chgm-form chgm-form--scroll">
        <div className="u-col-full"><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} className="chgm-label">{t('changemanagement.titulo')}</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} className={IS} /></div>
        <div><label htmlFor={`${idPrefix}-change-type`} className="chgm-label">{t('changemanagement.tipo_de_cambio')}</label><select id={`${idPrefix}-change-type`} value={form.change_type} onChange={set('change_type')} className={IS}>{CHANGE_TYPES.map(v => <option key={v} value={v}>{t(`changemanagement.opt_${v}`)}</option>)}</select></div>
        <div><label htmlFor={`${idPrefix}-risk`} className="chgm-label">{t('changemanagement.riesgo')}</label><select id={`${idPrefix}-risk`} value={form.risk} onChange={set('risk')} className={IS}>{RISKS.map(v => <option key={v} value={v}>{t(`changemanagement.risk_${v}`)}</option>)}</select></div>
        <div><label htmlFor={`${idPrefix}-planned-start`} className="chgm-label">{t('changemanagement.inicio_planificado')}</label><DateInput id={`${idPrefix}-planned-start`} withTime value={form.planned_start} onChange={set('planned_start')} className={IS} /></div>
        <div><label htmlFor={`${idPrefix}-planned-end`} className="chgm-label">{t('changemanagement.fin_planificado')}</label><DateInput id={`${idPrefix}-planned-end`} withTime value={form.planned_end} onChange={set('planned_end')} className={IS} /></div>
        <div><label id={`${idPrefix}-downtime-et`} htmlFor={`${idPrefix}-downtime`} className="chgm-label">{t('changemanagement.downtime_estimado')}</label><input id={`${idPrefix}-downtime`} aria-labelledby={`${idPrefix}-downtime-et`} type="number" value={form.downtime_minutes} onChange={set('downtime_minutes')} className={IS} min="0" /></div>
        <div><label htmlFor={`${idPrefix}-release`} className="chgm-label">{ts('sd_cfg.chg_release')}</label>
          <select id={`${idPrefix}-release`} value={form.release_id ?? ''} onChange={e => setForm(f => ({ ...f, release_id: e.target.value || null }))} className={IS}>
            <option value="">{ts('sd_cfg.chg_none')}</option>
            {versiones.filter(v => v.status !== 'released' && v.status !== 'cancelled').map(v => <option key={v.id} value={v.id}>{v.name}{v.version ? ` ${v.version}` : ''}</option>)}
          </select></div>
        <div className="u-col-full" role="group" aria-labelledby={`${idPrefix}-cis-et`}><span id={`${idPrefix}-cis-et`} className="chgm-label">{ts('sd_cfg.chg_affected_cis')}</span>
          <div className="chgm-cis">
            {cis.map(ci => {
              const on = (form.affected_cis ?? []).includes(ci.id)
              return <button key={ci.id} type="button" aria-pressed={on} onClick={() => alternarCi(ci.id)} className="chgm-chip">{ci.code ? `${ci.code} · ` : ''}{ci.name}</button>
            })}
          </div></div>
        <div className="u-col-full"><label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} className="chgm-label">{t('changemanagement.descripcion_2')}</label><textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={set('description')} rows={3} className={IS} /></div>
        <div className="u-col-full"><label id={`${idPrefix}-business-justification-et`} htmlFor={`${idPrefix}-business-justification`} className="chgm-label">{t('changemanagement.justificacion_de_negocio')}</label><textarea id={`${idPrefix}-business-justification`} aria-labelledby={`${idPrefix}-business-justification-et`} value={form.business_justification} onChange={set('business_justification')} rows={2} className={IS} /></div>
        <div><label id={`${idPrefix}-implementation-plan-et`} htmlFor={`${idPrefix}-implementation-plan`} className="chgm-label">{t('changemanagement.plan_de_implementacion')}</label><textarea id={`${idPrefix}-implementation-plan`} aria-labelledby={`${idPrefix}-implementation-plan-et`} value={form.implementation_plan} onChange={set('implementation_plan')} rows={4} className={IS} /></div>
        <div><label id={`${idPrefix}-rollback-plan-et`} htmlFor={`${idPrefix}-rollback-plan`} className="chgm-label">{t('changemanagement.plan_de_rollback')}</label><textarea id={`${idPrefix}-rollback-plan`} aria-labelledby={`${idPrefix}-rollback-plan-et`} value={form.rollback_plan} onChange={set('rollback_plan')} rows={4} className={IS} /></div>
        <div><label id={`${idPrefix}-test-plan-et`} htmlFor={`${idPrefix}-test-plan`} className="chgm-label">{t('changemanagement.plan_de_pruebas')}</label><textarea id={`${idPrefix}-test-plan`} aria-labelledby={`${idPrefix}-test-plan-et`} value={form.test_plan} onChange={set('test_plan')} rows={3} className={IS} /></div>
        <div><label id={`${idPrefix}-impact-description-et`} htmlFor={`${idPrefix}-impact-description`} className="chgm-label">{t('changemanagement.descripcion_de_impacto')}</label><textarea id={`${idPrefix}-impact-description`} aria-labelledby={`${idPrefix}-impact-description-et`} value={form.impact_description} onChange={set('impact_description')} rows={3} className={IS} /></div>
        <div className="chgm-form__footer"><Button variant="secondary" onClick={onClose}>{t('changemanagement.cancelar')}</Button><Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>{t('changemanagement.guardar_cambios')}</Button></div>
      </div>
    </Modal>
  )
}

function NewChangeModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const idCampo = useId()
  const { t } = useAppLang()
  const idPrefix = useId()
  const toast = useToast()
  const [form, setForm] = useState<ChangeFormData>({
    title: '', description: '', change_type: 'normal', risk: 'medium', priority: 'p3_medium', business_justification: '', implementation_plan: '', rollback_plan: '', test_plan: '', planned_start: '', planned_end: '',
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (data: ChangeFormData) => changesApi.create(data),
    onSuccess: onSaved,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const set = (k: keyof ChangeFormData) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const rawValue = e.target.value
    const nextValue = k === 'downtime_minutes' ? Number(rawValue) : rawValue
    setForm((f) => ({ ...f, [k]: nextValue }))
  }

  return (
    <Modal open title={t('changemanagement.nuevo_change_request')} onClose={onClose} size="lg">
      <div className="chgm-form">
        <div className="u-col-full"><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} className="chgm-label">{t('changemanagement.titulo')}</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} className={IS} placeholder={t('changemanagement.titulo_del_cambio')} /></div>
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="chgm-label">{t('changemanagement.tipo_de_cambio')}</label><select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.change_type} onChange={set('change_type')} className={IS}>{CHANGE_TYPES.map(v => <option key={v} value={v}>{t(`changemanagement.opt_${v}`)}</option>)}</select></div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="chgm-label">{t('changemanagement.riesgo')}</label><select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.risk} onChange={set('risk')} className={IS}>{RISKS.map(v => <option key={v} value={v}>{t(`changemanagement.risk_${v}`)}</option>)}</select></div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="chgm-label">{t('changemanagement.inicio_planificado')}</label><DateInput id={`${idCampo}-3`} withTime value={form.planned_start} onChange={set('planned_start')} className={IS} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="chgm-label">{t('changemanagement.fin_planificado')}</label><DateInput id={`${idCampo}-4`} withTime value={form.planned_end} onChange={set('planned_end')} className={IS} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="chgm-label">{t('changemanagement.descripcion_2')}</label><textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={set('description')} rows={3} className={IS} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="chgm-label">{t('changemanagement.justificacion_de_negocio')}</label><textarea id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.business_justification} onChange={set('business_justification')} rows={2} className={IS} /></div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="chgm-label">{t('changemanagement.plan_de_implementacion')}</label><textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.implementation_plan} onChange={set('implementation_plan')} rows={3} className={IS} /></div>
        <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="chgm-label">{t('changemanagement.plan_de_rollback')}</label><textarea id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.rollback_plan} onChange={set('rollback_plan')} rows={3} className={IS} /></div>
        <div className="chgm-form__footer chgm-form__footer--mt"><Button variant="secondary" onClick={onClose}>{t('changemanagement.cancelar')}</Button><Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.description} loading={isPending}>{t('changemanagement.crear_change_request')}</Button></div>
      </div>
    </Modal>
  )
}

export default function ChangeManagementTab() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)
  const [editing, setEditing] = useState<ChangeItem | null>(null)
  const [detail, setDetail] = useState<ChangeItem | null>(null)
  const [filterStatus, setFilterStatus] = useState('')
  const ts = useAppT()
  const [vista, setVista] = useState<'list' | 'calendar' | 'releases' | 'blackouts' | 'cab'>('list')
  const abrir = (id: string) => setDetail({ id } as ChangeItem)

  const { data: changes = [], isLoading } = useQuery<ChangeItem[]>({
    queryKey: ['sd-changes', filterStatus],
    queryFn: () => changesApi.list({ status: filterStatus || undefined }).then(r => r.data),
  })

  const { mutate: approve } = useMutation({
    mutationFn: ({ id, approved }: { id: ChangeId; approved: boolean }) => changesApi.approve(id, { approved }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success(t('changemanagement.change_actualizado')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('changemanagement.error_actualizar'))),
  })

  const { sort: changeSort, setSort: setChangeSort, sortedData: sortedChanges } = useSort(changes, 'number')

  const STATUS_ACTIONS: Record<string, StatusAction[]> = {
    draft: [{ label: t('changemanagement.act_enviar_revision'), next: 'submitted' }],
    submitted: [{ label: t('changemanagement.act_enviar_cab'), next: 'cab_review' }],
    // Se vota en el panel del cambio: cada miembro del CAB, con motivo si es en contra.
    cab_review: [{ label: ts('sd_cfg.chg_cab'), action: 'open' }],
    approved: [{ label: t('changemanagement.act_programar'), next: 'scheduled' }],
    scheduled: [{ label: t('changemanagement.act_iniciar'), next: 'in_progress' }],
    in_progress: [{ label: t('changemanagement.act_implementado'), next: 'implemented' }],
    implemented: [{ label: t('changemanagement.act_cerrar_exito'), next: 'closed_success' }, { label: t('changemanagement.act_cerrar_fallo'), next: 'closed_failed' }],
  }

  const handleAction = (c: ChangeItem, action: StatusAction) => {
    if (action.action === 'open') { setDetail(c); return }
    if (action.action === 'approve') { approve({ id: c.id, approved: true }); return }
    if (action.action === 'reject') { approve({ id: c.id, approved: false }); return }
    changesApi.update(c.id, { status: action.next })
      .then(() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success(t('changemanagement.estado_actualizado')) })
        .catch((e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)))
  }

  const nuevo = <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('changemanagement.nuevo_change_request_2')}</Button>

  return (
    <div className="u-stack-16">
      <Tabs
        ariaLabel={t('changemanagement.vistas')}
        active={vista}
        onChange={id => setVista(id as typeof vista)}
        items={[
          { id: 'list', label: ts('sd_cfg.chg_list'), icon: <List size={14} /> },
          { id: 'calendar', label: ts('sd_cfg.chg_calendar'), icon: <CalendarDays size={14} /> },
          { id: 'releases', label: ts('sd_cfg.chg_releases'), icon: <Package size={14} /> },
          { id: 'blackouts', label: ts('sd_cfg.chg_blackouts'), icon: <Snowflake size={14} /> },
          { id: 'cab', label: ts('sd_mercado.panel_cab'), icon: <Users size={14} /> },
        ]}
      />
      {vista === 'calendar' && <CalendarioCambios onOpen={abrir} />}
      {vista === 'releases' && <Versiones onOpen={abrir} />}
      {vista === 'blackouts' && <Congelaciones />}
      {vista === 'cab' && <PanelDelCab onOpen={abrir} />}
      {vista === 'list' && <>
      <div className="chgm-toolbar">
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} aria-label={t('changemanagement.filtrar_estado')} className="ds-input chgm-filter">
          <option value="">{t('changemanagement.todos_los_estados')}</option>
          {ESTADOS_FILTRO.map(s => <option key={s} value={s}>{etiquetaSd('chg_st', s)}</option>)}
        </select>
        {nuevo}
      </div>

      {isLoading ? <Spinner /> : changes.length === 0
        ? <EmptyState icon={<GitPullRequest size={28} />} title={t('changemanagement.sin_cambios_registrados')} description={t('changemanagement.sin_cambios_desc')} action={filterStatus ? undefined : nuevo} />
        : <div className="u-scroll-x">
          <table className="u-table">
            <thead><tr className="chgm-head-row"><th aria-sort={ariaSort(changeSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.numero')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.titulo_2')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'change_type')} className="u-cell-nowrap"><SortableTH col="change_type" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.tipo')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'risk')} className="u-cell-nowrap"><SortableTH col="risk" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.riesgo')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.estado')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'planned_start')} className="u-cell-nowrap"><SortableTH col="planned_start" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.inicio_planif')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'owner')} className="u-cell-nowrap"><SortableTH col="owner" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.owner')}</SortableTH></th><th className="chgm-th-plain">{t('changemanagement.acciones')}</th></tr></thead>
            <tbody>
              {sortedChanges.map(c => {
                const actions = STATUS_ACTIONS[c.status ?? ''] || []
                return (
                  <tr key={c.id} className="u-border-b">
                    <td className="chgm-td chgm-td--number">{c.number}</td>
                    <td className="chgm-td chgm-td--title"><button type="button" onClick={() => setDetail(c)} className="chgm-title-btn" title={c.title}>{c.title}</button></td>
                    <td className="chgm-td chgm-td--muted-xs">{etiquetaSd('chg_type', c.change_type)}</td>
                    <td className="chgm-td"><RiesgoBadge risk={c.risk} /></td>
                    <td className="chgm-td"><EstadoBadge status={c.status} /></td>
                    <td className="chgm-td chgm-td--muted-xs">{fmtDateTime(c.planned_start)}</td>
                    <td className="chgm-td chgm-td--owner">{c.owner || '—'}</td>
                    <td className="chgm-td"><div className="chgm-row-actions">
                      <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditing(c)}>{t('changemanagement.editar')}</Button>
                      {actions.map(a => <Button size="xs" variant="secondary" key={a.label} onClick={() => handleAction(c, a)}>{a.label}</Button>)}
                    </div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>}

      </>}
      {showNew && <NewChangeModal onClose={() => setShowNew(false)} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); setShowNew(false); toast.success(t('changemanagement.cr_creado')) }} />}
      {editing && <ChangeEditModal change={editing} onClose={() => setEditing(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); setEditing(null); toast.success(t('changemanagement.cr_actualizado')) }} />}
      {detail && <ChangeDetailPanel change={detail} onClose={() => setDetail(null)} onEdit={() => { setEditing(detail); setDetail(null) }} onAction={handleAction} statusActions={STATUS_ACTIONS} />}
    </div>
  )
}
