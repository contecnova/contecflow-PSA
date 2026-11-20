/**
 * SubcontractorsPage — subcontratistas, sus personas, asignaciones, horas y facturas.
 *
 * 16-11-2026: acción principal en la cabecera con icono (antes en el cuerpo con
 * "+" de texto); KPIs con KpiCard en .ds-grid-stats (antes centrados y con
 * cifra monoespaciada); el detalle ya tiene PageShell + PageHeader con migas
 * (antes se pintaba sin cabecera ni márgenes de página); pestañas con iconos;
 * vacíos con EmptyState e iconos lucide (antes 🤝👤📋🕐🧾); emojis de las
 * tarjetas y botones (📧👥✏🗑🏆🎉) cambiados por iconos lucide; estados con
 * StatusBadge y botones del kit.
 *
 * 19-11-2026 (proveedores y externalización, migración 189): alta con tipo
 * (persona freelance en un paso o empresa con modos), insignias de tipo, modos,
 * ciclo de vida y riesgo, KPIs del panorama y ficha con pestañas por tipo:
 * Resumen, Personas/Asignaciones/Horas (solo si tiene personas), Contratos y
 * precios, Servicios, Paquetes de trabajo, Consumo y facturación, Rendimiento y
 * Cumplimiento. Las pestañas nuevas viven en `pages/proveedores/`.
 */
import { useState, useId, useEffect } from 'react'
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, ReactNode } from 'react'
import { extractErr, fmtDate, fmtHours, fmtNumber } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseSubsApi, subcontractorsApi, projectsApi, skillsApi } from '../services/api'
import { CamposDeExterno, CredencialesDeExterno, cargaDeExterno, estadoDeAcceso, externoCompleto, formularioDeExternoInicial } from '../components/externos/FormularioDeExterno'
import type { FormDeExterno } from '../components/externos/FormularioDeExterno'
import type { ProjectListItem } from '../services/api/projects'
import type { SkillDelCatalogo, SubAsignacion, SubConciliacion, SubFactura, SubParteDeHoras, SubTrabajador, Subcontratista } from '../services/api/tipos-alm'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, ArrowLeft, Award, Briefcase, Building2, CalendarClock, Clock, Coins, FileText, Gauge, Handshake, HardHat, Layers, LayoutDashboard, Mail, Pencil, Plus, Receipt, Scale, ShieldCheck, Square, Trash2, UserRound, Users, X } from 'lucide-react'
import { Button, Card, EmptyState, IconButton, KpiCard, Modal, Spinner, useSort, SortableTH, ViewToggle, Tabs, Table, Select, TablaSimple, Checkbox, useErroresDeCampo } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { redondear2 } from '../utils/redondeo'
import { STALE_5_MIN_MS } from '../constants/timings'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { proveedoresApi } from '../services/api/proveedores'
import { pestanasDeLaFicha, esFreelance } from './proveedores/logica'
import type { PestanaDeFicha } from './proveedores/logica'
import { InsigniasDeProveedor, usePermisosDeProveedores } from './proveedores/comunes'
import AltaDeProveedor from './proveedores/AltaDeProveedor'
import PestanaResumen from './proveedores/PestanaResumen'
import PestanaContratos from './proveedores/PestanaContratos'
import PestanaServicios from './proveedores/PestanaServicios'
import PestanaPaquetes from './proveedores/PestanaPaquetes'
import PestanaConsumo from './proveedores/PestanaConsumo'
import PestanaRendimiento from './proveedores/PestanaRendimiento'
import PestanaCumplimiento from './proveedores/PestanaCumplimiento'
import './SubcontractorsPage.css'
/** Estados de factura de subcontratista y niveles de skill: su color sale de la clase. */
const ESTADOS_FACTURA = ['received', 'approved', 'paid', 'rejected']
const NIVELES = ['basic', 'intermediate', 'advanced', 'expert']
const claseNivel = (nivel: string) => NIVELES.includes(nivel) ? ` sub-skill--${nivel}` : ''
const TIPO_FACTURA: Record<string, StatusBadgeKind> = { received: 'warning', approved: 'accent', paid: 'success', rejected: 'danger' }

// Respuestas de /enterprise/subcontractors* y /skills/catalog: services/api/tipos-alm.
type Skill = SkillDelCatalogo
type Worker = SubTrabajador
type Sub = Subcontratista
type Timelog = SubParteDeHoras
type Invoice = SubFactura
type CredsInfo = { username: string; password?: string }
/** Papel en el proyecto de la asignación (ProjectMember.role). */
const PAPELES = ['lead', 'developer', 'designer', 'qa', 'analyst', 'devops', 'stakeholder', 'other']

function onKeyboardActivate(event: ReactKeyboardEvent, action: () => void) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

