import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, deliverablesApi } from '../services/api'
import type { Entregable } from '../services/api/tipos-alm'
import { Button, Modal, Spinner, EmptyState, useSort, SortableTH, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Package } from 'lucide-react'
import { fmtDate, fmtNumber, extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'
import { FULL_LIST_SIZE } from '../constants/pagination'
import './DeliverablesPage.css'

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
}

interface UserItem {
  id: string | number
  full_name?: string
}

interface DeliverableFormState {
  name: string
  description: string
  format: string
  planned_date: string
  owner_id: string
  client_contact: string
  acceptance_criteria: string
  sort_order: number
}

/** Estados del entregable; la etiqueta es `deliverables.estado_<clave>`. */
const STATUS_CFG = {
  planned:     { color: 'var(--text-2)', icon: '📋' },
  in_progress: { color: 'var(--accent)', icon: '🔄' },
  in_review:   { color: 'var(--warning)', icon: '👁' },
  delivered:   { color: 'var(--purple)', icon: '📤' },
  accepted:    { color: 'var(--success)', icon: '✅' },
  rejected:    { color: 'var(--danger)', icon: '❌' },
}
type EstadoEntregable = keyof typeof STATUS_CFG
const estadoDe = (s?: string | null): EstadoEntregable => (s && s in STATUS_CFG ? s : 'planned') as EstadoEntregable
const colorVar = (color: string) => ({ '--dlv-color': color } as CSSProperties)

