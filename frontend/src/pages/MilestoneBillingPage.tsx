/**
 * MilestoneBillingPage — Facturación por hito.
 *
 * 16-11-2026: título = el del menú ("Facturación por hito"); "milestone" →
 * "hito" en castellano; pestaña "Dashboard pendientes" → "Pendientes de
 * acción"; selector de proyecto en una barra (Card) bajo la cabecera y
 * "Nuevo hito" en la cabecera con icono; vacíos con EmptyState e icono lucide
 * (antes emojis); estados y acciones con iconos lucide en vez de
 * emojis/símbolos; botones del kit (antes botones propios); formulario con
 * Input/FormField/DateInput; fechas con fmtDate según idioma (antes ISO).
 * Dentro de la ficha del proyecto (`projectId`) no pinta una segunda cabecera.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation } from '@tanstack/react-query'
import { milestonesApi, projectsApi } from '../services/api'
import type { ProjectListItem } from '../services/api/projects'
import type { EstadoDeFacturacionDeHito, HitoDeFacturacion } from '../services/api/tipos-finanzas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  AlertTriangle, ArrowRight, CalendarDays, Check, CheckCircle2, Circle, Clock, Flag, FolderKanban,
  FolderOpen, Inbox, ListTodo, Plus, Receipt, RotateCcw, Send, X, XCircle,
} from 'lucide-react'
import { Button, Card, EmptyState, FormField, Input, Modal, Select, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import DsBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './MilestoneBillingPage.css'
type BillingStatus = EstadoDeFacturacionDeHito
/** El hito de la lista del proyecto o del panel de pendientes (que añade el proyecto). */
type MilestoneItem = HitoDeFacturacion & { project_name?: string }


// ── Estado: etiqueta, tipo de badge e icono ───────────────────────────────────
const STATUS: Record<BillingStatus, { label: string; kind: StatusBadgeKind; icon: ReactNode }> = {
  pending:          { label: 'pagina_mbill.pendiente',           kind: 'neutral', icon: <Circle size={12} aria-hidden /> },
  completed:        { label: 'pagina_mbill.completado',          kind: 'accent',  icon: <Check size={12} aria-hidden /> },
  pending_approval: { label: 'pagina_mbill.esperando_aprobacion', kind: 'warning', icon: <Clock size={12} aria-hidden /> },
  approved:         { label: 'pagina_mbill.aprobado',            kind: 'success', icon: <CheckCircle2 size={12} aria-hidden /> },
  rejected:         { label: 'pagina_mbill.rechazado_2',         kind: 'danger',  icon: <XCircle size={12} aria-hidden /> },
  invoiced:         { label: 'pagina_mbill.facturado',           kind: 'purple',  icon: <Receipt size={12} aria-hidden /> },
}

// ── Badge de estado ───────────────────────────────────────────────────────────
function StatusBadge({ status }: { status?: BillingStatus }) {
  const t = useAppT()
  const s = status ? (STATUS[status] || STATUS.pending) : STATUS.pending
  return (
    <DsBadge kind={s.kind} caps={false}><span className="mbill-badge">{s.icon}{t(s.label)}</span></DsBadge>
  )
}

// ── Modal de rechazo ──────────────────────────────────────────────────────────
function RejectModal({ milestone, onClose, onReject }: { milestone: MilestoneItem; onClose: () => void; onReject: (reason: string) => void }) {
  const t = useAppT()
  const fmtMoneda = useFormatoMoneda()
  const [reason, setReason] = useState('')
  // serialize_milestone: el hito tiene `name` y `billing_amount` (no `title`, `code`, `amount` ni `currency`).
  const milestoneLabel = milestone.name || milestone.id
  return (
    <Modal open title={t('pagina_mbill.rechazar_milestone')} onClose={onClose} size="sm">
      {milestoneLabel && (
        <div className="mbill-ref">
          {t('pagina_mbill.milestone')}{' '}<strong className="u-text1">{milestoneLabel}</strong>
          {milestone.billing_amount != null && (
            <span className="mbill-ref__importe">· {fmtMoneda(milestone.billing_amount)}</span>
          )}
        </div>
      )}
      <FormField label={t('milestonebilling.motivo_del_rechazo')}>
        <textarea value={reason} onChange={e => setReason(e.target.value)} className="mbill-textarea"
          placeholder={t('milestonebilling.describe_el_motivo_del_rechazo')} />
      </FormField>
      <div className="mbill-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="danger" icon={<X size={14} />} onClick={() => onReject(reason)} disabled={!reason.trim()}>{t('pagina_mbill.confirmar_rechazo')}</Button>
      </div>
    </Modal>
  )
}

