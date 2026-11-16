import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { milestonesApi, projectsApi } from '../services/api'
import type { ProjectListItem } from '../services/api/projects'
import type { EstadoDeFacturacionDeHito, HitoDeFacturacion } from '../services/api/tipos-finanzas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Flag } from 'lucide-react'
import { Button, Modal, EmptyState, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import DsBadge from '../components/ui/StatusBadge'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './MilestoneBillingPage.css'
type BillingStatus = EstadoDeFacturacionDeHito
/** El hito de la lista del proyecto o del panel de pendientes (que añade el proyecto). */
type MilestoneItem = HitoDeFacturacion & { project_name?: string }


// ── Colores y labels por estado ───────────────────────────────────────────────
const STATUS: Record<BillingStatus, { label: string; color: string; bg: string; icon: string }> = {
  pending:          { label: 'pagina_mbill.pendiente',          color: 'var(--text-2)', bg: 'var(--surface-4)',   icon: '○' },
  completed:        { label: 'pagina_mbill.completado',          color: 'var(--accent)', bg: 'var(--accent-muted)', icon: '✓' },
  pending_approval: { label: 'pagina_mbill.esperando_aprobacion',color: 'var(--warning)', bg: 'var(--warning-bg)', icon: '⏳' },
  approved:         { label: 'pagina_mbill.aprobado',            color: 'var(--success)', bg: 'var(--success-bg)', icon: '✅' },
  rejected:         { label: 'pagina_mbill.rechazado_2',           color: 'var(--danger)', bg: 'var(--danger-bg)', icon: '✗' },
  invoiced:         { label: 'pagina_mbill.facturado',           color: 'var(--purple)', bg: 'var(--purple-bg)', icon: '🧾' },
}

// ── Badge de estado ───────────────────────────────────────────────────────────
function StatusBadge({ status }: { status?: BillingStatus }) {
  const t = useAppT()
  const s = status ? (STATUS[status] || STATUS.pending) : STATUS.pending
  return (
    <DsBadge color={s.color} caps={false}>{s.icon} {t(s.label)}</DsBadge>
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
    <Modal open title={t('pagina_mbill.rechazar_milestone')} onClose={onClose} width={420}>
      {milestoneLabel && (
        <div className="mbill-card">
          {t('pagina_mbill.milestone')}{' '}<strong className="u-text1">{milestoneLabel}</strong>
          {milestone.billing_amount != null && (
            <span className="mbill-label">· {fmtMoneda(milestone.billing_amount)}</span>
          )}
        </div>
      )}
      <div className="u-mb-16">
        <label className="milestone-billing-page-e6">{t('milestonebilling.motivo_del_rechazo')}</label>
        <textarea value={reason} onChange={e => setReason(e.target.value)}
          className="milestone-billing-page-e1"
          placeholder={t('milestonebilling.describe_el_motivo_del_rechazo')} aria-label={t('milestonebilling.motivo_del_rechazo_2')} />
      </div>
      <div className="u-actions-8">
        <button onClick={onClose} className="u-btn-outline-sm">{t('common.cancel')}</button>
        <Button variant="danger" onClick={() => onReject(reason)} disabled={!reason.trim()}>{t('pagina_mbill.confirmar_rechazo')}</Button>
      </div>
    </Modal>
  )
}

// ── Milestone card ────────────────────────────────────────────────────────────
function MilestoneCard({ m, projectName, onRefresh }: { m: MilestoneItem; projectName: string; onRefresh: () => void | Promise<unknown> }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const toast = useToast()
  const _qc = useQueryClient()
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

  const status = m.billing_status || 'pending'
  const s = STATUS[status] || STATUS.pending

  return (
    <div className="mbill-box mileston-sx1 milestone-billing-page-e2" style={{ '--milestone-billing-page-border': `1px solid ${alpha(s.color, '30')}` } as CSSProperties}>
      <div className="mbill-row">
        <div className="u-flex1-min0">
          <div className="mbill-row-2">
            <StatusBadge status={m.billing_status} />
            {m.due_date && (
              <span className="u-text2-xs">📅 {m.due_date}</span>
            )}
          </div>
          <div className="mbill-box-2">{m.name}</div>
          <div className="u-text2-sm">
            📁 {projectName}
            {m.billing_amount && (
              <span className="mbill-label-2">
                💶 {fmtMoneda(m.billing_amount)}
              </span>
            )}
            {m.billing_pct && !m.billing_amount && (
              <span className="mbill-label-3">
                {m.billing_pct}{t('milestonebilling.del_contrato')}
              </span>
            )}
          </div>
          {m.rejection_reason && (
            <div className="mbill-card-2">
              {t('pagina_mbill.rechazado')}{' '}{m.rejection_reason}
            </div>
          )}
          {m.invoice_id && (
            <div className="mbill-card-3">
              {t('pagina_mbill.factura_generada')}
            </div>
          )}
        </div>

        {/* Acciones según estado */}
        <div className="mbill-row-3">
          {m.billing_status === 'pending' && (
            <Button size="sm" onClick={() => act('complete')} loading={loading === 'complete'}>
              {t('pagina_mbill.marcar_completado')}
            </Button>
          )}
          {m.billing_status === 'completed' && (
            <>
              <button onClick={() => act('uncomplete')} className="mbill-btn">
                {t('pagina_mbill.desmarcar')}
              </button>
              <Button size="sm" onClick={() => act('request')} loading={loading === 'request'}>
                {t('milestonebilling.solicitar_aprobacion')}
              </Button>
            </>
          )}
          {m.billing_status === 'pending_approval' && (
            <>
              <button onClick={() => setShowReject(true)}
                className="mbill-btn-2">
                {t('pagina_mbill.rechazar')}
              </button>
              <Button size="sm" onClick={() => act('approve')} loading={loading === 'approve'}>
                {t('pagina_mbill.aprobar')}
              </Button>
            </>
          )}
          {m.billing_status === 'approved' && (
            <Button size="sm" onClick={() => act('invoice')} loading={loading === 'invoice'}>
              {t('pagina_mbill.generar_factura')}
            </Button>
          )}
          {m.billing_status === 'rejected' && (
            <Button size="sm" onClick={() => act('complete')} loading={loading === 'complete'}>
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
    </div>
  )
}

// ── Formulario de nuevo milestone ─────────────────────────────────────────────
function NewMilestoneModal({ projectId, onClose, onSave }: { projectId: string; onClose: () => void; onSave: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
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
    <Modal open title={t('milestonebilling.nuevo_milestone')} onClose={onClose} width={500}>
      <div className="mbill-stack">
        <div>
          <label id={`${idCampo}-eta244`} htmlFor={`${idCampo}-a244`} className="milestone-billing-page-e6">{t('pagina_mbill.nombre')}</label>
          <input id={`${idCampo}-a244`} aria-labelledby={`${idCampo}-eta244`} value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} className="milestone-billing-page-e7" placeholder={t('milestonebilling.nombre_del_milestone')} />
        </div>
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="milestone-billing-page-e6">{t('milestonebilling.fecha_limite')}</label>
          <DateInput id={`${idCampo}-1`} value={form.due_date} onChange={e => setForm(f=>({...f,due_date:e.target.value}))} className="milestone-billing-page-e7" />
        </div>
        <div className="u-grid2-12">
          <div>
            <label className="milestone-billing-page-e6">{t('pagina_mbill.importe_a_facturar')}{fmtMoneda.simbolo})</label>
            <input type="number" value={form.billing_amount} onChange={e => setForm(f=>({...f,billing_amount:e.target.value}))} className="milestone-billing-page-e7" placeholder={t('pagina_mbill.importe_a_facturar_2')} aria-label={t('pagina_mbill.importe_a_facturar_2')} />
          </div>
          <div>
            <label className="milestone-billing-page-e6">{t('milestonebilling.o_del_contrato')}</label>
            <input type="number" value={form.billing_pct} onChange={e => setForm(f=>({...f,billing_pct:e.target.value}))} className="milestone-billing-page-e7" placeholder={t('milestonebilling.porcentaje_del_contrato')} aria-label={t('milestonebilling.porcentaje_del_contrato')} min="0" max="100" />
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="milestone-billing-page-e6">{t('milestonebilling.descripcion')}</label>
          <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} className="milestone-billing-page-e3" />
        </div>
      </div>
      <div className="u-actions-8">
        <button onClick={onClose} className="u-btn-outline-sm">{t('common.cancel')}</button>
        <Button onClick={() => mutate()} loading={isPending} disabled={!form.name || isPending}>{t('pagina_mbill.crear_milestone')}</Button>
      </div>
    </Modal>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
/** Rev. 173: con `projectId` va dentro de la ficha del proyecto, con el proyecto fijo y sin selector. */
export default function MilestoneBillingPage({ projectId }: { projectId?: string } = {}): JSX.Element {
  const t = useAppT()
  const _t = useAppT()
  const _toast = useToast()
  const _qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState(projectId ?? '')
  const [showNew, setShowNew]   = useState(false)
  const [tab, setTab] = useState<'project' | 'dashboard'>('project')

  const { data: projects = [] } = useQuery<ProjectListItem[]>({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list({}).then(r => r.data),
  })

  const { data: milestones = [], refetch } = useQuery<MilestoneItem[]>({
    queryKey: ['milestones', selectedProject],
    queryFn: () => milestonesApi.list(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: dashboard = [], refetch: refetchDash } = useQuery<MilestoneItem[]>({
    queryKey: ['milestones-dashboard'],
    queryFn: () => milestonesApi.dashboard().then(r => r.data),
    enabled: tab === 'dashboard',
  })

  const projectName = projects.find(p => String(p.id) === String(selectedProject))?.name || ''

  // Agrupados por estado
  // useQuery devuelve data como `any` en este proyecto (tipos de react-query), asi que
  // fijamos el tipo local antes de reducir para evitar TS2347.
  const byStatus = milestones.reduce<Record<string, MilestoneItem[]>>((acc, m) => {
    const key = m.billing_status || 'pending'
    acc[key] = [...(acc[key] || []), m]
    return acc
  }, {})

  return (
    <PageShell>
      <PageHeader
        icon={<Flag size={18} />}
        title={_t('milestone_billing.title')}
        subtitle={_t('milestone_billing.subtitle')}
      showListExport={false}
      />

      {!projectId && <Tabs
        items={[
          { id: 'project',   label: t('pagina_mbill.por_proyecto') },
          { id: 'dashboard', label: t('pagina_mbill.dashboard_pendientes'), count: dashboard.length || undefined },
        ]}
        active={tab}
        onChange={(id) => setTab(id as 'project' | 'dashboard')}
        ariaLabel={t('pagina_mbill.facturacion_por_hitos')}
      />}

      {/* Vista por proyecto */}
      {tab === 'project' && (
        <>
          <div className="mbill-row-4">
            {!projectId && <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              className="milestone-billing-page-e4">
              <option value="">{t('pagina_mbill.seleccionar_proyecto')}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>}
            {selectedProject && (
              <Button onClick={() => setShowNew(true)}>{t('milestonebilling.nuevo_milestone_2')}</Button>
            )}
          </div>

          {!selectedProject ? (
            <EmptyState icon="🧾" title={t('milestonebilling.selecciona_un_proyecto')} description={t('pagina_mbill.elige_un_proyecto_para_gestionar_sus')} />
          ) : milestones.length === 0 ? (
            <EmptyState icon="○" title={t('milestonebilling.sin_milestones')} description={t('pagina_mbill.crea_el_primer_milestone_para_empezar')} />
          ) : (
            <div>
              {/* Flujo visual */}
              <div className="mbill-row-5">
                {Object.entries(STATUS).map(([k, v], i) => (
                  <div key={k} className="u-row-center-6">
                    <div className={`mbill-box-3 ${byStatus[k]?.length > 0 ? 'mileston-sx2' : 'mileston-sx3'} milestone-billing-page-e5`} style={{ '--milestone-billing-page-background': v.bg, '--milestone-billing-page-color': v.color } as CSSProperties}>
                      {v.icon} {t(v.label)} {byStatus[k]?.length > 0 ? `(${byStatus[k].length})` : ''}
                    </div>
                    {i < Object.keys(STATUS).length - 1 && (
                      <span className="mbill-label-4">→</span>
                    )}
                  </div>
                ))}
              </div>

              {/* Milestones ordenados por flujo */}
              {['pending_approval', 'approved', 'completed', 'pending', 'rejected', 'invoiced'].map(status =>
                byStatus[status]?.map(m => (
                  <MilestoneCard key={m.id} m={m} projectName={projectName} onRefresh={refetch} />
                ))
              )}
            </div>
          )}
        </>
      )}

      {/* Dashboard de pendientes */}
      {tab === 'dashboard' && (
        <div>
          {dashboard.length === 0 ? (
            <EmptyState icon="✅" title={t('milestonebilling.sin_pendientes')} description={t('pagina_mbill.no_hay_milestones_pendientes_de_accion')} />
          ) : (
            <>
              <div className="mbill-box-4">
                {dashboard.length} {t('milestonebilling.milestones_requieren_accion_en_todos_los_proyectos')}
              </div>
              {dashboard.map(m => (
                <MilestoneCard
                  key={m.id} m={m}
                  projectName={m.project_name || ''}
                  onRefresh={refetchDash}
                />
              ))}
            </>
          )}
        </div>
      )}

      {showNew && (
        <NewMilestoneModal
          projectId={selectedProject}
          onClose={() => setShowNew(false)}
          onSave={() => { setShowNew(false); refetch() }}
        />
      )}
    </PageShell>
  )
}
