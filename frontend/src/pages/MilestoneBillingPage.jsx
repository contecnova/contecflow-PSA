import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { milestonesApi, projectsApi, unwrapList } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Flag } from 'lucide-react'
import { Button, Modal, EmptyState, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

// ── Colores y labels por estado ───────────────────────────────────────────────
const STATUS = {
  pending:          { label: 'Pendiente',          color: 'var(--text-2)', bg: 'var(--surface-4)',   icon: '○' },
  completed:        { label: 'Completado',          color: 'var(--accent)', bg: 'var(--accent-muted)', icon: '✓' },
  pending_approval: { label: 'Esperando aprobación',color: 'var(--warning)', bg: 'var(--warning-bg)', icon: '⏳' },
  approved:         { label: 'Aprobado',            color: 'var(--success)', bg: 'var(--success-bg)', icon: '✅' },
  rejected:         { label: 'Rechazado',           color: 'var(--danger)', bg: 'var(--danger-bg)', icon: '✗' },
  invoiced:         { label: 'Facturado',           color: 'var(--purple)', bg: 'var(--purple-bg)', icon: '🧾' },
}

// ── Badge de estado ───────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const s = STATUS[status] || STATUS.pending
  return (
    <span style={{ fontSize: "var(--text-xs)", padding: '3px 10px', borderRadius: 20, background: s.bg, color: s.color, fontWeight: 700, whiteSpace: 'nowrap' }}>
      {s.icon} {s.label}
    </span>
  )
}

// ── Modal de rechazo ──────────────────────────────────────────────────────────
function RejectModal({ milestone, onClose, onReject }) {
  const [reason, setReason] = useState('')
  const milestoneLabel = milestone?.name || milestone?.title || milestone?.code || milestone?.id
  return (
    <Modal open title="Rechazar milestone" onClose={onClose} width={420}>
      {milestoneLabel && (
        <div style={{
          marginBottom: 14,
          padding: '8px 12px',
          background: 'var(--surface-3)',
          border: '1px solid var(--surface-4)',
          borderRadius: 8,
          fontSize: 'var(--text-sm)',
          color: 'var(--text-2)',
        }}>
          Milestone: <strong style={{ color: 'var(--text-1)' }}>{milestoneLabel}</strong>
          {milestone?.amount != null && (
            <span style={{ marginLeft: 8, color: 'var(--text-3)' }}>· {milestone.amount} {milestone.currency || ''}</span>
          )}
        </div>
      )}
      <div style={{ marginBottom: 16 }}>
        <label style={lbl}>Motivo del rechazo *</label>
        <textarea value={reason} onChange={e => setReason(e.target.value)}
          style={{ ...inp, minHeight: 80, resize: 'vertical' }}
          placeholder="Describe el motivo del rechazo" aria-label="Motivo del rechazo" />
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
        <Button variant="danger" onClick={() => onReject(reason)} disabled={!reason.trim()}>✗ Confirmar rechazo</Button>
      </div>
    </Modal>
  )
}