// ── Worker Modal ──────────────────────────────────────────────────────────────
function WorkerModal({ subId, worker, onClose, onSaved }: { subId: string; worker?: Worker; onClose: () => void; onSaved?: () => void }) {
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency: defaultCurrency, weekly_capacity_hours: capacidadEmpresa } = useOrgSettings()
  const isEdit = !!worker
  const [form, setForm] = useState<FormDeExterno>(() => formularioDeExternoInicial(worker, defaultCurrency, capacidadEmpresa))
  const [skillForm, setSkillForm] = useState({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' })
  const [showSkillForm, setShowSkillForm] = useState(false)

  const t = useAppT()
  const etiquetaNivel = (nivel: string) => NIVELES.includes(nivel) ? t(`subcontractors.nivel_${nivel}`) : nivel
  const { data: skillCatalog = [] } = useQuery<Skill[]>({
    queryKey: ['skills-catalog'],
    queryFn: () => skillsApi.catalog().then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })

  const [credsInfo, setCredsInfo] = useState<CredsInfo | null>(null)

  const campos = useErroresDeCampo()
  const { mutate: save, isPending: saving } = useMutation({
    onMutate: () => campos.limpiar(),
    // El alta devuelve además la contraseña temporal del usuario creado (SubTrabajadorCreado).
    mutationFn: async (d: Record<string, unknown>): Promise<SubTrabajador & { temp_password?: string }> => isEdit
      ? (await enterpriseSubsApi.updateWorker(worker!.id, d)).data
      : (await enterpriseSubsApi.createWorker(subId, d)).data,
    onSuccess: (creado) => {
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['users'] })
      onSaved?.()
      // La contraseña temporal solo llega si se creó el usuario (con acceso): se enseña una vez.
      if (!isEdit && creado?.login_username && creado.temp_password) {
        setCredsInfo({ username: creado.login_username, password: creado.temp_password })
      } else {
        onClose()
        toast.success(isEdit ? t('subcontractors.trabajador_actualizado') : t('subcontractors.trabajador_anadido'))
      }
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const { mutate: addSkill, isPending: addingSkill } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.addWorkerSkill(worker?.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-workers', subId] }); setShowSkillForm(false); setSkillForm({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' }); toast.success(t('subcontractors.skill_anadida')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: removeSkill } = useMutation({
    mutationFn: (skill_id: string) => enterpriseSubsApi.removeWorkerSkill(worker?.id, skill_id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-workers', subId] }); toast.success(t('subcontractors.skill_eliminada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // group skill catalog by category
  const byCategory: Record<string, Skill[]> = skillCatalog.reduce((acc: Record<string, Skill[]>, s: Skill) => {
    const cat = s.category || 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(s)
    return acc
  }, {} as Record<string, Skill[]>)

  if (credsInfo) return <CredencialesDeExterno usuario={credsInfo.username} contrasena={credsInfo.password} onClose={onClose} />

  return (
    <Modal open title={isEdit ? `${t('subcontractors.edit_person', { name: worker?.name })}` : t('subcontractors.new_person')} onClose={onClose} width={560}>
      <CamposDeExterno form={form} errores={campos.de} onChange={c => { Object.keys(c).forEach(k => campos.limpiar(k)); setForm(f => ({ ...f, ...c })) }} />

      {/* Skills section — only shown in edit mode */}
      {isEdit && (
        <div className="sub-skills-block">
          <div className="sub-skills-head">
            <div className="u-text1-sm-600">{t('subcontractors.skills')}</div>
            <Button size="sm" variant="ghost" icon={showSkillForm ? <X size={14} /> : <Plus size={14} />} onClick={() => setShowSkillForm(s => !s)}>
              {showSkillForm ? t('subcontractors.cancel_skill') : t('subcontractors.add_skill')}
            </Button>
          </div>

          {/* Existing skills */}
          <div className={`sub-skills${showSkillForm ? ' sub-skills--open' : ''}`}>
            {(worker?.skills || []).map(s => (
              <span key={s.skill_id} className={`sub-skill${claseNivel(s.level)}`}>
                {s.skill_name}
                <span className="sub-skill-level">({etiquetaNivel(s.level)})</span>
                {s.certified && <span title={t('subcontractors.certified')} role="img" aria-label={t('subcontractors.certified')}><Award size={12} aria-hidden /></span>}
                <IconButton type="button" className="sub-skill-remove" onClick={() => removeSkill(s.skill_id)}
                  ariaLabel={t('subcontractors.quitar_skill', { skill: s.skill_name })} title={t('subcontractors.quitar_skill', { skill: s.skill_name })}><X size={12} aria-hidden /></IconButton>
              </span>
            ))}
            {(worker.skills || []).length === 0 && !showSkillForm && (
              <span className="u-text2-sm">{t('subcontractors.no_skills')}</span>
            )}
          </div>

          {/* Add skill form */}
          {showSkillForm && (
            <div className="sub-skill-form">
              <div className="u-col-full">
                <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.add_skill')} *</label>
                <Select suelto placeholder={false} id={`${idCampo}-9`} value={skillForm.skill_id} onChange={e => { campos.limpiar('skill_id'); setSkillForm(f => ({ ...f, skill_id: e.target.value })) }} className="sub-input">
                  <option value="">{t('subcontractors.select_skill')}</option>
                  {Object.entries(byCategory).map(([cat, skills]) => (
                    <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                      {skills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </optgroup>
                  ))}
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.level')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-10`} value={skillForm.level} onChange={e => { campos.limpiar('level'); setSkillForm(f => ({ ...f, level: e.target.value })) }} className="sub-input">
                  {NIVELES.map(l => <option key={l} value={l}>{etiquetaNivel(l)}</option>)}
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.years_experience')}</label>
                <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} type="number" value={skillForm.years_experience} onChange={e => { campos.limpiar('years_experience'); setSkillForm(f => ({ ...f, years_experience: e.target.value })) }} className="sub-input" min="0" step="0.5" />
              </div>
              <div className="sub-check-row">
                <Checkbox className="sub-check-label" checked={!!skillForm.certified} onChange={v => { campos.limpiar('certified'); setSkillForm(f => ({ ...f, certified: v })) }}
                  label={t('subcontractors.certified')} />
                {skillForm.certified && (
                  <input aria-label={t('subcontractors.placeholder_cert')} value={skillForm.cert_name} onChange={e => { campos.limpiar('cert_name'); setSkillForm(f => ({ ...f, cert_name: e.target.value })) }} className="sub-input sub-input--flex" placeholder={t('subcontractors.placeholder_cert')} />
                )}
              </div>
              <div className="sub-row-end-full">
                <Button size="sm" onClick={() => addSkill(skillForm)} loading={addingSkill} disabled={!skillForm.skill_id || addingSkill}>{t('subcontractors.assign_skill')}</Button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="u-actions-8">
        <Button variant="secondary" onClick={onClose}>
          {isEdit ? t('subcontractors.close') : t('subcontractors.cancel')}
        </Button>
        <Button onClick={() => save(cargaDeExterno(form))} loading={saving} disabled={!externoCompleto(form) || saving}>{isEdit ? t('subcontractors.save_changes') : t('subcontractors.add_person')}</Button>
      </div>
    </Modal>
  )
}

// ── Workers Panel ─────────────────────────────────────────────────────────────
function WorkersPanel({ subId, permitirAlta = true }: { subId: string; permitirAlta?: boolean }) {
  const toast = useToast()
  const qc = useQueryClient()
  const t = useAppT()
  const fmtMoneda = useFormatoMoneda()
  const [showCreate, setShowCreate] = useState(false)
  const [editWorker, setEditWorker] = useState<Worker | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<Worker | null>(null)

  const { data: workers = [], isLoading } = useQuery<Worker[]>({
    queryKey: ['sub-workers', subId],
    queryFn: () => enterpriseSubsApi.workers(subId).then(r => r.data),
  })
  const hoy = new Date().toISOString().slice(0, 10)

  const { mutate: deactivate } = useMutation({
    mutationFn: (id: string) => enterpriseSubsApi.deleteWorker(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('subcontractors.trabajador_desactivado'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      {permitirAlta && (
        <div className="sub-toolbar-end">
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('subcontractors.add_person')}</Button>
        </div>
      )}

      {workers.length === 0 ? (
        <EmptyState icon={<UserRound size={28} />} title={t('subcontractors.empty_people_title')} description={t('subcontractors.empty_people_desc')} />
      ) : (
        <div className="u-stack-10">
          {workers.map(w => (
            <Card key={w.id} className="sub-item">
              <div className="sub-worker">
                <div className="u-flex1-min0">
                  <div className="sub-worker-head">
                    <div className="u-md-700">{w.name}</div>
                    {w.role && <StatusBadge kind="neutral" caps={false}>{w.role}</StatusBadge>}
                    {!w.is_active && <StatusBadge kind="danger" caps={false}>{t('subcontractors.inactivo')}</StatusBadge>}
                    {(() => {
                      const acceso = estadoDeAcceso(w, hoy)
                      const tono = acceso === 'con_acceso' ? 'success' : acceso === 'caduca' ? 'info' : acceso === 'caducado' ? 'danger' : 'neutral'
                      return (
                        <StatusBadge kind={tono} caps={false}>
                          {acceso === 'caduca' || acceso === 'caducado'
                            ? t(`externos.acceso_${acceso}`, { fecha: fmtDate(w.access_until) })
                            : t(`externos.acceso_${acceso}`)}
                        </StatusBadge>
                      )
                    })()}
                  </div>
                  {w.email && <div className="sub-mail"><Mail size={12} aria-hidden />{w.email}</div>}
                  <div className="sub-mail"><UserRound size={12} aria-hidden />
                    {w.internal_owner_name ? t('externos.responsable_n', { nombre: w.internal_owner_name }) : t('externos.sin_responsable')}
                  </div>
                  {(!!w.cost_rate || !!w.sell_rate) && (
                    <div className="sub-rates">
                      {!!w.cost_rate && t('subcontractors.coste_por_hora', { importe: fmtMoneda(w.cost_rate, { moneda: w.currency }) })}
                      {!!w.cost_rate && !!w.sell_rate && ' · '}
                      {!!w.sell_rate && t('subcontractors.venta_por_hora', { importe: fmtMoneda(w.sell_rate, { moneda: w.currency }) })}
                    </div>
                  )}
                  {/* Skills */}
                  <div className="sub-skills sub-skills--compact">
                    {(w.skills || []).map(s => (
                      <span key={s.skill_id} className={`sub-skill sub-skill--chip${claseNivel(s.level)}`}>
                        {s.skill_name}
                        {s.certified && <Award size={11} aria-hidden className="sub-skill-cert" />}
                      </span>
                    ))}
                    {(w.skills || []).length === 0 && <span className="sub-no-skills">{t('subcontractors.no_skills_short')}</span>}
                  </div>
                </div>
                <div className="sub-worker-actions">
                  {(w.available_from || w.available_until) && (
                    <div className="sub-availability">
                      {w.available_from && <div>{t('subcontractors.desde_fecha', { fecha: fmtDate(w.available_from) })}</div>}
                      {w.available_until && <div>{t('subcontractors.hasta_fecha', { fecha: fmtDate(w.available_until) })}</div>}
                    </div>
                  )}
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setEditWorker(w)}>
                    {t('subcontractors.edit')}
                  </Button>
                  {w.is_active && (
                    <IconButton className="sub-borrar" onClick={() => setDeactivateTarget(w)}
                      ariaLabel={t('subcontractors.desactivar_a', { name: w.name })} title={t('subcontractors.desactivar_a', { name: w.name })}>
                      <Trash2 size={15} aria-hidden />
                    </IconButton>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {showCreate && <WorkerModal subId={subId} onClose={() => setShowCreate(false)} onSaved={() => qc.invalidateQueries({ queryKey: ['subcontractors'] })} />}
      {editWorker && <WorkerModal subId={subId} worker={editWorker} onClose={() => setEditWorker(null)} onSaved={() => qc.invalidateQueries({ queryKey: ['subcontractors'] })} />}
      {deactivateTarget && (
        <Modal open title={t('subcontractors.desactivar_trabajador')} onClose={() => setDeactivateTarget(null)} width={380}>
          <p className="sub-confirm-text">
            {t('subcontractors.se_desactivara_a')} <strong>{deactivateTarget.name}</strong> {t('subcontractors.y_no_podra_iniciar_sesion_ni_ser')}
          </p>
          <div className="u-actions-8">
            <Button variant="ghost" onClick={() => setDeactivateTarget(null)}>{t('subcontractors.cancel')}</Button>
            <Button variant="danger" onClick={() => { deactivate(deactivateTarget.id); setDeactivateTarget(null) }}>{t('subcontractors.deactivate')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
function SubDetail({ sub, onBack, onCambio }: { sub: Sub; onBack: () => void; onCambio?: (s: Sub) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const { tax_rate: ivaEmpresa } = useOrgSettings()
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const t = useAppT()
  const { gestionar } = usePermisosDeProveedores()
  const pestanas = pestanasDeLaFicha(sub)
  const [tabElegida, setTab] = useState<string>('summary')
  // Si la clasificación cambia y la pestaña deja de existir (p. ej. ya no tiene personas), a Resumen.
  const tab: string = pestanas.includes(tabElegida as PestanaDeFicha) ? tabElegida : 'summary'
  const [showTimelog, setShowTimelog] = useState(false)
  const [showInvoice, setShowInvoice] = useState(false)
  const [showAssign, setShowAssign] = useState(false)
  const [tlForm, setTlForm] = useState({ worker_id: '', assignment_id: '', log_date: new Date().toISOString().slice(0,10), hours: 8, description: '', task_reference: '' })
  const [invForm, setInvForm] = useState({ invoice_number: '', issue_date: new Date().toISOString().slice(0,10), due_date: '', amount: '', tax_pct: ivaEmpresa, description: '' }) // 18-11-2026: IVA por defecto de la empresa; total = round(amount*(1+iva/100), 2) como el backend
  const [ivaSubTocado, setIvaSubTocado] = useState(false)
  useEffect(() => { if (!ivaSubTocado) setInvForm(f => ({ ...f, tax_pct: ivaEmpresa })) }, [ivaEmpresa, ivaSubTocado])
  const [asgForm, setAsgForm] = useState({ project_id: '', worker_id: '', rate_id: '', member_role: '', allocation_pct: '', po_number: '', po_amount: '', hours_contracted: '', start_date: '', end_date: '', notes: '' })

  const { data: assignments = [] } = useQuery<SubAsignacion[]>({
    queryKey: ['sub-assignments', sub.id],
    queryFn: () => enterpriseSubsApi.assignments(sub.id).then(r => r.data),
  })
  const { data: timelogs = [] } = useQuery<Timelog[]>({
    queryKey: ['sub-timelogs', sub.id],
    queryFn: () => enterpriseSubsApi.timelogs(sub.id).then(r => r.data),
  })
  const { data: invoices = [] } = useQuery<Invoice[]>({
    queryKey: ['sub-invoices', sub.id],
    queryFn: () => enterpriseSubsApi.invoices(sub.id).then(r => r.data),
  })
  // Personas del proveedor: la asignación es de una persona, y el parte manual solo de las que no tienen acceso.
  const { data: workers = [] } = useQuery<Worker[]>({
    queryKey: ['sub-workers', sub.id],
    queryFn: () => enterpriseSubsApi.workers(sub.id).then(r => r.data),
  })
  const trabajadoresActivos = workers.filter(w => w.is_active)
  const sinAcceso = trabajadoresActivos.filter(w => w.has_access === false)
  const tarifas = sub.rates || []
  const { data: conciliacion = [], isLoading: cargandoConciliacion } = useQuery<SubConciliacion[]>({
    queryKey: ['sub-reconciliation', sub.id],
    queryFn: () => enterpriseSubsApi.reconciliation(sub.id).then(r => r.data),
    enabled: tab === 'billing',
  })
  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => ((r.data as { items?: ProjectListItem[] })?.items ?? r.data ?? []).filter((p: ProjectListItem) => p.status === 'active')),
  })

  const { mutate: logHours, isPending: logging } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.createTimelog(sub.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-timelogs', sub.id] }); setShowTimelog(false); toast.success(t('subcontractors.hours_logged')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: createInv, isPending: invoicing } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.createInvoice(sub.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-invoices', sub.id] }); setShowInvoice(false); toast.success(t('subcontractors.invoice_logged')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: createAssign, isPending: assigning } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.createAssignment(sub.id, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sub-assignments', sub.id] })
      qc.invalidateQueries({ queryKey: ['sub-workers', sub.id] })
      setShowAssign(false)
      setAsgForm({ project_id: '', worker_id: '', rate_id: '', member_role: '', allocation_pct: '', po_number: '', po_amount: '', hours_contracted: '', start_date: '', end_date: '', notes: '' })
      toast.success(t('subcontractors.assignment_created'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: endAssign } = useMutation({
    mutationFn: ({ id, end_date }: { id: string; end_date?: string | null }) => enterpriseSubsApi.endAssignment(id, { end_date: end_date || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sub-assignments', sub.id] })
      qc.invalidateQueries({ queryKey: ['sub-workers', sub.id] })
      toast.success(t('externos.asignacion_terminada'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const terminarAsignacion = (a: SubAsignacion) => openConfirmGlobal({
    message: t('externos.terminar_confirmar', { persona: a.worker_name || t('externos.sin_persona'), proyecto: a.project_name || '' }),
    onConfirm: () => endAssign({ id: a.id }),
    danger: true,
  })
  const numeroONull = (v: string) => (v === '' ? null : Number(v))
  const enviarAsignacion = () => createAssign({
    project_id: asgForm.project_id,
    worker_id: asgForm.worker_id,
    rate_id: asgForm.rate_id || null,
    member_role: asgForm.member_role || null,
    allocation_pct: numeroONull(asgForm.allocation_pct),
    po_number: asgForm.po_number || null,
    po_amount: numeroONull(asgForm.po_amount),
    hours_contracted: numeroONull(asgForm.hours_contracted),
    start_date: asgForm.start_date || null,
    end_date: asgForm.end_date || null,
    notes: asgForm.notes || null,
  })

  const { mutate: updateInvStatus } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => enterpriseSubsApi.updateInvoice(sub.id, id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sub-invoices', sub.id] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })

  const totalHours    = timelogs.reduce((s: number, l: Timelog) => s + l.hours, 0)
  const totalCost     = timelogs.reduce((s: number, l: Timelog) => s + (l.cost_amount || 0), 0)
  const pendingAmount = invoices.filter((i: Invoice) => i.status === 'received').reduce((s: number, i: Invoice) => s + i.total, 0)

  const subtitulo = [sub.code, sub.company, sub.email].filter(Boolean).join(' · ')

  return (
    <PageShell>
      <PageHeader
        icon={<HardHat size={18} />}
        title={sub.name}
        subtitle={subtitulo || undefined}
        breadcrumb={[{ label: t('subcontractors.title'), onClick: onBack }, { label: sub.name || '' }]}
        actions={<>
          <Button variant="secondary" icon={<ArrowLeft size={14} />} onClick={onBack}>{t('subcontractors.volver')}</Button>
        </>}
        showListExport={false}
      />
      <InsigniasDeProveedor sub={sub} />

      <div className="u-stack-16">
      {/* KPIs */}
      <div className="ds-grid-stats">
        <KpiCard icon={<Users size={16} />} label={t('subcontractors.kpi_personas')} value={sub.worker_count ?? '—'} />
        <KpiCard icon={<Briefcase size={16} />} label={t('subcontractors.kpi_asignaciones')} value={assignments.length} />
        <KpiCard icon={<Clock size={16} />} label={t('subcontractors.hours_logged')} value={`${fmtNumber(totalHours, 1)}h`} />
        <KpiCard icon={<Coins size={16} />} label={t('subcontractors.kpi_coste_acumulado')} value={fmtMoneda(totalCost)} />
        <KpiCard icon={<Receipt size={16} />} label={t('subcontractors.kpi_facturas_pendientes')} value={fmtMoneda(pendingAmount)} warning={pendingAmount > 0} />
      </div>

      <Tabs
        items={([
          { id: 'summary',     label: t('proveedores.tab_resumen'), icon: <LayoutDashboard size={14} /> },
          { id: 'workers',     label: t('subcontractors.kpi_personas'), icon: <Users size={14} /> },
          { id: 'assignments', label: t('subcontractors.kpi_asignaciones'), icon: <Briefcase size={14} />, count: assignments.length || undefined },
          { id: 'timelogs',    label: t('subcontractors.tab_horas'), icon: <Clock size={14} />, count: timelogs.length || undefined },
          { id: 'contracts',   label: t('proveedores.tab_contratos'), icon: <FileText size={14} /> },
          { id: 'services',    label: t('proveedores.tab_servicios'), icon: <Layers size={14} /> },
          { id: 'packages',    label: t('proveedores.tab_paquetes'), icon: <Building2 size={14} /> },
          { id: 'billing',     label: t('proveedores.tab_consumo'), icon: <Receipt size={14} />, count: invoices.length || undefined },
          { id: 'performance', label: t('proveedores.tab_rendimiento'), icon: <Gauge size={14} /> },
          { id: 'compliance',  label: t('proveedores.tab_cumplimiento'), icon: <ShieldCheck size={14} /> },
        ] as { id: PestanaDeFicha; label: string; icon: ReactNode; count?: number }[]).filter(p => pestanas.includes(p.id))}
        active={tab}
        onChange={setTab}
        ariaLabel={t('subcontractors.secciones_del_subcontratista')}
      />

      {tab === 'summary' && <PestanaResumen sub={sub} />}

      {/* Personas (Workers): el freelance es su única persona (se crea en el alta) */}
      {tab === 'workers' && <WorkersPanel subId={sub.id} permitirAlta={gestionar && !esFreelance(sub)} />}

      {tab === 'contracts' && <PestanaContratos sub={sub} />}
      {tab === 'services' && <PestanaServicios sub={sub} />}
      {tab === 'packages' && <PestanaPaquetes sub={sub} />}
      {tab === 'performance' && <PestanaRendimiento sub={sub} />}
      {tab === 'compliance' && <PestanaCumplimiento sub={sub} onCambio={onCambio} />}

      {/* Asignaciones */}
      {tab === 'assignments' && (
        <div>
          {gestionar && (
            <div className="sub-toolbar-end">
              <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowAssign(true)} disabled={trabajadoresActivos.length === 0}
                title={trabajadoresActivos.length === 0 ? t('proveedores.asignacion_exige_persona') : undefined}>{t('subcontractors.nueva_asignacion')}</Button>
            </div>
          )}
          {assignments.length === 0 ? (
            <EmptyState icon={<Briefcase size={28} />} title={t('subcontractors.empty_assignments_title')} description={t('subcontractors.empty_assignments_desc')} />
          ) : <div className="u-stack-8">{assignments.map(a => {
            const consumo = a.consumption_pct ?? a.budget_used_pct ?? 0
            const activa = a.is_active !== false && !a.ended_at
            const umbral = fmtNumber(a.threshold_pct ?? 0, 0)
            return (
            <Card key={a.id} className="sub-item">
              <div className="sub-asignacion">
                <div className="u-min0">
                  <div className="sub-worker-head">
                    <div className="u-base-700">{a.project_code} — {a.project_name}</div>
                    <StatusBadge kind={activa ? 'success' : 'neutral'} caps={false}>
                      {activa ? t('externos.asignacion_activa') : t('externos.asignacion_terminada_el', { fecha: fmtDate(a.ended_at || a.end_date) })}
                    </StatusBadge>
                    {a.alert && (
                      <StatusBadge kind="danger" caps={false}>
                        <AlertTriangle size={11} aria-hidden /> {t('externos.aviso_consumo', { umbral })}
                      </StatusBadge>
                    )}
                  </div>
                  <div className="u-text2-sm-mt2">
                    {[
                      t('externos.persona_n', { nombre: a.worker_name || t('externos.sin_persona') }),
                      a.member_role && (PAPELES.includes(a.member_role) ? t(`externos.papel_${a.member_role}`) : a.member_role),
                      a.allocation_pct != null && t('externos.dedicacion_n', { pct: fmtNumber(a.allocation_pct, 0) }),
                      a.rate?.description && t('externos.tarifa_n', { tarifa: a.rate.description }),
                      a.po_number && t('subcontractors.po_numero', { po: a.po_number }),
                      !!a.po_amount && t('subcontractors.techo_importe', { importe: fmtMoneda(a.po_amount) }),
                    ].filter(Boolean).join(' · ')}
                  </div>
                  <div className="u-text2-sm-mt2">
                    {[
                      t('externos.horas_imputadas_n', { horas: fmtHours(a.hours_imputed ?? 0) }),
                      t('externos.horas_manuales_n', { horas: fmtHours(a.hours_manual ?? 0) }),
                      a.cost_amount != null && t('externos.coste_n', { importe: fmtMoneda(a.cost_amount) }),
                    ].filter(Boolean).join(' · ')}
                  </div>
                  {!!a.hours_contracted && (
                    <div className="sub-progress-wrap">
                      <div className="sub-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.min(consumo, 100)}
                        aria-label={t('subcontractors.consumo_de_horas')}>
                        <div className={`sub-progress-bar${a.alert || consumo > 90 ? ' sub-progress-bar--over' : ''}`}
                          style={{ '--pct': `${Math.min(consumo, 100)}%` } as CSSProperties} />
                      </div>
                      <div className="sub-progress-text">{fmtHours(a.hours_logged)} / {fmtHours(a.hours_contracted)} ({fmtNumber(consumo, 1)}%)</div>
                    </div>
                  )}
                </div>
                <div className="sub-worker-actions">
                  <Button size="sm" variant="secondary" icon={<Clock size={14} />} onClick={() => { setTlForm(f => ({...f, assignment_id: a.id, worker_id: sinAcceso.some(w => w.id === a.worker_id) ? (a.worker_id || '') : ''})); setShowTimelog(true) }}>{t('subcontractors.registrar_horas')}</Button>
                  {activa && (
                    <Button size="sm" variant="ghost" className="sub-borrar" icon={<Square size={14} />} onClick={() => terminarAsignacion(a)}>{t('externos.terminar_asignacion')}</Button>
                  )}
                </div>
              </div>
            </Card>
            )
          })}</div>}
        </div>
      )}

      {/* Timelogs */}
      {tab === 'timelogs' && (
        <div>
          <div className="sub-toolbar-end">
            <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowTimelog(true)}>{t('subcontractors.registrar_horas')}</Button>
          </div>
          {timelogs.length === 0 ? (
            <EmptyState icon={<Clock size={28} />} title={t('subcontractors.empty_hours_title')} description={t('subcontractors.empty_hours_desc')} />
          ) : (
            <div className="sub-panel sub-panel--clip">
              <Table
                data={timelogs}
                columns={[
                  { key: 'log_date', label: t('subcontractors.col_fecha'), render: (_v, l) => <span className="u-text2-sm">{fmtDate(l.log_date)}</span> },
                  { key: 'worker_name', label: t('externos.col_persona'), render: (_v, l) => <span className="u-text2-sm">{l.worker_name || '—'}</span> },
                  { key: 'hours', label: t('subcontractors.tab_horas'), render: (_v, l) => <span className="sub-hours">{fmtHours(l.hours)}</span> },
                  { key: 'description', label: t('subcontractors.descripcion'), render: (_v, l) => <span className="sub-ellipsis" title={l.description || undefined}>{l.description || '—'}</span> },
                  { key: 'task_reference', label: t('subcontractors.col_ref_tarea'), render: (_v, l) => <span className="u-text2-xs">{l.task_reference || '—'}</span> },
                  { key: 'cost_amount', label: t('subcontractors.col_coste'), render: (_v, l) => (
                    <span className="sub-money-warning">
                      {l.cost_amount ? fmtMoneda(l.cost_amount) : '—'}
                    </span>
                  ) },
                  { key: 'project_name', label: t('subcontractors.col_proyecto'), render: (_v, l) => <span className="u-text2-xs">{l.project_name || '—'}</span> },
                ]}
              />
            </div>
          )}
        </div>
      )}

      {/* Consumo y facturación: consumo, previsión y estados de cuenta; debajo, facturas y conciliación por horas */}
      {tab === 'billing' && (
        <div className="u-stack-16">
          <PestanaConsumo sub={sub} facturas={invoices} />
          <div>
          <div className="sub-toolbar-end">
            <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowInvoice(true)}>{t('subcontractors.registrar_factura')}</Button>
          </div>
          {invoices.length === 0 ? (
            <EmptyState icon={<Receipt size={28} />} title={t('subcontractors.empty_invoices_title')} description={t('subcontractors.empty_invoices_desc')} />
          ) : (
            <div className="sub-panel sub-panel--clip u-scroll-x">
              <TablaSimple claseTabla="u-table">
                <thead>
                  <tr className="u-border-b">
                    {[t('subcontractors.col_n_factura'), t('subcontractors.col_fecha'), t('subcontractors.col_importe'), t('subcontractors.col_total_iva'), t('subcontractors.col_estado'), t('subcontractors.col_acciones')].map(h => (
                      <th key={h} scope="col" className="sub-th">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {invoices.map(inv => (
                    <tr key={inv.id} className="sub-tr">
                      <td className="sub-td sub-td--strong">{inv.invoice_number}</td>
                      <td className="sub-td sub-td--muted">{fmtDate(inv.issue_date)}</td>
                      <td className="sub-td sub-td--mono">{fmtMoneda(inv.amount)}</td>
                      <td className="sub-td sub-td--total">{fmtMoneda(inv.total)}</td>
                      <td className="sub-td">
                        <StatusBadge kind={TIPO_FACTURA[inv.status || ''] || 'neutral'} caps={false}>
                          {ESTADOS_FACTURA.includes(inv.status || '') ? t(`subcontractors.factura_${inv.status}`) : inv.status}
                        </StatusBadge>
                      </td>
                      <td className="sub-td">
                        <div className="u-row-6">
                          {inv.status === 'received' && (
                            <Button size="xs" variant="secondary" onClick={() => updateInvStatus({ id: inv.id, status: 'approved' })}>{t('subcontractors.approve')}</Button>
                          )}
                          {inv.status === 'approved' && (
                            <Button size="xs" variant="secondary" onClick={() => updateInvStatus({ id: inv.id, status: 'paid' })}>{t('subcontractors.marcar_pagada')}</Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple>
            </div>
          )}

          {/* Conciliación: factura frente a horas imputadas y de parte manual */}
          <div className="sub-conc">
            <div className="sub-conc-head">
              <Scale size={15} aria-hidden />
              <span className="u-text1-sm-600">{t('externos.conciliacion')}</span>
            </div>
            <p className="u-text2-sm">{t('externos.conciliacion_ayuda')}</p>
            {cargandoConciliacion ? <Spinner /> : conciliacion.length === 0 ? (
              <EmptyState icon={<Scale size={28} />} title={t('externos.conciliacion_vacia')} description={t('externos.conciliacion_vacia_desc')} />
            ) : (
              <div className="sub-panel sub-panel--clip u-scroll-x">
                <TablaSimple claseTabla="u-table">
                  <thead>
                    <tr className="u-border-b">
                      {[t('subcontractors.col_n_factura'), t('subcontractors.col_proyecto'), t('externos.col_periodo'), t('externos.col_imputadas'), t('externos.col_manuales'), t('externos.col_esperado'), t('subcontractors.col_importe'), t('externos.col_diferencia')].map(h => (
                        <th key={h} scope="col" className="sub-th">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {conciliacion.map(c => {
                      const signo = c.difference > 0 ? '+' : ''
                      const tono = c.difference > 0 ? ' sub-dif--sobre' : c.difference < 0 ? ' sub-dif--bajo' : ''
                      return (
                        <tr key={`${c.invoice_id}-${c.assignment_id ?? ''}`} className="sub-tr">
                          <td className="sub-td sub-td--strong">{c.invoice_number}<div className="u-text2-xs">{fmtDate(c.issue_date)}</div></td>
                          <td className="sub-td">{c.project_name || '—'}</td>
                          <td className="sub-td sub-td--muted">{c.period_from || c.period_to ? `${fmtDate(c.period_from)} – ${fmtDate(c.period_to)}` : '—'}</td>
                          <td className="sub-td sub-td--mono">{fmtHours(c.hours_imputed)}</td>
                          <td className="sub-td sub-td--mono">{fmtHours(c.hours_manual)}</td>
                          <td className="sub-td sub-td--mono">{fmtMoneda(c.expected_amount, { moneda: c.currency })}</td>
                          <td className="sub-td sub-td--mono">{fmtMoneda(c.amount, { moneda: c.currency })}</td>
                          <td className={`sub-td sub-td--mono sub-dif${tono}`}
                            title={c.difference > 0 ? t('externos.dif_sobre') : c.difference < 0 ? t('externos.dif_bajo') : undefined}>
                            {signo}{fmtMoneda(c.difference, { moneda: c.currency })}
                            {c.difference_pct != null && <span className="u-text2-xs"> ({signo}{fmtNumber(c.difference_pct, 1)}%)</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </TablaSimple>
              </div>
            )}
          </div>
          </div>
        </div>
      )}

      {/* Modal registrar horas */}
      {showTimelog && (
        <Modal open title={t('subcontractors.registrar_horas')} onClose={() => setShowTimelog(false)} width={480}>
          {/* Parte manual: solo de personas sin acceso; las que tienen login imputan ellas mismas. */}
          <p className="u-text2-sm">{t('externos.parte_manual_ayuda')}</p>
          <div className="sub-form-grid">
            <div className="u-col-full">
              <label id={`${idCampo}-tlw-et`} htmlFor={`${idCampo}-tlw`} className="sub-label">{t('externos.persona_sin_acceso')} *</label>
              <Select suelto placeholder={false} id={`${idCampo}-tlw`} value={tlForm.worker_id} onChange={e => setTlForm(f=>({...f,worker_id:e.target.value}))} className="sub-input">
                <option value="">{sinAcceso.length ? t('subcontractors.seleccionar') : t('externos.nadie_sin_acceso')}</option>
                {sinAcceso.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-1-et`} htmlFor={`${idCampo}-1`} className="sub-label">{t('subcontractors.asignacion')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-1`} value={tlForm.assignment_id} onChange={e => setTlForm(f=>({...f,assignment_id:e.target.value}))} className="sub-input">
                <option value="">{t('subcontractors.sin_asignacion')}</option>
                {assignments.map(a => <option key={a.id} value={a.id}>{a.project_code} — {a.project_name}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-2-et`} htmlFor={`${idCampo}-2`} className="sub-label">{t('subcontractors.col_fecha')}</label>
              <DateInput id={`${idCampo}-2`} aria-labelledby={`${idCampo}-2-et`} value={tlForm.log_date} onChange={e => setTlForm(f=>({...f,log_date:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-3-et`} htmlFor={`${idCampo}-3`} className="sub-label">{t('subcontractors.horas_obligatorio')}</label>
              <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-3-et`} type="number" value={tlForm.hours} onChange={e => setTlForm(f=>({...f,hours:+e.target.value}))} className="sub-input" min="0.5" step="0.5" />
            </div>
            <div>
              <label id={`${idCampo}-a599-et`} htmlFor={`${idCampo}-a599`} className="sub-label">{t('subcontractors.referencia_de_tarea')}</label>
              <input id={`${idCampo}-a599`} aria-labelledby={`${idCampo}-a599-et`} value={tlForm.task_reference} onChange={e => setTlForm(f=>({...f,task_reference:e.target.value}))} className="sub-input" placeholder={t('subcontractors.referencia_de_tarea')} />
            </div>
            <div className="u-col-full">
              <label id={`${idCampo}-tl-desc-et`} htmlFor={`${idCampo}-tl-desc`} className="sub-label">{t('subcontractors.descripcion')}</label>
              <input id={`${idCampo}-tl-desc`} aria-labelledby={`${idCampo}-tl-desc-et`} value={tlForm.description} onChange={e => setTlForm(f=>({...f,description:e.target.value}))} className="sub-input" placeholder={t('subcontractors.descripcion_del_parte')} />
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowTimelog(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => logHours({ ...tlForm, assignment_id: tlForm.assignment_id || null })} loading={logging} disabled={!tlForm.worker_id || !tlForm.hours || logging}>{t('subcontractors.registrar_horas')}</Button>
          </div>
        </Modal>
      )}

      {/* Modal registrar factura */}
      {showInvoice && (
        <Modal open title={t('subcontractors.registrar_factura')} onClose={() => setShowInvoice(false)} width={480}>
          <div className="sub-form-grid">
            <div>
              <label id={`${idCampo}-a619-et`} htmlFor={`${idCampo}-a619`} className="sub-label">{t('subcontractors.n_factura_obligatorio')}</label>
              <input id={`${idCampo}-a619`} aria-labelledby={`${idCampo}-a619-et`} value={invForm.invoice_number} onChange={e => setInvForm(f=>({...f,invoice_number:e.target.value}))} className="sub-input" placeholder={t('subcontractors.numero_de_factura')} />
            </div>
            <div>
              <label id={`${idCampo}-4-et`} htmlFor={`${idCampo}-4`} className="sub-label">{t('subcontractors.fecha_emision')}</label>
              <DateInput id={`${idCampo}-4`} aria-labelledby={`${idCampo}-4-et`} value={invForm.issue_date} onChange={e => setInvForm(f=>({...f,issue_date:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-5-et`} htmlFor={`${idCampo}-5`} className="sub-label">{t('subcontractors.importe_base_moneda', { moneda: fmtMoneda.simbolo })}</label>
              <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-5-et`} type="number" value={invForm.amount} onChange={e => setInvForm(f=>({...f,amount:e.target.value}))} className="sub-input" min="0" step="0.01" />
            </div>
            <div>
              <label id={`${idCampo}-6-et`} htmlFor={`${idCampo}-6`} className="sub-label">{t('subcontractors.iva_pct')}</label>
              <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-6-et`} type="number" value={invForm.tax_pct} onChange={e => { setIvaSubTocado(true); setInvForm(f=>({...f,tax_pct:+e.target.value})) }} className="sub-input" min="0" max="30" />
            </div>
            {invForm.amount && (
              <div className="sub-total-box">
                {t('subcontractors.total_con_iva')} <strong>{fmtMoneda(redondear2(+invForm.amount * (1 + invForm.tax_pct/100)))}</strong>
              </div>
            )}
            <div className="u-col-full">
              <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="sub-label">{t('subcontractors.descripcion')}</label>
              <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={invForm.description} onChange={e => setInvForm(f=>({...f,description:e.target.value}))} className="sub-input" />
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowInvoice(false)}>{t('common.cancel')}</Button>
            <Button onClick={() => createInv(invForm)} loading={invoicing} disabled={!invForm.invoice_number || !invForm.amount || invoicing}>{t('subcontractors.registrar_factura')}</Button>
          </div>
        </Modal>
      )}

      {/* Modal nueva asignación */}
      {showAssign && (
        <Modal open title={t('subcontractors.nueva_asignacion_2')} onClose={() => setShowAssign(false)} width={500}>
          <div className="sub-form-grid">
            <div className="u-col-full">
              <label id={`${idCampo}-8-et`} htmlFor={`${idCampo}-8`} className="sub-label">{t('subcontractors.proyecto_obligatorio')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-8`} value={asgForm.project_id} onChange={e => setAsgForm(f=>({...f,project_id:e.target.value}))} className="sub-input">
                <option value="">{t('subcontractors.seleccionar')}</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-asw-et`} htmlFor={`${idCampo}-asw`} className="sub-label">{t('externos.persona')} *</label>
              <Select suelto placeholder={false} id={`${idCampo}-asw`} value={asgForm.worker_id} onChange={e => setAsgForm(f=>({...f,worker_id:e.target.value}))} className="sub-input">
                <option value="">{t('subcontractors.seleccionar')}</option>
                {trabajadoresActivos.map(w => <option key={w.id} value={w.id}>{w.name}{w.role ? ` (${w.role})` : ''}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-asr-et`} htmlFor={`${idCampo}-asr`} className="sub-label">{t('externos.tarifa')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-asr`} value={asgForm.rate_id} onChange={e => setAsgForm(f=>({...f,rate_id:e.target.value}))} className="sub-input">
                <option value="">{tarifas.length ? t('externos.tarifa_de_la_persona') : t('externos.sin_tarifas')}</option>
                {tarifas.map(r => <option key={r.id} value={r.id}>{[r.description, r.cost_rate != null ? fmtMoneda(r.cost_rate, { moneda: r.currency }) : null].filter(Boolean).join(' · ')}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-asp-et`} htmlFor={`${idCampo}-asp`} className="sub-label">{t('externos.papel')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-asp`} value={asgForm.member_role} onChange={e => setAsgForm(f=>({...f,member_role:e.target.value}))} className="sub-input">
                <option value="">{t('externos.papel_por_defecto')}</option>
                {PAPELES.map(r => <option key={r} value={r}>{t(`externos.papel_${r}`)}</option>)}
              </Select>
            </div>
            <div>
              <label id={`${idCampo}-asa-et`} htmlFor={`${idCampo}-asa`} className="sub-label">{t('externos.dedicacion')}</label>
              <input id={`${idCampo}-asa`} aria-labelledby={`${idCampo}-asa-et`} type="number" min="0" max="100" step="5" value={asgForm.allocation_pct} onChange={e => setAsgForm(f=>({...f,allocation_pct:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-a663-et`} htmlFor={`${idCampo}-a663`} className="sub-label">{t('subcontractors.n_pedido_po')}</label>
              <input id={`${idCampo}-a663`} aria-labelledby={`${idCampo}-a663-et`} value={asgForm.po_number} onChange={e => setAsgForm(f=>({...f,po_number:e.target.value}))} className="sub-input" placeholder={t('subcontractors.numero_de_pedido')} />
            </div>
            <div>
              <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.techo_po_moneda', { moneda: fmtMoneda.simbolo })}</label>
              <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-9-et`} type="number" value={asgForm.po_amount} onChange={e => setAsgForm(f=>({...f,po_amount:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.horas_contratadas')}</label>
              <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-10-et`} type="number" value={asgForm.hours_contracted} onChange={e => setAsgForm(f=>({...f,hours_contracted:e.target.value}))} className="sub-input" />
            </div>
            <div>
              <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.fecha_inicio')}</label>
              <DateInput id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} value={asgForm.start_date} onChange={e => setAsgForm(f=>({...f,start_date:e.target.value}))} className="sub-input" />
            </div>
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => setShowAssign(false)}>{t('common.cancel')}</Button>
            <Button onClick={enviarAsignacion} loading={assigning} disabled={!asgForm.project_id || !asgForm.worker_id || assigning}>{t('subcontractors.crear_asignacion')}</Button>
          </div>
        </Modal>
      )}
      </div>
    </PageShell>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function SubcontractorsPage() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency, currencies: monedasDeLaEmpresa } = useOrgSettings()
  const fmtMoneda = useFormatoMoneda()
  const { gestionar } = usePermisosDeProveedores()
  const [elegido, setSelected] = useState<Sub | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const { data: dashboard } = useQuery({
    queryKey: ['sub-dashboard'],
    queryFn: () => enterpriseSubsApi.dashboard().then(r => r.data),
  })
  const { data: subs = [], isLoading } = useQuery<Sub[]>({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then(r => r.data),
  })
  // Panorama de proveedores (tipos, documentos, revisiones, estados de cuenta, previsión del mes).
  const { data: panorama } = useQuery({
    queryKey: ['suppliers', 'overview'],
    queryFn: () => proveedoresApi.panorama().then(r => r.data),
    retry: false,
  })
  // La ficha abierta sigue a la lista (clasificación, ciclo de vida y riesgo cambian desde la ficha).
  const selected = elegido ? (subs.find(s => s.id === elegido.id) ?? elegido) : null

  const [showEdit, setShowEdit] = useState(false)
  const [editTarget, setEditTarget] = useState<Sub | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [view, setView] = useState('grid')
  const { sort: subSort, setSort: setSubSort, sortedData: sortedSubs } = useSort<Sub>(subs, 'name')

  const camposEdit = useErroresDeCampo()
  const msgEdit = (k: string) => camposEdit.de(k) ? <div className="u-field-error">{camposEdit.de(k)}</div> : null
  const { mutate: update, isPending: updating } = useMutation({
    onMutate: () => camposEdit.limpiar(),
    mutationFn: ({ id, ...d }: { id: string; [k: string]: unknown }) => subcontractorsApi.update(id, d),
    onSuccess: (_res) => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      setShowEdit(false)
      setEditTarget(null)
      toast.success(t('subcontractors.subcontratista_actualizado'))
    },
    onError: (e: unknown) => { if (!camposEdit.recoger(e)) toast.error(extractErr(e, t('common.error_update'))) },
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => subcontractorsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      qc.invalidateQueries({ queryKey: ['sub-dashboard'] })
      toast.success(t('subcontractors.subcontratista_eliminado'))
    },
    onError: e => toast.error(extractErr(e, t('common.error_delete'))),
  })

  const abrirEdicion = (s: Sub) => {
    setEditTarget(s)
    setEditForm({ name: s.name||'', company: s.company||'', email: s.email||'', phone: s.phone||'', country: s.country||'España', currency: s.currency||currency, vat_number: s.vat_number||'', notes: s.notes||'' })
    setShowEdit(true)
  }
  const confirmarEliminar = (s: Sub) =>
    openConfirmGlobal({ message: t('subcontractors.confirmar_eliminar', { name: s.name }), onConfirm: () => remove(s.id), danger: true })

  if (selected) return <SubDetail sub={selected} onBack={() => setSelected(null)} onCambio={setSelected} />

  return (
    <PageShell>
      <PageHeader icon={<HardHat size={18} />} title={t('subcontractors.title')} subtitle={t('subcontractors.subtitle')}
        actions={<>
          {gestionar && <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('subcontractors.nuevo_subcontratista')}</Button>}
        </>} />

      <div className="u-stack-16">
      {/* KPIs */}
      {dashboard && (
        <div className="ds-grid-stats">
          <KpiCard icon={<Handshake size={16} />} label={t('subcontractors.kpi_activos')} value={dashboard.total_active_subs} />
          <KpiCard icon={<Clock size={16} />} label={t('subcontractors.hours_logged')} value={fmtHours(dashboard.total_hours_logged)} />
          <KpiCard icon={<Receipt size={16} />} label={t('subcontractors.kpi_facturas_pendientes')} value={dashboard.pending_invoices} warning={dashboard.pending_invoices > 0} />
        </div>
      )}
      {panorama && (
        <div className="ds-grid-stats">
          <KpiCard icon={<UserRound size={16} />} label={t('proveedores.kpi_freelance')} value={panorama.by_kind.freelance ?? 0} />
          <KpiCard icon={<Building2 size={16} />} label={t('proveedores.kpi_empresas')} value={panorama.by_kind.company ?? 0}
            sub={t('proveedores.kpi_modos', { personas: panorama.by_mode.staff_augmentation ?? 0, outsourcing: panorama.by_mode.outsourcing ?? 0, servicios: panorama.by_mode.managed_services ?? 0 })} />
          <KpiCard icon={<ShieldCheck size={16} />} label={t('proveedores.kpi_documentos')} value={panorama.documents_expired + panorama.documents_expiring}
            sub={t('proveedores.kpi_documentos_sub', { caducados: panorama.documents_expired, por_caducar: panorama.documents_expiring })}
            danger={panorama.documents_expired > 0} warning={panorama.documents_expiring > 0} />
          <KpiCard icon={<CalendarClock size={16} />} label={t('proveedores.kpi_revisiones')} value={panorama.reviews_overdue} warning={panorama.reviews_overdue > 0} />
          <KpiCard icon={<Scale size={16} />} label={t('proveedores.kpi_estados')} value={panorama.statements_pending_approval}
            sub={t('proveedores.kpi_disputados', { n: panorama.statements_disputed })} danger={panorama.statements_disputed > 0} />
          <KpiCard icon={<Coins size={16} />} label={t('proveedores.kpi_prevision_mes')} value={fmtMoneda(panorama.forecast_month, { moneda: panorama.currency })} />
        </div>
      )}

      {subs.length > 0 && (
        <div className="sub-actions-bar">
          <ViewToggle view={view} onChange={setView} />
        </div>
      )}

      {isLoading ? (
        <Spinner />
      ) : subs.length === 0 ? (
        <EmptyState
          icon={<Handshake size={28} />}
          title={t('subcontractors.sin_subcontratistas')}
          description={t('subcontractors.vacio_descripcion')}
          action={gestionar ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('subcontractors.nuevo_subcontratista')}</Button> : undefined}
        />
      ) : view === 'grid' ? (
        <div className="sub-grid">
          {sortedSubs.map(s => (
            <div key={s.id} onClick={() => setSelected(s)}
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => setSelected(s)) }}
              className="sub-card"
            >
              <div className="sub-card-head">
                <div className="u-min0">
                  <div className="u-md-700">{s.name}</div>
                  {s.company && <div className="u-text2-xs">{s.company}</div>}
                </div>
              </div>
              <InsigniasDeProveedor sub={s} />
              {s.email && <div className="sub-mail"><Mail size={12} aria-hidden />{s.email}</div>}
              <div className="sub-card-meta">
                <Users size={12} aria-hidden />{t((s.worker_count || 0) === 1 ? 'subcontractors.n_persona' : 'subcontractors.n_personas', { n: s.worker_count || 0 })} · {t((s.assignment_count || 0) === 1 ? 'subcontractors.n_asignacion' : 'subcontractors.n_asignaciones', { n: s.assignment_count || 0 })}
              </div>
              {gestionar && (
              <div className="sub-card-actions">
                <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={e => { e.stopPropagation(); abrirEdicion(s) }}>
                  {t('subcontractors.edit')}
                </Button>
                <Button size="sm" variant="ghost" className="sub-borrar" icon={<Trash2 size={14} />} onClick={e => { e.stopPropagation(); confirmarEliminar(s) }}>
                  {t('subcontractors.delete')}
                </Button>
              </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="ds-card ds-card--plano">
          <div className="sub-table-head">
            <SortableTH col="name" sort={subSort} onSort={setSubSort}>{t('subcontractors.col_empresa_nombre')}</SortableTH>
            <SortableTH col="code" sort={subSort} onSort={setSubSort}>{t('subcontractors.codigo')}</SortableTH>
            <SortableTH col="email" sort={subSort} onSort={setSubSort}>{t('subcontractors.email')}</SortableTH>
            <SortableTH col="worker_count" sort={subSort} onSort={setSubSort}>{t('subcontractors.kpi_personas')}</SortableTH>
            <SortableTH col="assignment_count" sort={subSort} onSort={setSubSort}>{t('subcontractors.kpi_asignaciones')}</SortableTH>
            <SortableTH col="is_active" sort={subSort} onSort={setSubSort}>{t('subcontractors.col_estado')}</SortableTH>
            <span>{t('subcontractors.col_acciones')}</span>
          </div>
          {sortedSubs.map(s => (
            <div key={s.id} className="sub-row"
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => setSelected(s)) }}
              onClick={() => setSelected(s)}>
              <div>
                <div className="u-base-600">{s.name}</div>
                {s.company && <div className="u-text2-xs">{s.company}</div>}
                <InsigniasDeProveedor sub={s} compacto />
              </div>
              <span className="u-text2-mono-xs">{s.code || '—'}</span>
              <span className="u-text2-sm">{s.email || '—'}</span>
              <span className="u-sm">{s.worker_count || 0}</span>
              <span className="u-sm">{s.assignment_count || 0}</span>
              <span>
                <StatusBadge kind={s.is_active ? 'success' : 'danger'} caps={false}>
                  {s.is_active ? t('subcontractors.activo') : t('subcontractors.inactivo')}
                </StatusBadge>
              </span>
              <div className="sub-row-actions">
                {gestionar && <>
                <IconButton onClick={e => { e.stopPropagation(); abrirEdicion(s) }}
                  ariaLabel={t('subcontractors.editar_a', { name: s.name })} title={t('subcontractors.editar_a', { name: s.name })}><Pencil size={14} aria-hidden /></IconButton>
                <IconButton className="sub-borrar" onClick={e => { e.stopPropagation(); confirmarEliminar(s) }}
                  ariaLabel={t('subcontractors.eliminar_a', { name: s.name })} title={t('subcontractors.eliminar_a', { name: s.name })}><Trash2 size={14} aria-hidden /></IconButton>
                </>}
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <AltaDeProveedor onClose={() => setShowCreate(false)} onCreado={setSelected} />}

      {showEdit && editTarget && (
        <Modal open title={t('subcontractors.editar_subcontratista')} onClose={() => { setShowEdit(false); setEditTarget(null) }} width={520}>
          <div className="sub-form-grid sub-form-grid--mb16">
            <div>
              <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="sub-label">{t('subcontractors.nombre_razon_social')}</label>
              <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} className="sub-input" />{msgEdit('name')}
            </div>
            <div>
              <label id={`${idCampo}-8-et`} htmlFor={`${idCampo}-8`} className="sub-label">{t('subcontractors.empresa')}</label>
              <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-8-et`} value={editForm.company} onChange={e => setEditForm(f=>({...f,company:e.target.value}))} className="sub-input" />{msgEdit('company')}
            </div>
            <div>
              <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.email')}</label>
              <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-9-et`} type="email" value={editForm.email} onChange={e => setEditForm(f=>({...f,email:e.target.value}))} className="sub-input" />{msgEdit('email')}
            </div>
            <div>
              <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.telefono')}</label>
              <input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-10-et`} value={editForm.phone} onChange={e => setEditForm(f=>({...f,phone:e.target.value}))} className="sub-input" />{msgEdit('phone')}
            </div>
            <div>
              <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.nif_vat')}</label>
              <input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} value={editForm.vat_number} onChange={e => setEditForm(f=>({...f,vat_number:e.target.value}))} className="sub-input" />{msgEdit('vat_number')}
            </div>
            <div>
              <label id={`${idCampo}-12-et`} htmlFor={`${idCampo}-12`} className="sub-label">{t('subcontractors.moneda')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-12`} value={editForm.currency} onChange={e => setEditForm(f=>({...f,currency:e.target.value}))} className="sub-input">
                {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
              </Select>{msgEdit('currency')}
            </div>
          </div>
          <div className="u-mb-16">
            <label id={`${idCampo}-13-et`} htmlFor={`${idCampo}-13`} className="sub-label">{t('subcontractors.notes')}</label>
            <textarea id={`${idCampo}-13`} aria-labelledby={`${idCampo}-13-et`} value={editForm.notes} onChange={e => setEditForm(f=>({...f,notes:e.target.value}))} className="sub-input sub-textarea" />{msgEdit('notes')}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => { setShowEdit(false); setEditTarget(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => update({id: editTarget.id, ...editForm})} loading={updating} disabled={!editForm.name || updating}>{t('subcontractors.save_changes')}</Button>
          </div>
        </Modal>
      )}
      </div>
    </PageShell>
  )
}