// ── Tarjeta de hito ───────────────────────────────────────────────────────────
function MilestoneCard({ m, projectName, onRefresh }: { m: MilestoneItem; projectName: string; onRefresh: () => void | Promise<unknown> }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const [showReject, setShowReject] = useState(false)
  const [loading, setLoading] = useState<'complete' | 'uncomplete' | 'request' | 'approve' | 'reject' | 'invoice' | null>(null)

  const act = async (action: 'complete' | 'uncomplete' | 'request' | 'approve' | 'reject' | 'invoice', payload?: string) => {
    setLoading(action)
    try {
      // Completar y revertir devuelven el hito sin mensaje; el resto trae `message`.
      let mensaje: string | undefined
      if (action === 'complete')        await milestonesApi.complete(m.id)
      if (action === 'uncomplete')      await milestonesApi.uncomplete(m.id)
      if (action === 'request')         mensaje = (await milestonesApi.requestApproval(m.id, {})).data.message
      if (action === 'approve')         mensaje = (await milestonesApi.approve(m.id, { approved: true })).data.message
      if (action === 'reject')          mensaje = (await milestonesApi.approve(m.id, { approved: false, rejection_reason: payload })).data.message
      if (action === 'invoice')         mensaje = (await milestonesApi.generateInvoice(m.id)).data.message
      toast.success(mensaje || t('pagina_mbill.accion_completada'))
      onRefresh()
    } catch (e: unknown) {
      toast.error(extractErr(e, t('pagina_mbill.error')))
    } finally {
      setLoading(null)
      setShowReject(false)
    }
  }


  return (
    <Card className="mbill-hito">
      <div className="mbill-hito__fila">
        <div className="u-flex1-min0">
          <div className="mbill-hito__estado">
            <StatusBadge status={m.billing_status} />
            {m.due_date && (
              <span className="mbill-meta"><CalendarDays size={13} aria-hidden />{fmtDate(m.due_date)}</span>
            )}
          </div>
          <div className="mbill-hito__nombre">{m.name}</div>
          <div className="mbill-hito__datos">
            {projectName && <span className="mbill-meta"><FolderOpen size={13} aria-hidden />{projectName}</span>}
            {m.billing_amount ? (
              <span className="mbill-importe">{fmtMoneda(m.billing_amount)}</span>
            ) : m.billing_pct ? (
              <span className="mbill-pct">{m.billing_pct}{t('milestonebilling.del_contrato')}</span>
            ) : null}
          </div>
          {m.rejection_reason && (
            <div className="mbill-aviso mbill-aviso--rechazo">
              <AlertTriangle size={13} aria-hidden />
              <span>{t('pagina_mbill.rechazado')}{' '}{m.rejection_reason}</span>
            </div>
          )}
          {m.invoice_id && (
            <div className="mbill-aviso mbill-aviso--factura">
              <Receipt size={13} aria-hidden />
              <span>{t('pagina_mbill.factura_generada')}</span>
            </div>
          )}
        </div>

        {/* Acciones según estado */}
        <div className="mbill-hito__acciones">
          {m.billing_status === 'pending' && (
            <Button size="sm" icon={<Check size={13} />} onClick={() => act('complete')} loading={loading === 'complete'}>
              {t('pagina_mbill.marcar_completado')}
            </Button>
          )}
          {m.billing_status === 'completed' && (
            <>
              <Button size="sm" variant="ghost" icon={<RotateCcw size={13} />} onClick={() => act('uncomplete')} loading={loading === 'uncomplete'}>
                {t('pagina_mbill.desmarcar')}
              </Button>
              <Button size="sm" icon={<Send size={13} />} onClick={() => act('request')} loading={loading === 'request'}>
                {t('milestonebilling.solicitar_aprobacion')}
              </Button>
            </>
          )}
          {m.billing_status === 'pending_approval' && (
            <>
              <Button size="sm" variant="secondary" icon={<X size={13} />} onClick={() => setShowReject(true)}>
                {t('pagina_mbill.rechazar')}
              </Button>
              <Button size="sm" icon={<CheckCircle2 size={13} />} onClick={() => act('approve')} loading={loading === 'approve'}>
                {t('pagina_mbill.aprobar')}
              </Button>
            </>
          )}
          {m.billing_status === 'approved' && (
            <Button size="sm" icon={<Receipt size={13} />} onClick={() => act('invoice')} loading={loading === 'invoice'}>
              {t('pagina_mbill.generar_factura')}
            </Button>
          )}
          {m.billing_status === 'rejected' && (
            <Button size="sm" icon={<RotateCcw size={13} />} onClick={() => act('complete')} loading={loading === 'complete'}>
              {t('pagina_mbill.re_completar')}
            </Button>
          )}
        </div>
      </div>

      {showReject && (
        <RejectModal
          milestone={m}
          onClose={() => setShowReject(false)}
          onReject={reason => act('reject', reason)}
        />
      )}
    </Card>
  )
}

