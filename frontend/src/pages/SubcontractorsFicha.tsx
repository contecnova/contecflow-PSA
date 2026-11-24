// Ficha de un subcontratista (pestañas, asignaciones, horas y facturas). 23-11-2026: troceado de SubcontractorsPage sin cambio de comportamiento.
import { useState, useId, useEffect } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { extractErr, fmtDate, fmtHours, fmtNumber } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseSubsApi } from '../services/api'
import type { SubAsignacion, SubConciliacion } from '../services/api/tipos-alm'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, ArrowLeft, Briefcase, Building2, Clock, Coins, FileText, Gauge, HardHat, Layers, LayoutDashboard, Plus, Receipt, Scale, ShieldCheck, Square, Users } from 'lucide-react'
import { Button, Card, EmptyState, KpiCard, Modal, Spinner, Tabs, Table, Select, TablaSimple, Input } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { redondear2 } from '../utils/redondeo'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { pestanasDeLaFicha, esFreelance } from './proveedores/logica'
import type { PestanaDeFicha } from './proveedores/logica'
import { InsigniasDeProveedor, usePermisosDeProveedores } from './proveedores/comunes'
import PestanaResumen from './proveedores/PestanaResumen'
import PestanaContratos from './proveedores/PestanaContratos'
import PestanaServicios from './proveedores/PestanaServicios'
import PestanaPaquetes from './proveedores/PestanaPaquetes'
import PestanaConsumo from './proveedores/PestanaConsumo'
import PestanaRendimiento from './proveedores/PestanaRendimiento'
import PestanaCumplimiento from './proveedores/PestanaCumplimiento'
import { useListaDeProyectos } from '../hooks/useListas'
import { ESTADOS_FACTURA, type Invoice, PAPELES, type Sub, TIPO_FACTURA, type Timelog, type Worker } from './SubcontractorsComun'
import { WorkersPanel } from './SubcontractorsTrabajadores'

