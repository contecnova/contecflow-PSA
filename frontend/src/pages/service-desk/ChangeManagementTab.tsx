import { useId, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { changesApi, cmdbApi, sdChangePlanningApi } from '../../services/api'
import type { CambioItsm, CambioItsmDetalle, EstadoDeCambio } from '../../services/api/tipos-cambios'
import { CalendarioCambios, Congelaciones, PanelCab, Versiones } from './CambiosPlanificacion'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH, ariaSort } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { useTabListKeys } from '../../components/ui/Tabs'
import { etiquetaSd } from './sdUtils'
import DateInput from '../../components/ui/DateInput'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import './ChangeManagementTab.css'

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
  color: string
  next?: EstadoDeCambio
  action?: 'approve' | 'reject' | 'open'
}

const CHANGE_STATUS_COLOR: Record<string, string> = {
  draft: COLOR.text2,
  submitted: COLOR.accent,
  cab_review: COLOR.warning,
  approved: COLOR.success,
  scheduled: 'var(--sky-blue)',
  in_progress: COLOR.accent,
  implemented: COLOR.success,
  post_review: COLOR.warning,
  closed_success: COLOR.success,
  closed_failed: COLOR.danger,
  cancelled: COLOR.text3,
}

const RISKS = ['low', 'medium', 'high', 'critical'] as const
const CHANGE_TYPES = ['standard', 'normal', 'emergency'] as const

/** Color del dato (estado, riesgo, accion) para las clases `.chgm-*` que lo leen. */
const colorVar = (c: string) => ({ '--chgm-c': c } as CSSProperties)

const riskColor = (risk?: string | null) =>
  risk === 'critical' ? COLOR.danger : risk === 'high' ? 'var(--orange)' : risk === 'medium' ? COLOR.warning : COLOR.success

function fmtDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString(localeActivo(), { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
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
  const sc = CHANGE_STATUS_COLOR[c.status ?? ''] || COLOR.text2
  const rc = riskColor(c.risk)

  const Section = ({ title, content: text }: { title: string; content?: string }) => text ? (
    <div className="u-mb-16">
      <div className="chgm-sec__title">{title}</div>
      <div className="chgm-sec__body">{text}</div>
    </div>
  ) : null

  const actions = statusActions[c.status || ''] || []

  return (
    <div className="chgm-panel">
      <div className="chgm-panel__head">
        <div className="chgm-panel__top">
          <div className="chgm-panel__titlebox">
            <div className="chgm-panel__meta">
              <span className="chgm-panel__number">{c.number}</span>
              <span className="chgm-badge" style={colorVar(sc)}>{etiquetaSd('chg_st', c.status)}</span>
              {c.risk && <span className="chgm-risk" style={colorVar(rc)}>⚠ {t(`changemanagement.risk_${c.risk}`)}</span>}
              <span className="u-text3-xs">{etiquetaSd('chg_type', c.change_type)}</span>
            </div>
            <div className="chgm-panel__title">{c.title}</div>
          </div>
          <button type="button" onClick={onClose} aria-label={t('changemanagement.cerrar_detalle')} className="chgm-panel__close"><span aria-hidden="true">×</span></button>
        </div>
        <div className="chgm-panel__actions">
          <button type="button" onClick={onEdit} className="chgm-btn"><span aria-hidden="true">✏</span> {t('changemanagement.editar')}</button>
          {actions.map(a => (
            <button type="button" key={a.label} onClick={() => { onAction(c, a); onClose() }} className="chgm-btn chgm-btn--action" style={colorVar(a.color)}>{a.label}</button>
          ))}
        </div>
      </div>

      <div className="chgm-panel__body">
        {isLoading ? <Spinner /> : <>
          {c.rejected_reason && (
            <div role="status" className="chgm-rejected">{c.rejected_reason}</div>
          )}
          <PanelCab changeId={c.id} />
          <div className="chgm-facts">
            {[
              ['solicitante', c.requester || '—'],
              ['owner', c.owner || '—'],
              ['inicio_planif', fmtDate(c.planned_start)],
              ['fin_planif', fmtDate(c.planned_end)],
              ['inicio_real', fmtDate(c.actual_start)],
              ['fin_real', fmtDate(c.actual_end)],
              ['downtime', c.downtime_minutes ? t('changemanagement.n_min', { n: c.downtime_minutes }) : '—'],
              ['aprobado', c.approved_at ? fmtDate(c.approved_at) : '—'],
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

const IS = 'chgm-input chgm-input--block'

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
  const [vista, setVista] = useState<'list' | 'calendar' | 'releases' | 'blackouts'>('list')
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
    draft: [{ label: t('changemanagement.act_enviar_revision'), next: 'submitted', color: COLOR.accent }],
    submitted: [{ label: t('changemanagement.act_enviar_cab'), next: 'cab_review', color: COLOR.warning }],
    // Se vota en el panel del cambio: cada miembro del CAB, con motivo si es en contra.
    cab_review: [{ label: ts('sd_cfg.chg_cab'), action: 'open', color: COLOR.warning }],
    approved: [{ label: t('changemanagement.act_programar'), next: 'scheduled', color: COLOR.accent }],
    scheduled: [{ label: t('changemanagement.act_iniciar'), next: 'in_progress', color: COLOR.accent }],
    in_progress: [{ label: t('changemanagement.act_implementado'), next: 'implemented', color: COLOR.success }],
    implemented: [{ label: t('changemanagement.act_cerrar_exito'), next: 'closed_success', color: COLOR.success }, { label: t('changemanagement.act_cerrar_fallo'), next: 'closed_failed', color: COLOR.danger }],
  }

  const VISTAS = ['list', 'calendar', 'releases', 'blackouts'] as const
  const teclas = useTabListKeys([...VISTAS], vista, id => setVista(id as typeof vista))

  const handleAction = (c: ChangeItem, action: StatusAction) => {
    if (action.action === 'open') { setDetail(c); return }
    if (action.action === 'approve') { approve({ id: c.id, approved: true }); return }
    if (action.action === 'reject') { approve({ id: c.id, approved: false }); return }
    changesApi.update(c.id, { status: action.next })
      .then(() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success(t('changemanagement.estado_actualizado')) })
        .catch((e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)))
  }

  return (
    <div>
      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} role="tablist" aria-label={ts('sd_cfg.chg_calendar')} className="chgm-tabs">
        {VISTAS.map(v => (
          <button key={v} type="button" role="tab" data-tab-id={v} tabIndex={v === teclas.focusId ? 0 : -1} aria-selected={vista === v} onClick={() => setVista(v)}
            className="chgm-tab">{ts(`sd_cfg.chg_${v}`)}</button>
        ))}
      </div>
      {vista === 'calendar' && <CalendarioCambios onOpen={abrir} />}
      {vista === 'releases' && <Versiones onOpen={abrir} />}
      {vista === 'blackouts' && <Congelaciones />}
      {vista === 'list' && <>
      <div className="u-row-between u-mb-20">
        <div className="u-row-10"><select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} aria-label={t('changemanagement.filtrar_estado')} className="chgm-input"><option value="">{t('changemanagement.todos_los_estados')}</option>{['draft', 'submitted', 'cab_review', 'approved', 'scheduled', 'in_progress', 'implemented', 'post_review', 'closed_success', 'closed_failed'].map(s => <option key={s} value={s}>{etiquetaSd('chg_st', s)}</option>)}</select></div>
        <Button onClick={() => setShowNew(true)}>{t('changemanagement.nuevo_change_request_2')}</Button>
      </div>

      {isLoading ? <Spinner /> : changes.length === 0 ? <EmptyState icon="🔄" title={t('changemanagement.sin_cambios_registrados')} description={t('changemanagement.sin_cambios_desc')} /> :
        <div className="u-scroll-x">
          <table className="u-table">
            <thead><tr className="chgm-head-row"><th aria-sort={ariaSort(changeSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.numero')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.titulo_2')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'change_type')} className="u-cell-nowrap"><SortableTH col="change_type" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.tipo')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'risk')} className="u-cell-nowrap"><SortableTH col="risk" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.riesgo')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.estado')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'planned_start')} className="u-cell-nowrap"><SortableTH col="planned_start" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.inicio_planif')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'owner')} className="u-cell-nowrap"><SortableTH col="owner" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.owner')}</SortableTH></th><th className="chgm-th-plain">{t('changemanagement.acciones')}</th></tr></thead>
            <tbody>
              {sortedChanges.map(c => {
                const sc = CHANGE_STATUS_COLOR[c.status ?? ''] || COLOR.text2
                const rc = riskColor(c.risk)
                const actions = STATUS_ACTIONS[c.status ?? ''] || []
                return (
                  <tr key={c.id} className="u-border-b">
                    <td className="chgm-td chgm-td--number">{c.number}</td>
                    <td className="chgm-td chgm-td--title"><button type="button" onClick={() => setDetail(c)} className="chgm-title-btn">{c.title}</button></td>
                    <td className="chgm-td chgm-td--muted-xs">{etiquetaSd('chg_type', c.change_type)}</td>
                    <td className="chgm-td">{c.risk && <span className="chgm-risk" style={colorVar(rc)}>{t(`changemanagement.risk_${c.risk}`)}</span>}</td>
                    <td className="chgm-td"><span className="chgm-badge chgm-badge--nowrap" style={colorVar(sc)}>{etiquetaSd('chg_st', c.status)}</span></td>
                    <td className="chgm-td chgm-td--muted-xs">{fmtDate(c.planned_start)}</td>
                    <td className="chgm-td chgm-td--owner">{c.owner || '—'}</td>
                    <td className="chgm-td"><div className="chgm-row-actions"><button type="button" onClick={() => setEditing(c)} className="chgm-btn-sm"><span aria-hidden="true">✏</span> {t('changemanagement.editar')}</button>{actions.map(a => <button type="button" key={a.label} onClick={() => handleAction(c, a)} className="chgm-btn-sm chgm-btn-sm--action" style={colorVar(a.color)}>{a.label}</button>)}</div></td>
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