// ── Formulario de nuevo hito ──────────────────────────────────────────────────
function NewMilestoneModal({ projectId, onClose, onSave }: { projectId: string; onClose: () => void; onSave: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState({ name: '', description: '', due_date: '', billing_amount: '', billing_pct: '' })
  const { mutate, isPending } = useMutation({
    mutationFn: () => milestonesApi.create(projectId, {
      ...form,
      billing_amount: form.billing_amount ? +form.billing_amount : null,
      billing_pct:    form.billing_pct    ? +form.billing_pct    : null,
    }),
    onSuccess: () => { toast.success(t('pagina_mbill.milestone_creado')); onSave() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open title={t('milestonebilling.nuevo_milestone')} onClose={onClose} size="md">
      <div className="mbill-form">
        <Input label={t('pagina_mbill.nombre')} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          placeholder={t('milestonebilling.nombre_del_milestone')} />
        <FormField label={t('milestonebilling.fecha_limite')}>
          <DateInput value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
        </FormField>
        <div className="mbill-form__dos">
          <Input type="number" label={`${t('pagina_mbill.importe_a_facturar_2')} (${fmtMoneda.simbolo})`} value={form.billing_amount}
            onChange={e => setForm(f => ({ ...f, billing_amount: e.target.value }))} placeholder={t('pagina_mbill.importe_a_facturar_2')} />
          <Input type="number" label={t('milestonebilling.o_del_contrato')} value={form.billing_pct}
            onChange={e => setForm(f => ({ ...f, billing_pct: e.target.value }))} placeholder={t('milestonebilling.porcentaje_del_contrato')} />
        </div>
        <FormField label={t('milestonebilling.descripcion')}>
          <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="mbill-textarea" />
        </FormField>
      </div>
      <div className="mbill-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button icon={<Plus size={14} />} onClick={() => mutate()} loading={isPending} disabled={!form.name}>{t('pagina_mbill.crear_milestone')}</Button>
      </div>
    </Modal>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
/** Rev. 173: con `projectId` va dentro de la ficha del proyecto, con el proyecto fijo y sin selector. */
export default function MilestoneBillingPage({ projectId }: { projectId?: string } = {}): JSX.Element {
  const t = useAppT()
  const [selectedProject, setSelectedProject] = useState(projectId ?? '')
  const [showNew, setShowNew]   = useState(false)
  const [tab, setTab] = useState<'project' | 'dashboard'>('project')

  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => r.data),
    enabled: !projectId,
  })

  const { data: milestones = [], refetch } = useQuery<MilestoneItem[]>({
    queryKey: ['milestones', selectedProject],
    queryFn: () => milestonesApi.list(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: dashboard = [], refetch: refetchDash } = useQuery<MilestoneItem[]>({
    queryKey: ['milestones-dashboard'],
    queryFn: () => milestonesApi.dashboard().then(r => r.data),
    enabled: !projectId,
  })

  const projectName = projectId ? '' : (projects.find(p => String(p.id) === String(selectedProject))?.name || '')

  // Agrupados por estado
  const byStatus = milestones.reduce<Record<string, MilestoneItem[]>>((acc, m) => {
    const key = m.billing_status || 'pending'
    acc[key] = [...(acc[key] || []), m]
    return acc
  }, {})

  const botonNuevo = selectedProject && tab === 'project'
    ? <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('milestonebilling.nuevo_milestone_2')}</Button>
    : null

  const vistaProyecto = (
    <>
      {!projectId && (
        <Card className="mbill-filtros">
          <Select label={t('pagina_mbill.proyecto')} value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
            className="mbill-filtros__proyecto"
            options={projects.map(p => ({ value: String(p.id), label: p.code ? `${p.code} — ${p.name}` : p.name }))} />
        </Card>
      )}
      {projectId && botonNuevo && <div className="mbill-barra">{botonNuevo}</div>}

      {!selectedProject ? (
        <Card>
          <EmptyState icon={<FolderKanban size={28} />} title={t('milestonebilling.selecciona_un_proyecto')} description={t('pagina_mbill.elige_un_proyecto_para_gestionar_sus')} />
        </Card>
      ) : milestones.length === 0 ? (
        <Card>
          <EmptyState icon={<Flag size={28} />} title={t('milestonebilling.sin_milestones')} description={t('pagina_mbill.crea_el_primer_milestone_para_empezar')}
            action={<Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('milestonebilling.nuevo_milestone_2')}</Button>} />
        </Card>
      ) : (
        <>
          {/* Flujo visual */}
          <div className="mbill-flujo" aria-hidden>
            {Object.entries(STATUS).map(([k, v], i) => (
              <div key={k} className="mbill-flujo__paso">
                <span className={(byStatus[k]?.length ?? 0) > 0 ? '' : 'mbill-flujo__vacio'}>
                  <DsBadge kind={v.kind} caps={false}>
                    <span className="mbill-badge">{v.icon}{t(v.label)}{(byStatus[k]?.length ?? 0) > 0 ? ` (${byStatus[k].length})` : ''}</span>
                  </DsBadge>
                </span>
                {i < Object.keys(STATUS).length - 1 && <ArrowRight size={14} className="mbill-flujo__flecha" />}
              </div>
            ))}
          </div>

          {/* Hitos ordenados por flujo */}
          <div className="mbill-lista">
            {['pending_approval', 'approved', 'completed', 'pending', 'rejected', 'invoiced'].map(status =>
              byStatus[status]?.map(m => (
                <MilestoneCard key={m.id} m={m} projectName={projectName} onRefresh={refetch} />
              ))
            )}
          </div>
        </>
      )}
    </>
  )

  const modalNuevo = showNew && (
    <NewMilestoneModal
      projectId={selectedProject}
      onClose={() => setShowNew(false)}
      onSave={() => { setShowNew(false); refetch() }}
    />
  )

  // Dentro de la ficha del proyecto: sin cabecera ni pestañas propias.
  if (projectId) {
    return <div className="u-stack-16">{vistaProyecto}{modalNuevo}</div>
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Flag size={18} />}
        title={t('nav.milestone_billing')}
        subtitle={t('milestone_billing.subtitle')}
        actions={botonNuevo}
        showListExport={false}
      />

      <div className="u-stack-16">
        <Tabs
          items={[
            { id: 'project',   label: t('pagina_mbill.por_proyecto'), icon: <FolderKanban size={14} /> },
            { id: 'dashboard', label: t('pagina_mbill.dashboard_pendientes'), icon: <ListTodo size={14} />, count: dashboard.length || undefined },
          ]}
          active={tab}
          onChange={(id) => setTab(id as 'project' | 'dashboard')}
          ariaLabel={t('pagina_mbill.facturacion_por_hitos')}
        />

        {tab === 'project' && vistaProyecto}

        {tab === 'dashboard' && (
          dashboard.length === 0 ? (
            <Card>
              <EmptyState icon={<Inbox size={28} />} title={t('milestonebilling.sin_pendientes')} description={t('pagina_mbill.no_hay_milestones_pendientes_de_accion')} />
            </Card>
          ) : (
            <>
              <div className="mbill-resumen">
                {dashboard.length} {t('milestonebilling.milestones_requieren_accion_en_todos_los_proyectos')}
              </div>
              <div className="mbill-lista">
                {dashboard.map(m => (
                  <MilestoneCard
                    key={m.id} m={m}
                    projectName={m.project_name || ''}
                    onRefresh={refetchDash}
                  />
                ))}
              </div>
            </>
          )
        )}
      </div>

      {modalNuevo}
    </PageShell>
  )
}