export function SubDetail({ sub, onBack, onCambio }: { sub: Sub; onBack: () => void; onCambio?: (s: Sub) => void }) {
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
  const { data: projects = [] } = useListaDeProyectos({ status: 'active' })

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
              <Select label={<>{t('externos.persona_sin_acceso')}*</>} placeholder={false} id={`${idCampo}-tlw`} value={tlForm.worker_id} onChange={e => setTlForm(f=>({...f,worker_id:e.target.value}))}>
                <option value="">{sinAcceso.length ? t('subcontractors.seleccionar') : t('externos.nadie_sin_acceso')}</option>
                {sinAcceso.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
              </Select>
            </div>
            <Select label={t('subcontractors.asignacion')} placeholder={false} id={`${idCampo}-1`} value={tlForm.assignment_id} onChange={e => setTlForm(f=>({...f,assignment_id:e.target.value}))}>
                <option value="">{t('subcontractors.sin_asignacion')}</option>
                {assignments.map(a => <option key={a.id} value={a.id}>{a.project_code} — {a.project_name}</option>)}
              </Select>
            <DateInput label={t('subcontractors.col_fecha')} id={`${idCampo}-2`} value={tlForm.log_date} onChange={e => setTlForm(f=>({...f,log_date:e.target.value}))} />
            <Input label={t('subcontractors.horas_obligatorio')} id={`${idCampo}-3`} type="number" value={tlForm.hours} onChange={e => setTlForm(f=>({...f,hours:+e.target.value}))} min="0.5" step="0.5" />
            <Input label={t('subcontractors.referencia_de_tarea')} id={`${idCampo}-a599`} value={tlForm.task_reference} onChange={e => setTlForm(f=>({...f,task_reference:e.target.value}))} placeholder={t('subcontractors.referencia_de_tarea')} />
            <div className="u-col-full">
              <Input label={t('subcontractors.descripcion')} id={`${idCampo}-tl-desc`} value={tlForm.description} onChange={e => setTlForm(f=>({...f,description:e.target.value}))} placeholder={t('subcontractors.descripcion_del_parte')} />
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
            <Input label={t('subcontractors.n_factura_obligatorio')} id={`${idCampo}-a619`} value={invForm.invoice_number} onChange={e => setInvForm(f=>({...f,invoice_number:e.target.value}))} placeholder={t('subcontractors.numero_de_factura')} />
            <DateInput label={t('subcontractors.fecha_emision')} id={`${idCampo}-4`} value={invForm.issue_date} onChange={e => setInvForm(f=>({...f,issue_date:e.target.value}))} />
            <Input label={t('subcontractors.importe_base_moneda', { moneda: fmtMoneda.simbolo })} id={`${idCampo}-5`} type="number" value={invForm.amount} onChange={e => setInvForm(f=>({...f,amount:e.target.value}))} min="0" step="0.01" />
            <Input label={t('subcontractors.iva_pct')} id={`${idCampo}-6`} type="number" value={invForm.tax_pct} onChange={e => { setIvaSubTocado(true); setInvForm(f=>({...f,tax_pct:+e.target.value})) }} min="0" max="30" />
            {invForm.amount && (
              <div className="sub-total-box">
                {t('subcontractors.total_con_iva')} <strong>{fmtMoneda(redondear2(+invForm.amount * (1 + invForm.tax_pct/100)))}</strong>
              </div>
            )}
            <div className="u-col-full">
              <Input label={t('subcontractors.descripcion')} id={`${idCampo}-7`} value={invForm.description} onChange={e => setInvForm(f=>({...f,description:e.target.value}))} />
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
              <Select label={t('subcontractors.proyecto_obligatorio')} placeholder={false} id={`${idCampo}-8`} value={asgForm.project_id} onChange={e => setAsgForm(f=>({...f,project_id:e.target.value}))}>
                <option value="">{t('subcontractors.seleccionar')}</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </Select>
            </div>
            <Select label={<>{t('externos.persona')}*</>} placeholder={false} id={`${idCampo}-asw`} value={asgForm.worker_id} onChange={e => setAsgForm(f=>({...f,worker_id:e.target.value}))}>
                <option value="">{t('subcontractors.seleccionar')}</option>
                {trabajadoresActivos.map(w => <option key={w.id} value={w.id}>{w.name}{w.role ? ` (${w.role})` : ''}</option>)}
              </Select>
            <Select label={t('externos.tarifa')} placeholder={false} id={`${idCampo}-asr`} value={asgForm.rate_id} onChange={e => setAsgForm(f=>({...f,rate_id:e.target.value}))}>
                <option value="">{tarifas.length ? t('externos.tarifa_de_la_persona') : t('externos.sin_tarifas')}</option>
                {tarifas.map(r => <option key={r.id} value={r.id}>{[r.description, r.cost_rate != null ? fmtMoneda(r.cost_rate, { moneda: r.currency }) : null].filter(Boolean).join(' · ')}</option>)}
              </Select>
            <Select label={t('externos.papel')} placeholder={false} id={`${idCampo}-asp`} value={asgForm.member_role} onChange={e => setAsgForm(f=>({...f,member_role:e.target.value}))}>
                <option value="">{t('externos.papel_por_defecto')}</option>
                {PAPELES.map(r => <option key={r} value={r}>{t(`externos.papel_${r}`)}</option>)}
              </Select>
            <Input label={t('externos.dedicacion')} id={`${idCampo}-asa`} type="number" min="0" max="100" step="5" value={asgForm.allocation_pct} onChange={e => setAsgForm(f=>({...f,allocation_pct:e.target.value}))} />
            <Input label={t('subcontractors.n_pedido_po')} id={`${idCampo}-a663`} value={asgForm.po_number} onChange={e => setAsgForm(f=>({...f,po_number:e.target.value}))} placeholder={t('subcontractors.numero_de_pedido')} />
            <Input label={t('subcontractors.techo_po_moneda', { moneda: fmtMoneda.simbolo })} id={`${idCampo}-9`} type="number" value={asgForm.po_amount} onChange={e => setAsgForm(f=>({...f,po_amount:e.target.value}))} />
            <Input label={t('subcontractors.horas_contratadas')} id={`${idCampo}-10`} type="number" value={asgForm.hours_contracted} onChange={e => setAsgForm(f=>({...f,hours_contracted:e.target.value}))} />
            <DateInput label={t('subcontractors.fecha_inicio')} id={`${idCampo}-11`} value={asgForm.start_date} onChange={e => setAsgForm(f=>({...f,start_date:e.target.value}))} />
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