// ── Milestone card ────────────────────────────────────────────────────────────
function MilestoneCard({ m, projectName, onRefresh }) {
  const toast = useToast()
  const _qc = useQueryClient()
  const [showReject, setShowReject] = useState(false)
  const [loading, setLoading] = useState(null)

  const act = async (action, payload) => {
    setLoading(action)
    try {
      let res
      if (action === 'complete')        res = await milestonesApi.complete(m.id)
      if (action === 'uncomplete')      res = await milestonesApi.uncomplete(m.id)
      if (action === 'request')         res = await milestonesApi.requestApproval(m.id)
      if (action === 'approve')         res = await milestonesApi.approve(m.id, { approved: true })
      if (action === 'reject')          res = await milestonesApi.approve(m.id, { approved: false, rejection_reason: payload })
      if (action === 'invoice')         res = await milestonesApi.generateInvoice(m.id)
      toast.success(res?.data?.message || 'Acción completada')
      onRefresh()
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Error')
    } finally {
      setLoading(null)
      setShowReject(false)
    }
  }

  const s = STATUS[m.billing_status] || STATUS.pending

  return (
    <div style={{
      background: 'var(--surface-2)', border: `1px solid ${s.color}30`,
      borderRadius: 12, padding: '16px 20px', marginBottom: 10,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
            <StatusBadge status={m.billing_status} />
            {m.due_date && (
              <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>📅 {m.due_date}</span>
            )}
          </div>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)', marginBottom: 2 }}>{m.name}</div>
          <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
            📁 {projectName}
            {m.billing_amount && (
              <span style={{ marginLeft: 10, color: 'var(--accent)', fontWeight: 600 }}>
                💶 {m.billing_amount.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' })}
              </span>
            )}
            {m.billing_pct && !m.billing_amount && (
              <span style={{ marginLeft: 10, color: 'var(--warning)', fontWeight: 600 }}>
                {m.billing_pct}% del contrato
              </span>
            )}
          </div>
          {m.rejection_reason && (
            <div style={{ marginTop: 8, padding: '6px 10px', background: 'var(--danger-bg)', borderRadius: 6, fontSize: "var(--text-xs)", color: 'var(--danger)' }}>
              ✗ Rechazado: {m.rejection_reason}
            </div>
          )}
          {m.invoice_id && (
            <div style={{ marginTop: 8, padding: '6px 10px', background: 'var(--purple-bg)', borderRadius: 6, fontSize: "var(--text-xs)", color: 'var(--purple)' }}>
              🧾 Factura generada
            </div>
          )}
        </div>

        {/* Acciones según estado */}
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {m.billing_status === 'pending' && (
            <Button size="sm" onClick={() => act('complete')} loading={loading === 'complete'}>
              ✓ Marcar completado
            </Button>
          )}
          {m.billing_status === 'completed' && (
            <>
              <button onClick={() => act('uncomplete')} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '5px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                ↩ Desmarcar
              </button>
              <Button size="sm" onClick={() => act('request')} loading={loading === 'request'}>
                ⏳ Solicitar aprobación
              </Button>
            </>
          )}
          {m.billing_status === 'pending_approval' && (
            <>
              <button onClick={() => setShowReject(true)}
                style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 7, padding: '5px 12px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>
                ✗ Rechazar
              </button>
              <Button size="sm" onClick={() => act('approve')} loading={loading === 'approve'}>
                ✅ Aprobar
              </Button>
            </>
          )}
          {m.billing_status === 'approved' && (
            <Button size="sm" onClick={() => act('invoice')} loading={loading === 'invoice'}>
              🧾 Generar factura
            </Button>
          )}
          {m.billing_status === 'rejected' && (
            <Button size="sm" onClick={() => act('complete')} loading={loading === 'complete'}>
              ↩ Re-completar
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
function NewMilestoneModal({ projectId, onClose, onSave }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', description: '', due_date: '', billing_amount: '', billing_pct: '' })
  const { mutate, isPending } = useMutation({
    mutationFn: () => milestonesApi.create(projectId, {
      ...form,
      billing_amount: form.billing_amount ? +form.billing_amount : null,
      billing_pct:    form.billing_pct    ? +form.billing_pct    : null,
    }),
    onSuccess: () => { toast.success('Milestone creado'); onSave() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title="Nuevo milestone" onClose={onClose} width={500}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
        <div>
          <label style={lbl}>Nombre *</label>
          <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder="Nombre del milestone" aria-label="Nombre del milestone" />
        </div>
        <div>
          <label style={lbl}>Fecha límite</label>
          <input type="date" value={form.due_date} onChange={e => setForm(f=>({...f,due_date:e.target.value}))} style={inp} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={lbl}>Importe a facturar (€)</label>
            <input type="number" value={form.billing_amount} onChange={e => setForm(f=>({...f,billing_amount:e.target.value}))} style={inp} placeholder="Importe a facturar" aria-label="Importe a facturar" />
          </div>
          <div>
            <label style={lbl}>O % del contrato</label>
            <input type="number" value={form.billing_pct} onChange={e => setForm(f=>({...f,billing_pct:e.target.value}))} style={inp} placeholder="Porcentaje del contrato" aria-label="Porcentaje del contrato" min="0" max="100" />
          </div>
        </div>
        <div>
          <label style={lbl}>Descripción</label>
          <textarea value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} style={{ ...inp, minHeight: 60, resize: 'vertical' }} />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
        <Button onClick={() => mutate()} loading={isPending} disabled={!form.name || isPending}>Crear milestone</Button>
      </div>
    </Modal>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function MilestoneBillingPage() {
  const _t = useAppT()
  const _toast = useToast()
  const _qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showNew, setShowNew]   = useState(false)
  const [tab, setTab]           = useState('project')   // project | dashboard

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(unwrapList),
  })

  const { data: milestones = [], refetch } = useQuery({
    queryKey: ['milestones', selectedProject],
    queryFn: () => milestonesApi.list(selectedProject).then(r => r.data),
    enabled: !!selectedProject,
  })

  const { data: dashboard = [], refetch: refetchDash } = useQuery({
    queryKey: ['milestones-dashboard'],
    queryFn: () => milestonesApi.dashboard().then(r => r.data),
    enabled: tab === 'dashboard',
  })

  const projectName = projects.find(p => p.id === selectedProject)?.name || ''

  // Agrupados por estado
  const byStatus = milestones.reduce((acc, m) => {
    acc[m.billing_status] = [...(acc[m.billing_status] || []), m]
    return acc
  }, {})

  return (
    <PageShell>
      <PageHeader
        icon={<Flag size={18} />}
        title={_t('milestone_billing.title')}
        subtitle={_t('milestone_billing.subtitle')}
      />

      <Tabs
        items={[
          { id: 'project',   label: 'Por proyecto' },
          { id: 'dashboard', label: 'Dashboard pendientes', count: dashboard.length || undefined },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="Facturación por hitos"
      />

      {/* Vista por proyecto */}
      {tab === 'project' && (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
            <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
              style={{ ...inp, maxWidth: 320 }}>
              <option value="">Seleccionar proyecto...</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
            {selectedProject && (
              <Button onClick={() => setShowNew(true)}>+ Nuevo milestone</Button>
            )}
          </div>

          {!selectedProject ? (
            <EmptyState icon="🧾" title="Selecciona un proyecto" description="Elige un proyecto para gestionar sus milestones de facturacion" />
          ) : milestones.length === 0 ? (
            <EmptyState icon="○" title="Sin milestones" description="Crea el primer milestone para empezar a controlar hitos facturables" />
          ) : (
            <div>
              {/* Flujo visual */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
                {Object.entries(STATUS).map(([k, v], i) => (
                  <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{
                      padding: '4px 12px', borderRadius: 20, background: v.bg,
                      color: v.color, fontSize: "var(--text-xs)", fontWeight: 700,
                      opacity: byStatus[k]?.length > 0 ? 1 : 0.3,
                    }}>
                      {v.icon} {v.label} {byStatus[k]?.length > 0 ? `(${byStatus[k].length})` : ''}
                    </div>
                    {i < Object.keys(STATUS).length - 1 && (
                      <span style={{ color: 'var(--surface-4)', fontSize: "var(--text-lg)" }}>→</span>
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
            <EmptyState icon="✅" title="Sin pendientes" description="No hay milestones pendientes de accion en este momento" />
          ) : (
            <>
              <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 16 }}>
                {dashboard.length} milestones requieren acción en todos los proyectos
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
