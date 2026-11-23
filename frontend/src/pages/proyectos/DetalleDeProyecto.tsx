/**
 * Ficha de proyecto en modal: resumen, miembros, fases, solicitudes y documentos.
 * Troceado de ProjectsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState, useMemo, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, portalApi } from '../../services/api'
import type { MemberAddPayload } from '../../services/api'
import {
  Badge, Button, Modal, Spinner, EmptyState, MarcaExterno, etiquetaDePersona, Pulsable, Select, Input, Textarea,
} from '../../components/ui'
import { Plus, Pencil, Users, Lightbulb, Coins, Clock, CalendarDays, MessageSquare, Layers, X } from 'lucide-react'
import DocumentsPanel from '../../components/DocumentsPanel'
import { fmtDate, fmtCurrency, extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAppT } from '../../i18n/AppLangContext'
import { z } from 'zod'
import { useFormValidation } from '../../hooks/useFormValidation'
import { alpha } from '../../constants/theme'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { makeProjectMemberSchema, MEMBER_ROLES } from './compartido'
import type { CambioDeCampo, ProjectSummary, ProjectDetail, ProjectMember, FeatureRequest, RespondForm, RespondBody } from './compartido'

export function ProjectDetailModal({ project, detail, open, onClose, onEdit }: { project: ProjectSummary | null; detail: ProjectDetail | undefined; open: boolean; onClose: () => void; onEdit: (p: ProjectSummary) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('info')
  const [addForm, setAddForm] = useState({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' })
  const projectMemberSchema = useMemo(() => makeProjectMemberSchema(t), [t])
  const addValidation = useFormValidation(projectMemberSchema)
  const [showAdd, setShowAdd] = useState(false)

  const { data: members = [], isLoading: loadingMembers } = useQuery({
    queryKey: ['project-members', project?.id],
    queryFn: () => projectsApi.members(project.id).then(r => r.data as ProjectMember[]),
    enabled: !!project?.id && tab === 'team',
  })
  // Selector de personas: `/users/directory` (ficha mínima) sirve a cualquier rol; `/users` da 403 al subcontratado.
  const { data: allUsers = [] } = useQuery({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    enabled: !!project?.id && tab === 'team',
  })

  // ── Feature Requests (tab 'requests') ─────────────────────────
  const [respondingFr, setRespondingFr] = useState<string | null>(null)
  const [respondForm, setRespondForm] = useState<RespondForm>({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' })

  const { data: featureRequests = [], isLoading: loadingFRs } = useQuery({
    queryKey: ['project-feature-requests', project?.id],
    queryFn: () => portalApi.featureRequests({ project_id: project.id }).then((r): FeatureRequest[] => r.data),
    enabled: !!project?.id && tab === 'requests',
  })

  const { mutate: respondFR, isPending: respondingFRPending } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RespondBody }) => portalApi.respondFeatureRequest(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-feature-requests', project?.id] }); setRespondingFr(null); setRespondForm({ pm_response: '', estimated_hours: '', estimated_cost: '', estimated_delivery_weeks: '', status: 'estimated' }) },
    onError: e => toast.error(extractErr(e, traducir('proyectos_ui.error_responder'))),
  })

  const { mutate: addMember, isPending: adding } = useMutation({
    // Sin strictNullChecks, zod marca opcionales todas las claves del tipo inferido;
    // `user_id` y `role` ya los ha exigido el esquema al validar.
    mutationFn: (d: z.infer<ReturnType<typeof makeProjectMemberSchema>>) => projectsApi.addMember(project.id, d as MemberAddPayload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', project.id] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); setShowAdd(false); setAddForm({ user_id: '', role: 'developer', allocation_pct: 100, notes: '' }); addValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, traducir('proyectos_ui.error_anadir_miembro'))),
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: (memberId: string) => projectsApi.removeMember(project.id, memberId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project-members', project.id] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (!project || !detail) return null

  const TABS = [
    { id: 'info',     label: traducir('proyectos_ui.tab_info') },
    { id: 'team',     label: members.length > 0 ? traducir('proyectos_ui.tab_equipo_n', { n: members.length }) : traducir('proyectos_ui.tab_equipo') },
    { id: 'phases',   label: traducir('proyectos_ui.tab_fases') },
    { id: 'docs',     label: traducir('proyectos_ui.tab_documentos') },
    { id: 'requests', label: featureRequests.length > 0 ? traducir('proyectos_ui.tab_solicitudes_n', { n: featureRequests.length }) : traducir('proyectos_ui.tab_solicitudes') },
  ]

  const memberUserIds = new Set(members.map(m => m.user_id))
  const availableUsers = allUsers.filter(u => !memberUserIds.has(u.id))

  const setAddField = (key: keyof typeof addForm) => (e: CambioDeCampo) => {
    const value = key === 'allocation_pct' ? Number(e.target.value) : e.target.value
    setAddForm(current => ({ ...current, [key]: value }))
    addValidation.clearFieldError(key)
  }

  const submitAddMember = () => {
    const result = addValidation.validateForm(addForm)
    if (!result.success) {
      return
    }
    addMember(result.data)
  }

  return (
    <Modal open={open} onClose={onClose} title={detail.name} width={720}>
      {/* Badges */}
      <div className="prj-row-4">
        <Badge label={detail.status} display={undefined} _color={undefined} /><Badge label={detail.risk_level} display={undefined} _color={undefined} /><Badge label={detail.project_type} display={undefined} _color={undefined} />
      </div>

      {/* Tab bar */}
      <div className="prj-row-5">
        {TABS.map(t => (
          <Pulsable className="prj-btn-xs-2" aria-pressed={tab === t.id} key={t.id} onClick={() => setTab(t.id)}
            style={{ '--prj-btn-xs-2-border': `1px solid ${tab === t.id ? 'var(--accent)' : 'var(--surface-4)'}`, '--prj-btn-xs-2-background': tab === t.id ? 'var(--accent-muted)' : 'transparent', '--prj-btn-xs-2-color': tab === t.id ? 'var(--accent)' : 'var(--text-2)' } as CSSProperties}>
            {t.label}
          </Pulsable>
        ))}
      </div>

      {/* INFO TAB */}
      {tab === 'info' && (
        <>
          {detail.description && <p className="prj-text-muted-md">{detail.description}</p>}
          <div className="prj-grid">
            {[
              { label: traducir('proyectos_ui.codigo'),        value: detail.code },
              { label: traducir('proyectos_ui.col_pm'),            value: detail.project_manager?.full_name || '—' },
              { label: traducir('proyectos_ui.cliente'),       value: detail.client_name || '—' },
              { label: traducir('proyectos_ui.departamento'),  value: detail.department || '—' },
              { label: traducir('proyectos_ui.inicio'),        value: fmtDate(detail.start_date) },
              { label: traducir('proyectos_ui.fin_planificado'),   value: fmtDate(detail.end_date_planned) },
              { label: traducir('proyectos_ui.col_progreso'),      value: `${detail.progress_pct?.toFixed(0) ?? 0}%` },
              { label: traducir('proyectos_ui.tareas'),        value: detail.tasks_total > 0 ? traducir('proyectos_ui.tareas_completadas', { hechas: detail.tasks_done ?? 0, total: detail.tasks_total }) : '—' },
              { label: traducir('proyectos_ui.tab_equipo'),        value: (detail.team_size ?? 0) === 1 ? traducir('proyectos_ui.una_persona') : traducir('proyectos_ui.n_personas', { n: detail.team_size ?? 0 }) },
              { label: traducir('proyectos_ui.col_presupuesto'),   value: detail.budget_amount ? fmtCurrency(detail.budget_amount) : '—' },
              { label: traducir('proyectos_ui.gastado'),       value: detail.total_cost_spent ? fmtCurrency(detail.total_cost_spent) : '—' },
            ].map(({ label, value }) => (
              <div className="prj-card-3" key={label}>
                <div className="prj-text-muted-xs">{label}</div>
                <div className="u-md-600">{value}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* TEAM TAB */}
      {tab === 'team' && (
        <div>
          <div className="u-row-between-mb16">
            <p className="prj-text-muted-base">
              {traducir('projects.personas_asignadas_explicitamente_a_este_proyecto')}
            </p>
            <Button variant={showAdd ? 'secondary' : 'primary'} icon={showAdd ? <X size={14} /> : <Plus size={14} />} onClick={() => setShowAdd(s => !s)}>
              {showAdd ? traducir('proyectos_ui.cancelar_x') : traducir('proyectos_ui.anadir_miembro')}
            </Button>
          </div>

          {/* Formulario añadir */}
          {showAdd && (
            <div className="prj-card-4">
              <div className="prj-grid-2">
                <div>
                  <label className="prj-label-muted-xs" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{traducir('proyectos_ui.persona_req')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-1`} value={addForm.user_id} onChange={setAddField('user_id')}
                    className={addValidation.inputClass('projects-page-campo', 'user_id')}>
                    <option value="">{traducir('proyectos_ui.seleccionar_persona')}</option>
                    {availableUsers.map(u => <option key={u.id} value={u.id}>{etiquetaDePersona(traducir, u)}{u.job_title ? ` (${u.job_title})` : ''}</option>)}
                  </Select>
                  {addValidation.errors.user_id && <div className="u-field-error">{addValidation.errors.user_id}</div>}
                </div>
                <div>
                  <label className="prj-label-muted-xs" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{traducir('proyectos_ui.rol')}</label>
                  <Select suelto placeholder={false} className="prj-input-2" id={`${idCampo}-2`} value={addForm.role} onChange={setAddField('role')}>
                    {Object.entries(MEMBER_ROLES).map(([k, v]) => <option key={k} value={k}>{traducir(v)}</option>)}
                  </Select>
                </div>
                <div>
                  <label className="prj-label-muted-xs" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{traducir('proyectos_ui.dedicacion')}</label>
                  <Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" min="1" max="100" value={addForm.allocation_pct}
                    onChange={setAddField('allocation_pct')}
                    inputClassName={addValidation.inputClass('projects-page-campo', 'allocation_pct')} />
                  {addValidation.errors.allocation_pct && <div className="u-field-error">{addValidation.errors.allocation_pct}</div>}
                </div>
              </div>
              <div className="u-row-end">
                <Button
                  onClick={submitAddMember}
                  disabled={adding}
                >
                  {adding ? traducir('proyectos_ui.anadiendo') : traducir('proyectos_ui.confirmar_asignacion')}
                </Button>
              </div>
            </div>
          )}

          {/* Lista de miembros */}
          {loadingMembers ? <Spinner /> : members.length === 0 ? (
            <EmptyState icon={<Users size={28} />} title={traducir('projects.todavia_no_hay_miembros_asignados')}
              description={traducir('projects.usa_el_boton_anadir_miembro_para_asignar')} />
          ) : (
            <div className="u-stack-8">
              {members.map(m => (
                <div className="prj-row-6" key={m.id}>
                  <div className="prj-row-accent">
                    {m.avatar_initials}
                  </div>
                  <div className="u-flex1">
                    {/* `role` aquí es el papel en el proyecto: la marca sale de `external_company`. */}
                    <div className="u-md-600">{m.full_name} <MarcaExterno persona={{ external_company: m.external_company }} /></div>
                    {m.email && <div className="u-text2-sm">{m.email}</div>}
                  </div>
                  <span className="prj-card-accent">
                    {MEMBER_ROLES[m.role] ? traducir(MEMBER_ROLES[m.role]) : m.role}
                  </span>
                  {typeof m.allocation_pct === 'number' && (
                  <span className="prj-box-4" style={{ '--prj-box-4-color': m.allocation_pct >= 100 ? 'var(--success)' : m.allocation_pct >= 50 ? 'var(--warning)' : 'var(--text-2)' } as CSSProperties}>
                    {m.allocation_pct}%
                  </span>
                  )}
                  <Pulsable className="prj-btn-danger-lg" aria-label={traducir('proyectos_ui.quitar_miembro')} title={traducir('proyectos_ui.quitar_miembro')} onClick={() => { openConfirmGlobal({ message: traducir('proyectos_ui.quitar_miembro_confirm', { nombre: m.full_name }), onConfirm: () => removeMember(m.id), danger: true }) }}>×</Pulsable>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* PHASES TAB */}
      {tab === 'phases' && (
        detail.phases?.length > 0 ? (
          <div>
            {detail.phases.map(ph => (
              <div className="prj-row-7" key={ph.id}>
                <div>
                  <div className="u-600">{ph.name}</div>
                  {(ph.start_date || ph.end_date) && (
                    <div className="u-text2-xs-mt2">
                      {fmtDate(ph.start_date)} → {fmtDate(ph.end_date)}
                    </div>
                  )}
                </div>
                <Badge label={ph.status} display={undefined} _color={undefined} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Layers size={28} />} title={traducir('projects.no_phases')} />
        )
      )}

      {/* DOCS TAB */}
      {tab === 'docs' && (
        <DocumentsPanel projectId={project.id} taskId={undefined} ticketId={undefined} />
      )}

      {/* FEATURE REQUESTS TAB */}
      {tab === 'requests' && (
        <div>
          {loadingFRs ? <Spinner /> : featureRequests.length === 0 ? (
            <EmptyState icon={<Lightbulb size={28} />} title={traducir('projects.no_hay_solicitudes_de_funcionalidad_para_este')}
              description={traducir('projects.los_clientes_pueden_crear_solicitudes_desde_el')} />
          ) : (
            <div className="u-stack-10">
              {featureRequests.map(fr => {
                const statusColors: Record<string, string> = { new: 'var(--accent)', reviewing: 'var(--warning)', estimated: 'var(--orange)', approved: 'var(--success)', rejected: 'var(--danger)', in_development: 'var(--purple)', done: 'var(--success)' }
                const priorityColors: Record<string, string> = { low: 'var(--text-2)', medium: 'var(--accent)', high: 'var(--warning)', critical: 'var(--danger)' }
                const statusLabels: Record<string, string> = { new: traducir('proyectos_ui.sol_new'), reviewing: traducir('proyectos_ui.sol_reviewing'), estimated: traducir('proyectos_ui.sol_estimated'), approved: traducir('proyectos_ui.sol_approved'), rejected: traducir('proyectos_ui.sol_rejected'), in_development: traducir('proyectos_ui.sol_in_development'), done: traducir('proyectos_ui.sol_done') }
                const isResponding = respondingFr === fr.id
                const canRespond = ['new', 'reviewing', 'estimated'].includes(fr.status)
                return (
                  <div className="prj-card-5" key={fr.id} style={{ '--prj-card-5-border': `1px solid ${isResponding ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
                    <div className="prj-row-8">
                      <div className="u-flex1-min0">
                        <div className="prj-row-9">
                          <span className="prj-text-muted-xs-strong-mono">{fr.code}</span>
                          <span className="prj-box-5" style={{ '--prj-box-5-border': `1px solid ${alpha(statusColors[fr.status] || 'var(--text-2)', '40')}`, '--prj-box-5-color': statusColors[fr.status] || 'var(--text-2)', '--prj-box-5-background': alpha(statusColors[fr.status] || 'var(--text-2)', '18') } as CSSProperties}>{statusLabels[fr.status] || fr.status}</span>
                          <span className="prj-text-xs prj-text-3" style={{ '--prj-text-3-color': priorityColors[fr.priority] || 'var(--text-2)' } as CSSProperties}>● {fr.priority}</span>
                          {fr.client_approved === true && <span className="prj-text-success-xs">{traducir('projects.cliente_aprobo')}</span>}
                          {fr.client_approved === false && <span className="prj-text-danger-xs">{traducir('projects.cliente_rechazo')}</span>}
                        </div>
                        <div className="prj-text-md-2">{fr.title}</div>
                        <div className="prj-text-muted-sm-2">{fr.description}</div>
                        {fr.business_justification && <div className="prj-text-muted-sm-3">{traducir('projects.justificacion')} {fr.business_justification}</div>}
                        {(fr.estimated_cost != null || fr.estimated_hours != null) && (
                          <div className="prj-row-10">
                            {fr.estimated_cost != null && <span className="u-text2-sm prj-dato-icono"><Coins size={12} aria-hidden /> {fmtCurrency(fr.estimated_cost)}</span>}
                            {fr.estimated_hours != null && <span className="u-text2-sm prj-dato-icono"><Clock size={12} aria-hidden /> {fr.estimated_hours}h</span>}
                            {fr.estimated_delivery_weeks != null && <span className="u-text2-sm prj-dato-icono"><CalendarDays size={12} aria-hidden /> {traducir('proyectos_ui.n_semanas_abrev', { n: fr.estimated_delivery_weeks })}</span>}
                          </div>
                        )}
                        {fr.pm_response && <div className="prj-card-muted prj-dato-icono"><MessageSquare size={12} aria-hidden /> {fr.pm_response}</div>}
                      </div>
                      <div className="prj-stack-2">
                        {canRespond && (
                          <Pulsable className="prj-btn-xs-3" onClick={() => { setRespondingFr(isResponding ? null : fr.id); if (!isResponding) setRespondForm({ pm_response: fr.pm_response || '', estimated_hours: fr.estimated_hours ?? '', estimated_cost: fr.estimated_cost ?? '', estimated_delivery_weeks: fr.estimated_delivery_weeks ?? '', status: fr.status === 'new' ? 'estimated' : fr.status }) }}
                            style={{ '--prj-btn-xs-3-border': `1px solid ${isResponding ? 'var(--accent)' : 'var(--surface-4)'}`, '--prj-btn-xs-3-background': isResponding ? 'var(--accent-muted)' : 'transparent', '--prj-btn-xs-3-color': isResponding ? 'var(--accent)' : 'var(--text-2)' } as CSSProperties}>
                            {isResponding ? traducir('proyectos_ui.cancelar_x') : traducir('proyectos_ui.responder')}
                          </Pulsable>
                        )}
                        <div className="prj-text-muted-xs-2">{fmtDate(fr.submitted_at)}</div>
                      </div>
                    </div>

                    {/* Formulario de respuesta PM */}
                    {isResponding && (
                      <div className="prj-box-6">
                        <div className="prj-text-muted-sm-strong">{traducir('projects.respuesta_del_pm')}</div>
                        <div className="prj-grid-3">
                          <div>
                            <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp828`} htmlFor={`${idCampo}-${fr.id}-resp828`}>{traducir('proyectos_ui.coste_estimado_moneda', { moneda: fmtMoneda.simbolo })}</label>
                            <Input id={`${idCampo}-${fr.id}-resp828`} aria-labelledby={`${idCampo}-${fr.id}-etresp828`} type="number" min="0" value={respondForm.estimated_cost} onChange={e => setRespondForm(f => ({ ...f, estimated_cost: e.target.value }))} placeholder="0" inputClassName="prj-fs" />
                          </div>
                          <div>
                            <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp832`} htmlFor={`${idCampo}-${fr.id}-resp832`}>{traducir('proyectos_ui.horas_estimadas')}</label>
                            <Input id={`${idCampo}-${fr.id}-resp832`} aria-labelledby={`${idCampo}-${fr.id}-etresp832`} type="number" min="0" value={respondForm.estimated_hours} onChange={e => setRespondForm(f => ({ ...f, estimated_hours: e.target.value }))} placeholder="0" inputClassName="prj-fs" />
                          </div>
                          <div>
                            <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp836`} htmlFor={`${idCampo}-${fr.id}-resp836`}>{traducir('proyectos_ui.semanas_entrega')}</label>
                            <Input id={`${idCampo}-${fr.id}-resp836`} aria-labelledby={`${idCampo}-${fr.id}-etresp836`} type="number" min="0" max="104" value={respondForm.estimated_delivery_weeks} onChange={e => setRespondForm(f => ({ ...f, estimated_delivery_weeks: e.target.value }))} placeholder="0" inputClassName="prj-fs" />
                          </div>
                        </div>
                        <div className="u-mb-10">
                          <label className="prj-ls" id={`${idCampo}-${fr.id}-etresp841`} htmlFor={`${idCampo}-${fr.id}-resp841`}>{traducir('projects.mensaje_al_cliente')}</label>
                          <Textarea id={`${idCampo}-${fr.id}-resp841`} aria-labelledby={`${idCampo}-${fr.id}-etresp841`} rows={3} value={respondForm.pm_response} onChange={e => setRespondForm(f => ({ ...f, pm_response: e.target.value }))} placeholder={traducir('projects.explica_la_estimacion_o_razon_del_rechazo')} inputClassName="prj-fs prj-input" />
                        </div>
                        <div className="u-row-center-10">
                          <label className="prj-label-muted-xs-2" id={`${idCampo}-${fr.id}-etresp845`} htmlFor={`${idCampo}-${fr.id}-resp845`}>{traducir('proyectos_ui.col_estado')}</label>
                          <Select suelto placeholder={false} className="prj-fs prj-input-3" id={`${idCampo}-${fr.id}-resp845`} value={respondForm.status} onChange={e => setRespondForm(f => ({ ...f, status: e.target.value }))}>
                            <option value="estimated">{traducir('proyectos_ui.sol_estimated')}</option>
                            <option value="rejected">{traducir('proyectos_ui.rechazar')}</option>
                            <option value="in_development">{traducir('proyectos_ui.sol_in_development')}</option>
                            <option value="done">{traducir('proyectos_ui.sol_done')}</option>
                          </Select>
                          <div className="u-flex1" />
                          <Button onClick={() => respondFR({ id: fr.id, data: { pm_response: respondForm.pm_response || undefined, estimated_hours: respondForm.estimated_hours !== '' ? Number(respondForm.estimated_hours) : undefined, estimated_cost: respondForm.estimated_cost !== '' ? Number(respondForm.estimated_cost) : undefined, estimated_delivery_weeks: respondForm.estimated_delivery_weeks !== '' ? Number(respondForm.estimated_delivery_weeks) : undefined, status: respondForm.status } })} disabled={respondingFRPending}>
                            {respondingFRPending ? traducir('proyectos_ui.guardando') : traducir('proyectos_ui.guardar_respuesta')}
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="prj-row-11">
        <Button variant="secondary" onClick={onClose}>{traducir('common.close')}</Button>
        <Button onClick={() => { onClose(); onEdit(detail) }} icon={<Pencil size={14} />}>{traducir('proyectos_ui.editar_proyecto')}</Button>
      </div>
    </Modal>
  )
}
