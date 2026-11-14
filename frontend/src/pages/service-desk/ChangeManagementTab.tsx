import { useId, useState } from 'react'
import type { ChangeEvent, CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { changesApi, cmdbApi, sdChangePlanningApi } from '../../services/api'
import { CalendarioCambios, Congelaciones, PanelCab, Versiones } from './CambiosPlanificacion'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Spinner, EmptyState, Modal, useSort, SortableTH, ariaSort } from '../../components/ui'
import { COLOR, alpha } from '../../constants/theme'
import { useAppLang } from '../../i18n/AppLangContext'
import { useTabListKeys } from '../../components/ui/Tabs'
import { etiquetaSd } from './sdUtils'
import DateInput from '../../components/ui/DateInput'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'

type ChangeId = string | number
type ChangeRisk = 'low' | 'medium' | 'high' | 'critical' | string
type ChangeStatus =
  | 'draft'
  | 'submitted'
  | 'cab_review'
  | 'approved'
  | 'scheduled'
  | 'in_progress'
  | 'implemented'
  | 'post_review'
  | 'closed_success'
  | 'closed_failed'
  | 'cancelled'
  | string

interface ChangeItem {
  id: ChangeId
  number?: string
  title?: string
  status?: ChangeStatus
  risk?: ChangeRisk
  change_type?: string
  owner?: string
  requester?: string
  planned_start?: string
  planned_end?: string
  actual_start?: string
  actual_end?: string
  approved_at?: string
  downtime_minutes?: number
  description?: string
  business_justification?: string
  implementation_plan?: string
  rollback_plan?: string
  test_plan?: string
  impact_description?: string
  priority?: string
  affected_cis?: string[]
  release_id?: string | null
  rejected_reason?: string | null
}

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
  next?: ChangeStatus
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

  const c = (detail || change) as ChangeItem
  const sc = CHANGE_STATUS_COLOR[c.status ?? ''] || COLOR.text2
  const rc = c.risk === 'critical' ? COLOR.danger : c.risk === 'high' ? 'var(--orange)' : c.risk === 'medium' ? COLOR.warning : COLOR.success

  const Section = ({ title, content: text }: { title: string; content?: string }) => text ? (
    <div className="u-mb-16">
      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>{title}</div>
      <div style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', lineHeight: 1.6, whiteSpace: 'pre-wrap', background: 'var(--surface-1)', borderRadius: 8, padding: '10px 14px' }}>{text}</div>
    </div>
  ) : null

  const actions = statusActions[c.status || ''] || []

  return (
    <div style={{
      position: 'fixed', top: 12, right: 12, width: 560, maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100vh - 24px)',
      background: 'var(--surface-0)', border: '1px solid var(--surface-4)', borderRadius: 12,
      zIndex: 'var(--z-dropdown)', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '-8px 0 32px rgba(0,0,0,0.25)',
    }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)', background: 'var(--surface-1)', position: 'sticky', top: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, marginRight: 12 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 700 }}>{c.number}</span>
              <span style={{ fontSize: "var(--text-xs)", background: alpha(sc, '15'), color: sc, padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{etiquetaSd('chg_st', c.status)}</span>
              <span style={{ fontSize: "var(--text-xs)", color: rc, fontWeight: 600 }}>⚠ {c.risk}</span>
              <span className="u-text3-xs">{etiquetaSd('chg_type', c.change_type)}</span>
            </div>
            <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, color: 'var(--text-1)', lineHeight: 1.3 }}>{c.title}</div>
          </div>
          <button onClick={onClose} aria-label="Cerrar detalle" style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: "var(--text-xl)", cursor: 'pointer', lineHeight: 1, padding: '0 4px' }}>×</button>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button onClick={onEdit} style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>✏ Editar</button>
          {actions.map(a => (
            <button key={a.label} onClick={() => { onAction(c, a); onClose() }} style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: `1px solid ${alpha(a.color, '40')}`, background: alpha(a.color, '10'), color: a.color, fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>{a.label}</button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, padding: '20px', overflowY: 'auto' }}>
        {isLoading ? <Spinner /> : <>
          {c.rejected_reason && (
            <div role="status" style={{ border: `1px solid ${alpha(COLOR.danger, '50')}`, background: alpha(COLOR.danger, '10'), borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 'var(--text-sm)', color: COLOR.danger }}>{c.rejected_reason}</div>
          )}
          <PanelCab changeId={c.id} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 20 }}>
            {[
              ['Solicitante', c.requester || '—'],
              ['Owner', c.owner || '—'],
              ['Inicio planif.', fmtDate(c.planned_start)],
              ['Fin planif.', fmtDate(c.planned_end)],
              ['Inicio real', fmtDate(c.actual_start)],
              ['Fin real', fmtDate(c.actual_end)],
              ['Downtime', c.downtime_minutes ? `${c.downtime_minutes} min` : '—'],
              ['Aprobado', c.approved_at ? fmtDate(c.approved_at) : '—'],
            ].map(([label, val]) => (
              <div key={label} style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)', fontWeight: 500 }}>{val}</div>
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
  const { data: versiones = [] } = useQuery<{ id: string; name: string; version?: string | null; status: string }[]>({
    queryKey: ['sd-releases'], queryFn: () => sdChangePlanningApi.releases().then(r => r.data as { id: string; name: string; version?: string | null; status: string }[]),
  })
  const alternarCi = (id: string) => setForm(f => ({ ...f, affected_cis: (f.affected_cis ?? []).includes(id)
    ? (f.affected_cis ?? []).filter(x => x !== id) : [...(f.affected_cis ?? []), id] }))
  const { mutate, isPending } = useMutation({
    mutationFn: (data: ChangeFormData) => changesApi.update(change.id, data),
    onSuccess: onSaved,
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al guardar')),
  })
  const set = (k: keyof ChangeFormData) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const rawValue = e.target.value
    const nextValue = k === 'downtime_minutes' ? Number(rawValue) : rawValue
    setForm((f) => ({ ...f, [k]: nextValue }))
  }
  const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={`Editar ${change.number}`} onClose={onClose} size="lg">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, maxHeight: '70vh', overflowY: 'auto', paddingRight: 4 }}>
        <div className="u-col-full"><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} style={LS}>{t('changemanagement.titulo')}</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-change-type`} style={LS}>{t('changemanagement.tipo_de_cambio')}</label><select id={`${idPrefix}-change-type`} value={form.change_type} onChange={set('change_type')} style={IS}><option value="standard">Standard — pre-aprobado</option><option value="normal">Normal — requiere CAB</option><option value="emergency">Emergency — ECAB</option></select></div>
        <div><label htmlFor={`${idPrefix}-risk`} style={LS}>Riesgo</label><select id={`${idPrefix}-risk`} value={form.risk} onChange={set('risk')} style={IS}>{[['low', 'Bajo'], ['medium', 'Medio'], ['high', 'Alto'], ['critical', 'Crítico']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div><label htmlFor={`${idPrefix}-planned-start`} style={LS}>Inicio planificado</label><DateInput id={`${idPrefix}-planned-start`} withTime value={form.planned_start} onChange={set('planned_start')} style={IS} /></div>
        <div><label htmlFor={`${idPrefix}-planned-end`} style={LS}>Fin planificado</label><DateInput id={`${idPrefix}-planned-end`} withTime value={form.planned_end} onChange={set('planned_end')} style={IS} /></div>
        <div><label id={`${idPrefix}-downtime-et`} htmlFor={`${idPrefix}-downtime`} style={LS}>Downtime estimado (min)</label><input id={`${idPrefix}-downtime`} aria-labelledby={`${idPrefix}-downtime-et`} type="number" value={form.downtime_minutes} onChange={set('downtime_minutes')} style={IS} min="0" /></div>
        <div><label htmlFor={`${idPrefix}-release`} style={LS}>{ts('sd_cfg.chg_release')}</label>
          <select id={`${idPrefix}-release`} value={form.release_id ?? ''} onChange={e => setForm(f => ({ ...f, release_id: e.target.value || null }))} style={IS}>
            <option value="">{ts('sd_cfg.chg_none')}</option>
            {versiones.filter(v => v.status !== 'released' && v.status !== 'cancelled').map(v => <option key={v.id} value={v.id}>{v.name}{v.version ? ` ${v.version}` : ''}</option>)}
          </select></div>
        <div className="u-col-full"><span style={LS}>{ts('sd_cfg.chg_affected_cis')}</span>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', maxHeight: 140, overflowY: 'auto' }}>
            {cis.map(ci => {
              const on = (form.affected_cis ?? []).includes(ci.id)
              return <button key={ci.id} type="button" aria-pressed={on} onClick={() => alternarCi(ci.id)} style={{ padding: '4px 10px', borderRadius: 'var(--radius-full)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-xs)', border: `1px solid ${on ? 'var(--accent)' : 'var(--surface-4)'}`, background: on ? 'var(--accent-muted)' : 'transparent', color: on ? 'var(--accent)' : 'var(--text-2)' }}>{ci.code ? `${ci.code} · ` : ''}{ci.name}</button>
            })}
          </div></div>
        <div className="u-col-full"><label id={`${idPrefix}-description-et`} htmlFor={`${idPrefix}-description`} style={LS}>{t('changemanagement.descripcion_2')}</label><textarea id={`${idPrefix}-description`} aria-labelledby={`${idPrefix}-description-et`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div className="u-col-full"><label id={`${idPrefix}-business-justification-et`} htmlFor={`${idPrefix}-business-justification`} style={LS}>{t('changemanagement.justificacion_de_negocio')}</label><textarea id={`${idPrefix}-business-justification`} aria-labelledby={`${idPrefix}-business-justification-et`} value={form.business_justification} onChange={set('business_justification')} rows={2} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label id={`${idPrefix}-implementation-plan-et`} htmlFor={`${idPrefix}-implementation-plan`} style={LS}>{t('changemanagement.plan_de_implementacion')}</label><textarea id={`${idPrefix}-implementation-plan`} aria-labelledby={`${idPrefix}-implementation-plan-et`} value={form.implementation_plan} onChange={set('implementation_plan')} rows={4} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label id={`${idPrefix}-rollback-plan-et`} htmlFor={`${idPrefix}-rollback-plan`} style={LS}>{t('changemanagement.plan_de_rollback')}</label><textarea id={`${idPrefix}-rollback-plan`} aria-labelledby={`${idPrefix}-rollback-plan-et`} value={form.rollback_plan} onChange={set('rollback_plan')} rows={4} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label id={`${idPrefix}-test-plan-et`} htmlFor={`${idPrefix}-test-plan`} style={LS}>{t('changemanagement.plan_de_pruebas')}</label><textarea id={`${idPrefix}-test-plan`} aria-labelledby={`${idPrefix}-test-plan-et`} value={form.test_plan} onChange={set('test_plan')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label id={`${idPrefix}-impact-description-et`} htmlFor={`${idPrefix}-impact-description`} style={LS}>{t('changemanagement.descripcion_de_impacto')}</label><textarea id={`${idPrefix}-impact-description`} aria-labelledby={`${idPrefix}-impact-description-et`} value={form.impact_description} onChange={set('impact_description')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10 }}><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>Guardar cambios</Button></div>
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
  const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const LS: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <Modal open title={t('changemanagement.nuevo_change_request')} onClose={onClose} size="lg">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="u-col-full"><label id={`${idPrefix}-title-et`} htmlFor={`${idPrefix}-title`} style={LS}>{t('changemanagement.titulo')}</label><input id={`${idPrefix}-title`} aria-labelledby={`${idPrefix}-title-et`} value={form.title} onChange={set('title')} style={IS} placeholder={t('changemanagement.titulo_del_cambio')} /></div>
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={LS}>{t('changemanagement.tipo_de_cambio')}</label><select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.change_type} onChange={set('change_type')} style={IS}><option value="standard">Standard — pre-aprobado</option><option value="normal">Normal — requiere CAB</option><option value="emergency">Emergency — ECAB</option></select></div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={LS}>Riesgo</label><select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.risk} onChange={set('risk')} style={IS}><option value="low">Bajo</option><option value="medium">Medio</option><option value="high">Alto</option><option value="critical">{t('changemanagement.critico')}</option></select></div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={LS}>Inicio planificado</label><DateInput id={`${idCampo}-3`} withTime value={form.planned_start} onChange={set('planned_start')} style={IS} /></div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={LS}>Fin planificado</label><DateInput id={`${idCampo}-4`} withTime value={form.planned_end} onChange={set('planned_end')} style={IS} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={LS}>{t('changemanagement.descripcion_2')}</label><textarea id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.description} onChange={set('description')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div className="u-col-full"><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={LS}>{t('changemanagement.justificacion_de_negocio')}</label><textarea id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.business_justification} onChange={set('business_justification')} rows={2} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={LS}>{t('changemanagement.plan_de_implementacion')}</label><textarea id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.implementation_plan} onChange={set('implementation_plan')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={LS}>{t('changemanagement.plan_de_rollback')}</label><textarea id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.rollback_plan} onChange={set('rollback_plan')} rows={3} style={{ ...IS, resize: 'vertical' }} /></div>
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button onClick={() => mutate(form)} disabled={isPending || !form.title || !form.description} loading={isPending}>Crear Change Request</Button></div>
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

  const { data: changesRaw = [], isLoading } = useQuery({
    queryKey: ['sd-changes', filterStatus],
    queryFn: () => changesApi.list({ status: filterStatus || undefined }).then(r => r.data),
  })
  const changes = changesRaw as ChangeItem[]

  const { mutate: approve } = useMutation({
    mutationFn: ({ id, approved }: { id: ChangeId; approved: boolean }) => changesApi.approve(id, { approved }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success('Change actualizado') },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al actualizar')),
  })

  const { sort: changeSort, setSort: setChangeSort, sortedData: sortedChanges } = useSort(changes, 'number')

  const IS: CSSProperties = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }

  const STATUS_ACTIONS: Record<string, StatusAction[]> = {
    draft: [{ label: 'Enviar a revisión', next: 'submitted', color: COLOR.accent }],
    submitted: [{ label: 'Enviar a CAB', next: 'cab_review', color: COLOR.warning }],
    // Se vota en el panel del cambio: cada miembro del CAB, con motivo si es en contra.
    cab_review: [{ label: ts('sd_cfg.chg_cab'), action: 'open', color: COLOR.warning }],
    approved: [{ label: 'Programar', next: 'scheduled', color: COLOR.accent }],
    scheduled: [{ label: 'Iniciar', next: 'in_progress', color: COLOR.accent }],
    in_progress: [{ label: 'Implementado', next: 'implemented', color: COLOR.success }],
    implemented: [{ label: 'Cerrar éxito', next: 'closed_success', color: COLOR.success }, { label: 'Cerrar fallo', next: 'closed_failed', color: COLOR.danger }],
  }

  const VISTAS = ['list', 'calendar', 'releases', 'blackouts'] as const
  const teclas = useTabListKeys([...VISTAS], vista, id => setVista(id as typeof vista))

  const handleAction = (c: ChangeItem, action: StatusAction) => {
    if (action.action === 'open') { setDetail(c); return }
    if (action.action === 'approve') { approve({ id: c.id, approved: true }); return }
    if (action.action === 'reject') { approve({ id: c.id, approved: false }); return }
    changesApi.update(c.id, { status: action.next })
      .then(() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); toast.success('Estado actualizado') })
        .catch((e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)))
  }

  return (
    <div>
      <div ref={teclas.listRef} onKeyDown={teclas.onKeyDown} role="tablist" aria-label={ts('sd_cfg.chg_calendar')} style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {VISTAS.map(v => (
          <button key={v} type="button" role="tab" data-tab-id={v} tabIndex={v === teclas.focusId ? 0 : -1} aria-selected={vista === v} onClick={() => setVista(v)}
            style={{ padding: '6px 14px', borderRadius: 8, cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)', fontWeight: 600,
              border: `1px solid ${vista === v ? 'var(--accent)' : 'var(--surface-4)'}`, background: vista === v ? 'var(--accent-muted)' : 'transparent',
              color: vista === v ? 'var(--accent)' : 'var(--text-2)' }}>{ts(`sd_cfg.chg_${v}`)}</button>
        ))}
      </div>
      {vista === 'calendar' && <CalendarioCambios onOpen={abrir} />}
      {vista === 'releases' && <Versiones onOpen={abrir} />}
      {vista === 'blackouts' && <Congelaciones />}
      {vista === 'list' && <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div className="u-row-10"><select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={IS}><option value="">{t('changemanagement.todos_los_estados')}</option>{['draft', 'submitted', 'cab_review', 'approved', 'scheduled', 'in_progress', 'implemented', 'post_review', 'closed_success', 'closed_failed'].map(s => <option key={s} value={s}>{etiquetaSd('chg_st', s)}</option>)}</select></div>
        <Button onClick={() => setShowNew(true)}>{t('changemanagement.nuevo_change_request_2')}</Button>
      </div>

      {isLoading ? <Spinner /> : changes.length === 0 ? <EmptyState icon="🔄" title={t('changemanagement.sin_cambios_registrados')} description="Crea el primer change request para iniciar el flujo de gestión de cambios." /> :
        <div className="u-scroll-x">
          <table className="u-table">
            <thead><tr style={{ borderBottom: '2px solid var(--surface-4)' }}><th aria-sort={ariaSort(changeSort, 'number')} className="u-cell-nowrap"><SortableTH col="number" sort={changeSort} onSort={setChangeSort}>Nº</SortableTH></th><th aria-sort={ariaSort(changeSort, 'title')} className="u-cell-nowrap"><SortableTH col="title" sort={changeSort} onSort={setChangeSort}>{t('changemanagement.titulo_2')}</SortableTH></th><th aria-sort={ariaSort(changeSort, 'change_type')} className="u-cell-nowrap"><SortableTH col="change_type" sort={changeSort} onSort={setChangeSort}>Tipo</SortableTH></th><th aria-sort={ariaSort(changeSort, 'risk')} className="u-cell-nowrap"><SortableTH col="risk" sort={changeSort} onSort={setChangeSort}>Riesgo</SortableTH></th><th aria-sort={ariaSort(changeSort, 'status')} className="u-cell-nowrap"><SortableTH col="status" sort={changeSort} onSort={setChangeSort}>Estado</SortableTH></th><th aria-sort={ariaSort(changeSort, 'planned_start')} className="u-cell-nowrap"><SortableTH col="planned_start" sort={changeSort} onSort={setChangeSort}>Inicio planif.</SortableTH></th><th aria-sort={ariaSort(changeSort, 'owner')} className="u-cell-nowrap"><SortableTH col="owner" sort={changeSort} onSort={setChangeSort}>Owner</SortableTH></th><th style={{ padding: '10px 8px', whiteSpace: 'nowrap', fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase' }}>Acciones</th></tr></thead>
            <tbody>
              {sortedChanges.map(c => {
                const sc = CHANGE_STATUS_COLOR[c.status ?? ''] || COLOR.text2
                const rc = c.risk === 'critical' ? COLOR.danger : c.risk === 'high' ? 'var(--orange)' : c.risk === 'medium' ? COLOR.warning : COLOR.success
                const actions = STATUS_ACTIONS[c.status ?? ''] || []
                return (
                  <tr key={c.id} className="u-border-b">
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: 'var(--accent)', fontWeight: 600 }}>{c.number}</td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-base)", color: 'var(--text-1)', maxWidth: 220 }}><button onClick={() => setDetail(c)} style={{ background: 'none', border: 'none', color: 'var(--text-1)', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', fontSize: "var(--text-base)", padding: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 220 }}>{c.title}</button></td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{etiquetaSd('chg_type', c.change_type)}</td>
                    <td style={{ padding: '10px 8px' }}><span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: rc }}>{c.risk}</span></td>
                    <td style={{ padding: '10px 8px' }}><span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: sc, background: alpha(sc, '15'), padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap' }}>{etiquetaSd('chg_st', c.status)}</span></td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{fmtDate(c.planned_start)}</td>
                    <td style={{ padding: '10px 8px', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{c.owner || '—'}</td>
                    <td style={{ padding: '10px 8px' }}><div style={{ display: 'flex', gap: 4, flexWrap: 'nowrap' }}><button onClick={() => setEditing(c)} style={{ padding: '3px 8px', borderRadius: 5, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>✏ Editar</button>{actions.map(a => <button key={a.label} onClick={() => handleAction(c, a)} style={{ padding: '3px 8px', borderRadius: 5, border: `1px solid ${alpha(a.color, '40')}`, background: alpha(a.color, '10'), color: a.color, fontSize: "var(--text-2xs)", cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>{a.label}</button>)}</div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>}

      </>}
      {showNew && <NewChangeModal onClose={() => setShowNew(false)} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); setShowNew(false); toast.success('Change request creado') }} />}
      {editing && <ChangeEditModal change={editing} onClose={() => setEditing(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ['sd-changes'] }); setEditing(null); toast.success('Change request actualizado') }} />}
      {detail && <ChangeDetailPanel change={detail} onClose={() => setDetail(null)} onEdit={() => { setEditing(detail); setDetail(null) }} onAction={handleAction} statusActions={STATUS_ACTIONS} />}
    </div>
  )
}