function StatusDropdown({ del, onUpdate }: { del: Entregable; onUpdate: (status: string) => void }) {
  const t = useAppT()
  const [open, setOpen] = useState(false)
  const estado = estadoDe(del.status)
  const cfg = STATUS_CFG[estado]
  return (
    <div className="dlv-status">
      <button type="button" className="dlv-status__btn" style={colorVar(cfg.color)}
        aria-haspopup="menu" aria-expanded={open}
        onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}
        aria-label={t('deliverables.cambiar_estado', { estado: t(`deliverables.estado_${estado}`) })}
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}>
        <span aria-hidden="true">{cfg.icon}</span> {t(`deliverables.estado_${estado}`)} <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <>
          <div role="presentation" className="dlv-status__backdrop" onMouseDown={() => setOpen(false)} />
          <div className="dlv-status__menu" role="menu" tabIndex={-1} onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}>
            {(Object.keys(STATUS_CFG) as EstadoEntregable[]).map((s) => (
              <button key={s} type="button" role="menuitemradio" aria-checked={del.status === s} className="dlv-status__item"
                onClick={() => { onUpdate(s); setOpen(false) }}>
                <span aria-hidden="true">{STATUS_CFG[s].icon}</span> {t(`deliverables.estado_${s}`)}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function DeliverableFormModal({ del, projectId, onClose }: { del?: Entregable | null; projectId: string; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!del?.id
  const { data: usersRaw = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list({ page_size: FULL_LIST_SIZE }).then(r => r.data) })
  const users = usersRaw as UserItem[]
  const [form, setForm] = useState<DeliverableFormState>({
    name: del?.name || '',
    description: del?.description || '',
    format: del?.format || '',
    planned_date: del?.planned_date || '',
    owner_id: del?.owner_id != null ? String(del.owner_id) : '',
    client_contact: del?.client_contact || '',
    acceptance_criteria: del?.acceptance_criteria || '',
    sort_order: del?.sort_order || 0,
  })
  const set = <K extends keyof DeliverableFormState>(k: K) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value as DeliverableFormState[K] }))

  const { mutate, isPending } = useMutation({
    mutationFn: (data: DeliverableFormState) => isEdit ? deliverablesApi.updateInProject(projectId, del!.id, data) : deliverablesApi.createForProject(projectId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deliverables', projectId] }); qc.invalidateQueries({ queryKey: ['deliverables-overview'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open title={isEdit ? t('deliverables.editar_entregable') : t('deliverables.nuevo_entregable')} onClose={onClose} width={560}>
      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idCampo}-eta139`} htmlFor={`${idCampo}-a139`} className="dlv-label">{t('deliverables.nombre_obligatorio')}</label>
          <input id={`${idCampo}-a139`} aria-labelledby={`${idCampo}-eta139`} value={form.name} onChange={set('name')} className="dlv-input" placeholder={t('deliverables.nombre_del_entregable')} />
        </div>
        <div>
          <label id={`${idCampo}-eta143`} htmlFor={`${idCampo}-a143`} className="dlv-label">{t('deliverables.formato')}</label>
          <input id={`${idCampo}-a143`} aria-labelledby={`${idCampo}-eta143`} value={form.format} onChange={set('format')} className="dlv-input" placeholder={t('deliverables.formato_de_entrega')} />
        </div>
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="dlv-label">{t('deliverables.fecha_planificada')}</label>
          <DateInput id={`${idCampo}-1`} value={form.planned_date} onChange={set('planned_date')} className="dlv-input" />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="dlv-label">{t('deliverables.responsable')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.owner_id} onChange={set('owner_id')} className="dlv-input">
            <option value="">{t('deliverables.sin_asignar')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label id={`${idCampo}-eta158`} htmlFor={`${idCampo}-a158`} className="dlv-label">{t('deliverables.contacto_cliente')}</label>
          <input id={`${idCampo}-a158`} aria-labelledby={`${idCampo}-eta158`} value={form.client_contact} onChange={set('client_contact')} className="dlv-input" placeholder={t('deliverables.contacto_del_cliente')} />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="dlv-label">{t('deliverables.descripcion')}</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.description} onChange={set('description')} rows={2} className="dlv-input" />
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="dlv-label">{t('deliverables.criterios_de_aceptacion')}</label>
          <textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.acceptance_criteria} onChange={set('acceptance_criteria')} rows={2} className="dlv-input" placeholder={t('deliverables.criterios_de_aceptacion')} />
        </div>
        <div className="dlv-form-footer">
          <Button variant="secondary" onClick={onClose}>{t('deliverables.cancelar')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name} loading={isPending}>
            {isPending ? t('deliverables.guardando') : isEdit ? t('deliverables.guardar') : t('deliverables.crear_entregable')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function DeliverablesPage(): JSX.Element {
  const t = useAppT()
  const toast = useToast()
  const { hasRole } = useAuth()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing, setEditing] = useState<Entregable | null>(null)
  const [tab, setTab] = useState<'project' | 'overview'>('project')

  const { data: projectsRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list({}).then(r => r.data) })
  const projects = projectsRaw as ProjectItem[]

  const { data: delivData, isLoading } = useQuery({
    queryKey: ['deliverables', selectedProject],
    queryFn: () => deliverablesApi.listByProject(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: overview = [] } = useQuery({
    queryKey: ['deliverables-overview'],
    queryFn: () => deliverablesApi.overviewAll().then(r => r.data),
    enabled: tab === 'overview',
  })

  const { mutate: updateStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string | number; status: string }) => deliverablesApi.updateInProject(selectedProject, id, { status }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deliverables', selectedProject] }); qc.invalidateQueries({ queryKey: ['deliverables-overview'] }); qc.invalidateQueries({ queryKey: ['deliverables-uat'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: accept } = useMutation({
    mutationFn: (id: string | number) => deliverablesApi.accept(selectedProject, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deliverables', selectedProject] }); qc.invalidateQueries({ queryKey: ['deliverables-overview'] }); qc.invalidateQueries({ queryKey: ['deliverables-uat'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: reject } = useMutation({
    mutationFn: ({ id, reason }: { id: string | number; reason: string }) => deliverablesApi.reject(selectedProject, id, reason),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deliverables', selectedProject] }); qc.invalidateQueries({ queryKey: ['deliverables-overview'] }); qc.invalidateQueries({ queryKey: ['deliverables-uat'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string | number) => deliverablesApi.deleteFromProject(selectedProject, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['deliverables', selectedProject] }); qc.invalidateQueries({ queryKey: ['deliverables-overview'] }); qc.invalidateQueries({ queryKey: ['deliverables-uat'] }); },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const deliverables = delivData?.deliverables || []
  const summary = delivData?.summary
  const { sort: ovSort, setSort: setOvSort, sortedData: sortedOverview } = useSort(overview, 'name')

  return (
    <PageShell>
      <PageHeader icon={<Package size={18} />} title={t('deliverables.title')} subtitle={t('deliverables.subtitle')} />

      <Tabs
        items={[
          { id: 'project',  label: t('deliverables.tab_por_proyecto'), icon: '📁' },
          { id: 'overview', label: t('deliverables.tab_vista_global'), icon: '🌐' },
        ]}
        active={tab}
        onChange={(id) => setTab(id as 'project' | 'overview')}
        className="deliv-tabs"
      />

      {tab === 'project' && (
        <>
          <div className="dlv-toolbar">
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              className="dlv-project-select" aria-label={t('deliverables.proyecto')}>
              <option value="">{t('deliverables.seleccionar_proyecto')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && hasRole('admin', 'pm') && <Button onClick={() => setShowCreate(true)} icon="＋">{t('deliverables.new_deliverable')}</Button>}
          </div>

          {selectedProject && (summary?.total ?? 0) > 0 && (
            <div className="dlv-kpis">
              {[
                { key: 'kpi_total', value: fmtNumber(summary.total, 0), color: 'var(--text-2)' },
                { key: 'kpi_aceptados', value: fmtNumber(summary.accepted, 0), color: 'var(--success)' },
                { key: 'kpi_entregados', value: fmtNumber(summary.delivered, 0), color: 'var(--purple)' },
                { key: 'kpi_en_retraso', value: fmtNumber(summary.overdue, 0), color: 'var(--danger)' },
                { key: 'kpi_completado', value: `${fmtNumber(summary.completion_pct, 0)}%`, color: 'var(--accent)' },
              ].map(({ key, value, color }) => (
                <div key={key} className="dlv-kpi">
                  <div className="dlv-kpi__value" style={colorVar(color)}>{value}</div>
                  <div className="dlv-kpi__label">{t(`deliverables.${key}`)}</div>
                </div>
              ))}
            </div>
          )}

          {!selectedProject ? (
            <EmptyState icon="📦" title={t('deliverables.selecciona_un_proyecto')} description={t('deliverables.elige_proyecto_desc')} />
          ) : isLoading ? <Spinner /> : deliverables.length === 0 ? (
            <EmptyState icon="📦" title={t('deliverables.no_deliverables')} description={t('deliverables.sin_entregables_desc')} />
          ) : (
            <div className="u-stack-10">
              {deliverables.map(d => {
                const cfg = STATUS_CFG[estadoDe(d.status)]
                return (
                  <div key={d.id} className={d.overdue ? 'dlv-card dlv-card--overdue' : 'dlv-card'} style={colorVar(cfg.color)}>
                    <div className="dlv-card__body">
                      <div className="u-flex1">
                        <div className="dlv-card__head">
                          <span className="u-text2-mono-xs">{d.code}</span>
                          <span className="u-md-700">{d.name}</span>
                          {d.format && <span className="dlv-card__format">{d.format}</span>}
                          {d.overdue && <span className="dlv-overdue"><span aria-hidden="true">⚠ </span>{t('deliverables.en_retraso')}</span>}
                        </div>
                        {d.description && <p className="dlv-card__desc">{d.description}</p>}
                        <div className="dlv-card__dates">
                          {d.planned_date && <span className={d.overdue ? 'dlv-date--overdue' : undefined}><span aria-hidden="true">📅 </span>{t('deliverables.planificado_el', { fecha: fmtDate(d.planned_date) })}</span>}
                          {d.delivered_date && <span className="dlv-date--delivered"><span aria-hidden="true">📤 </span>{t('deliverables.entregado_el', { fecha: fmtDate(d.delivered_date) })}</span>}
                          {d.accepted_date && <span className="u-success"><span aria-hidden="true">✅ </span>{t('deliverables.aceptado_el', { fecha: fmtDate(d.accepted_date) })}</span>}
                          {d.owner_name && <span className="u-text2"><span aria-hidden="true">👤 </span>{d.owner_name}</span>}
                          {d.client_contact && <span className="u-text2"><span aria-hidden="true">🏢 </span>{d.client_contact}</span>}
                        </div>
                        {d.rejection_reason && <div className="dlv-card__rejection"><span aria-hidden="true">💬 </span>{d.rejection_reason}</div>}
                        {d.acceptance_criteria && <div className="dlv-card__criteria"><span aria-hidden="true">✓ </span>{d.acceptance_criteria}</div>}
                      </div>
                      <div className="dlv-card__actions">
                        <StatusDropdown del={d} onUpdate={(status) => updateStatus({ id: d.id, status })} />
                        <div className="u-row-6">
                          {d.status === 'delivered' && hasRole('admin', 'pm') && (
                            <>
                              <Button size="sm" onClick={() => accept(d.id)}>{t('deliverables.aceptar')}</Button>
                              <Button size="sm" variant="danger" onClick={async () => { const r = await pedirTexto({ title: t('deliverables.rechazar_titulo'), message: t('deliverables.rechazar_mensaje'), label: t('deliverables.rechazar_motivo'), required: true, multiline: true, danger: true, confirmLabel: t('deliverables.rechazar_confirmar') }); if (r) reject({ id: d.id, reason: r }) }}>{t('deliverables.rechazar')}</Button>
                            </>
                          )}
                          {hasRole('admin', 'pm') && <button type="button" className="dlv-icon-btn" onClick={() => setEditing(d)}
                            aria-label={t('deliverables.editar_n', { nombre: d.name })} title={t('deliverables.editar_n', { nombre: d.name })}><span aria-hidden="true">✏️</span></button>}
                          {hasRole('admin', 'pm') && <button type="button" className="dlv-icon-btn dlv-icon-btn--danger" onClick={() => { openConfirmGlobal({ message: t('deliverables.confirmar_eliminar'), onConfirm: () => del(d.id), danger: true }) }}
                            aria-label={t('deliverables.eliminar_n', { nombre: d.name })} title={t('deliverables.eliminar_n', { nombre: d.name })}><span aria-hidden="true">🗑</span></button>}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {tab === 'overview' && (
        overview.length === 0 ? (
          <EmptyState icon="📦" title={t('deliverables.sin_entregables_en_la_vista_global')} description={t('deliverables.sin_entregables_global_desc')} />
        ) : (
          <div className="ds-card ds-card--plano u-scroll-x">
            <div className="dlv-ov">
              <div className="dlv-ov__row dlv-ov__row--head">
                <SortableTH col="name" sort={ovSort} onSort={setOvSort}>{t('deliverables.col_entregable')}</SortableTH>
                <SortableTH col="project_code" sort={ovSort} onSort={setOvSort}>{t('deliverables.col_proyecto')}</SortableTH>
                <SortableTH col="owner_name" sort={ovSort} onSort={setOvSort}>{t('deliverables.col_responsable')}</SortableTH>
                <SortableTH col="planned_date" sort={ovSort} onSort={setOvSort}>{t('deliverables.col_planificado')}</SortableTH>
                <SortableTH col="delivered_date" sort={ovSort} onSort={setOvSort}>{t('deliverables.col_entregado')}</SortableTH>
                <SortableTH col="status" sort={ovSort} onSort={setOvSort}>{t('deliverables.col_estado')}</SortableTH>
              </div>
              {sortedOverview.map(d => {
                const estado = estadoDe(d.status)
                const cfg = STATUS_CFG[estado]
                return (
                  <div key={d.id} className="dlv-ov__row">
                    <div>
                      <div className="u-base-600">{d.name}</div>
                      {d.overdue && <span className="dlv-overdue dlv-overdue--sm"><span aria-hidden="true">⚠ </span>{t('deliverables.en_retraso')}</span>}
                    </div>
                    <span className="u-text2-sm">{d.project_code}</span>
                    <span className="u-sm">{d.owner_name || '—'}</span>
                    <span className={d.overdue ? 'dlv-ov__date dlv-ov__date--overdue' : 'dlv-ov__date'}>{d.planned_date ? fmtDate(d.planned_date) : '—'}</span>
                    <span className="dlv-ov__date dlv-ov__date--delivered">{d.delivered_date ? fmtDate(d.delivered_date) : '—'}</span>
                    <span className="dlv-ov__status" style={colorVar(cfg.color)}><span aria-hidden="true">{cfg.icon} </span>{t(`deliverables.estado_${estado}`)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      )}

      {showCreate && selectedProject && <DeliverableFormModal projectId={selectedProject} onClose={() => setShowCreate(false)} />}
      {editing && <DeliverableFormModal del={editing} projectId={String(editing.project_id || selectedProject)} onClose={() => setEditing(null)} />}
    </PageShell>
  )
}