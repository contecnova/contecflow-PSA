import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../services/api'
import _api, { usersApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { CheckCircle } from 'lucide-react'
import { Button, Modal, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'

const inp = { background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }
const panel = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }

const ENTITY_LABELS = {
  timesheet:      { label: 'Timesheets',       icon: '🕐', color: 'var(--accent)' },
  expense:        { label: 'Gastos',            icon: '💶', color: 'var(--warning)' },
  change_request: { label: 'Cambios (CR)',       icon: '🔄', color: 'var(--purple)' },
  milestone:      { label: 'Milestones',        icon: '◎',  color: 'var(--success)' },
  purchase:       { label: 'Compras',           icon: '🛒', color: 'var(--danger)' },
}

const APPROVER_TYPE_LABELS = {
  user:               'Usuario específico',
  role:               'Por rol',
  manager:            'Manager del solicitante',
  any_in_department:  'Cualquiera del departamento',
}

const ROLES = ['admin', 'pm', 'team_lead', 'hr', 'developer', 'designer', 'finance']

// ── Modal de paso ─────────────────────────────────────────────────────────────
function StepModal({ workflowId, step, onClose }) {
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const qc = useQueryClient()
  const isEdit = !!step?.id
  const [form, setForm] = useState({
    step_order:          step?.step_order          || 1,
    name:                step?.name                || '',
    approver_type:       step?.approver_type       || 'role',
    approver_role:       step?.approver_role       || '',
    approver_user_id:    step?.approver_user_id    || '',
    approver_department: step?.approver_department || '',
    is_optional:         step?.is_optional         || false,
    timeout_hours:       step?.timeout_hours       || 72,
    on_timeout:          step?.on_timeout          || 'escalate',
  })

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? approvalsApi.updateStep(workflowId, step.id, d)
      : approvalsApi.addStep(workflowId, d),
    onSuccess: () => {
      qc.invalidateQueries(['approval-workflow', workflowId])
      toast.success(isEdit ? 'Paso actualizado' : 'Paso añadido')
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <Modal open title={isEdit ? '✏️ Editar paso' : '+ Nuevo paso de aprobación'} onClose={onClose} width={520}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <div>
          <label style={lbl}>Nombre del paso *</label>
          <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder="Ej: Manager directo, Director, CFO" />
        </div>
        <div>
          <label style={lbl}>Orden</label>
          <input type="number" value={form.step_order} onChange={e => setForm(f=>({...f,step_order:+e.target.value}))} style={inp} min="1" max="10" />
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={lbl}>Tipo de aprobador</label>
          <select value={form.approver_type} onChange={e => setForm(f=>({...f,approver_type:e.target.value}))} style={inp}>
            {Object.entries(APPROVER_TYPE_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>

        {form.approver_type === 'role' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={lbl}>Rol requerido</label>
            <select value={form.approver_role} onChange={e => setForm(f=>({...f,approver_role:e.target.value}))} style={inp}>
              <option value="">Seleccionar rol...</option>
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        )}

        {form.approver_type === 'user' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={lbl}>Usuario aprobador</label>
            <select value={form.approver_user_id} onChange={e => setForm(f=>({...f,approver_user_id:e.target.value}))} style={inp}>
              <option value="">Seleccionar usuario...</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
            </select>
          </div>
        )}

        {form.approver_type === 'any_in_department' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={lbl}>Departamento</label>
            <input value={form.approver_department} onChange={e => setForm(f=>({...f,approver_department:e.target.value}))} style={inp} placeholder="IT, Finance, HR..." />
          </div>
        )}

        <div>
          <label style={lbl}>Tiempo límite (horas)</label>
          <input type="number" value={form.timeout_hours} onChange={e => setForm(f=>({...f,timeout_hours:+e.target.value}))} style={inp} min="1" />
        </div>
        <div>
          <label style={lbl}>Si supera el tiempo</label>
          <select value={form.on_timeout} onChange={e => setForm(f=>({...f,on_timeout:e.target.value}))} style={inp}>
            <option value="escalate">Escalar al siguiente</option>
            <option value="auto_approve">Aprobar automáticamente</option>
            <option value="reject">Rechazar automáticamente</option>
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: 12, color: 'var(--text-1)' }}>
            <input type="checkbox" checked={form.is_optional} onChange={e => setForm(f=>({...f,is_optional:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
            Paso opcional (se puede saltar si el aprobador no responde)
          </label>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
        <Button onClick={() => mutate(form)} loading={isPending} disabled={!form.name || isPending}>
          {isEdit ? '💾 Guardar' : '+ Añadir paso'}
        </Button>
      </div>
    </Modal>
  )
}

// ── Detalle de flujo ──────────────────────────────────────────────────────────
function WorkflowDetail({ workflowId, onBack }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showStep, setShowStep] = useState(false)
  const [editStep, setEditStep] = useState(null)

  const { data: wf } = useQuery({
    queryKey: ['approval-workflow', workflowId],
    queryFn: () => approvalsApi.getWorkflow(workflowId).then(r => r.data),
  })

  const { mutate: delStep } = useMutation({
    mutationFn: sid => approvalsApi.deleteStep(workflowId, sid),
    onSuccess: () => { qc.invalidateQueries(['approval-workflow', workflowId]); toast.success('Paso eliminado') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const { mutate: toggleActive } = useMutation({
    mutationFn: val => approvalsApi.updateWorkflow(workflowId, { is_active: val }),
    onSuccess: () => qc.invalidateQueries(['approval-workflow', workflowId]),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  if (!wf) return null
  const steps = [...(wf.steps || [])].sort((a, b) => a.step_order - b.step_order)
  const entity = ENTITY_LABELS[wf.entity_type] || { label: wf.entity_type, icon: '○', color: 'var(--text-2)' }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 }}>
        <button onClick={onBack} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>← Volver</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 18, fontWeight: 800 }}>{wf.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
            <span style={{ color: entity.color }}>{entity.icon} {entity.label}</span>
            {wf.is_default && <span style={{ marginLeft: 8, fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>DEFAULT</span>}
            {!wf.is_active && <span style={{ marginLeft: 8, fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'var(--danger-bg)', color: 'var(--danger)' }}>INACTIVO</span>}
          </div>
        </div>
        <button onClick={() => toggleActive(!wf.is_active)} style={{
          background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8,
          padding: '6px 14px', color: wf.is_active ? 'var(--warning)' : 'var(--success)',
          cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
        }}>
          {wf.is_active ? '⏸ Desactivar' : '▶ Activar'}
        </button>
        <Button onClick={() => setShowStep(true)}>+ Añadir paso</Button>
      </div>

      {steps.length === 0 ? (
        <EmptyState icon="○" title="Sin pasos definidos" description="Añade los pasos del flujo de aprobación en orden" />
      ) : (
        <div style={{ position: 'relative' }}>
          {steps.map((step, i) => {
            const color = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--purple)', 'var(--danger)'][i % 5]
            return (
              <div key={step.id} style={{ display: 'flex', gap: 16, marginBottom: 6 }}>
                {/* Línea vertical */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 40, flexShrink: 0 }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', background: color + '20', border: `2px solid ${color}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 800, color, flexShrink: 0 }}>
                    {step.step_order}
                  </div>
                  {i < steps.length - 1 && (
                    <div style={{ width: 2, flex: 1, minHeight: 20, background: 'var(--surface-4)', margin: '4px 0' }} />
                  )}
                </div>

                {/* Card del paso */}
                <div style={{ ...panel, padding: '14px 18px', flex: 1, marginBottom: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{step.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                        {APPROVER_TYPE_LABELS[step.approver_type]}
                        {step.approver_role && ` · Rol: ${step.approver_role}`}
                        {step.approver_user_name && ` · ${step.approver_user_name}`}
                        {step.approver_department && ` · Dept: ${step.approver_department}`}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                        ⏱ {step.timeout_hours}h timeout · {step.on_timeout === 'escalate' ? 'Escala si no responde' : step.on_timeout === 'auto_approve' ? 'Auto-aprueba' : 'Auto-rechaza'}
                        {step.is_optional && ' · Opcional'}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button onClick={() => setEditStep(step)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>✏️</button>
                      <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar paso "${step.name}"?`, onConfirm: () => delStep(step.id), danger: true }) }} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}

          {/* Resultado final */}
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ width: 40, flexShrink: 0, display: 'flex', justifyContent: 'center' }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--success-bg)', border: '2px solid #00e5a0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>✓</div>
            </div>
            <div style={{ ...panel, padding: '12px 18px', flex: 1, borderColor: 'var(--success-border)' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--success)' }}>Aprobado — acción automática</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>El sistema ejecuta la acción vinculada al entity_type</div>
            </div>
          </div>
        </div>
      )}

      {(showStep || editStep) && (
        <StepModal workflowId={workflowId} step={editStep} onClose={() => { setShowStep(false); setEditStep(null) }} />
      )}
    </div>
  )
}

// ── Tab de mis solicitudes pendientes ─────────────────────────────────────────
function MyPendingTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [entityFilter, setEntityFilter] = useState('all')
  const [sortMode, setSortMode] = useState('oldest') // oldest | newest

  const { data: pending = [], isLoading } = useQuery({
    queryKey: ['approvals-pending-me'],
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    refetchInterval: 30000,
  })

  const { mutate: decide, isPending: deciding } = useMutation({
    mutationFn: ({ id, decision, note }) => approvalsApi.decide(id, { decision, note }),
    onSuccess: () => {
      qc.invalidateQueries(['approvals-pending-me'])
      // Cascade to the affected entity caches (approval could be for timesheets, expenses, or absences)
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['expenses-pending'])
      qc.invalidateQueries(['expenses-my'])
      qc.invalidateQueries(['absences-pending'])
      qc.invalidateQueries(['team-absences'])
      toast.success('Decisión registrada')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const [bulkApproving, setBulkApproving] = useState(false)

  const handleBulkApprove = async () => {
    if (selectedIds.size === 0) return
    setBulkApproving(true)
    try {
      await Promise.all(Array.from(selectedIds).map(id => approvalsApi.decide(id, { decision: 'approved' })))
      toast.success(`${selectedIds.size} solicitudes aprobadas`)
      setSelectedIds(new Set())
      qc.invalidateQueries(['approvals-pending-me'])
      qc.invalidateQueries(['timesheets-pending'])
      qc.invalidateQueries(['timesheets-mine'])
      qc.invalidateQueries(['expenses-pending'])
      qc.invalidateQueries(['expenses-my'])
      qc.invalidateQueries(['absences-pending'])
      qc.invalidateQueries(['team-absences'])
    } catch (e) {
      toast.error(extractErr(e, 'Error en aprobación masiva'))
    } finally {
      setBulkApproving(false)
    }
  }

  const toggleSelect = (id) => setSelectedIds(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const toggleAll = () => setSelectedIds(prev =>
    prev.size === queue.length ? new Set() : new Set(queue.map(r => r.id))
  )

  const queue = pending
    .filter(r => entityFilter === 'all' ? true : r.entity_type === entityFilter)
    .sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime()
      const tb = new Date(b.created_at || 0).getTime()
      return sortMode === 'oldest' ? ta - tb : tb - ta
    })

  const statsByEntity = pending.reduce((acc, r) => {
    acc[r.entity_type] = (acc[r.entity_type] || 0) + 1
    return acc
  }, {})

  if (isLoading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-2)' }}>Cargando...</div>

  if (pending.length === 0) return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-2)' }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Sin aprobaciones pendientes</div>
      <div style={{ fontSize: 13 }}>Estás al día con todas las solicitudes</div>
    </div>
  )

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10, marginBottom: 14 }}>
        <div style={{ ...panel, padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Pendientes totales</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--warning)' }}>{pending.length}</div>
        </div>
        {Object.entries(statsByEntity).slice(0, 3).map(([k, count]) => {
          const entity = ENTITY_LABELS[k] || { label: k, icon: '○', color: 'var(--text-2)' }
          return (
            <div key={k} style={{ ...panel, padding: '10px 12px' }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{entity.icon} {entity.label}</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: entity.color }}>{count}</div>
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <select value={entityFilter} onChange={e => setEntityFilter(e.target.value)} style={{ ...inp, width: 220 }}>
          <option value="all">Todas las entidades</option>
          {Object.entries(ENTITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select value={sortMode} onChange={e => setSortMode(e.target.value)} style={{ ...inp, width: 220 }}>
          <option value="oldest">Priorizar más antiguas</option>
          <option value="newest">Priorizar más recientes</option>
        </select>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-2)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={queue.length > 0 && selectedIds.size === queue.length}
            onChange={toggleAll}
            style={{ width: 15, height: 15, cursor: 'pointer', accentColor: 'var(--accent)' }}
          />
          {selectedIds.size === 0
            ? `${queue.length} solicitud(es) en cola para tu aprobación`
            : `${selectedIds.size} de ${queue.length} seleccionadas`}
        </label>
        {selectedIds.size > 0 && (
          <Button size="sm" onClick={handleBulkApprove} loading={bulkApproving}>
            ✅ Aprobar seleccionadas ({selectedIds.size})
          </Button>
        )}
      </div>
      {queue.map(req => {
        const entity = ENTITY_LABELS[req.entity_type] || { label: req.entity_type, icon: '○', color: 'var(--text-2)' }
        const ageHours = Math.max(0, Math.floor((Date.now() - new Date(req.created_at || Date.now()).getTime()) / 3600000))
        const isUrgent = ageHours >= 24
        return (
          <div key={req.id} style={{ background: selectedIds.has(req.id) ? 'var(--surface-3)' : 'var(--surface-2)', border: `1px solid ${selectedIds.has(req.id) ? 'var(--accent)' : isUrgent ? 'rgba(245,158,11,0.35)' : '#1e2d45'}`, borderRadius: 12, padding: '16px 20px', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <input
                type="checkbox"
                checked={selectedIds.has(req.id)}
                onChange={() => toggleSelect(req.id)}
                style={{ width: 15, height: 15, marginTop: 4, cursor: 'pointer', flexShrink: 0, accentColor: 'var(--accent)' }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, padding: '2px 8px', borderRadius: 20, background: entity.color + '20', color: entity.color, fontWeight: 700 }}>
                    {entity.icon} {entity.label}
                  </span>
                  {req.step_name && (
                    <span style={{ fontSize: 11, color: 'var(--text-2)' }}>Paso {req.step_order}: {req.step_name}</span>
                  )}
                </div>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>
                  {req.entity_summary || req.entity_id}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                  Solicitado por: {req.requester_name} · {req.created_at}
                </div>
                {isUrgent && (
                  <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 4, fontWeight: 700 }}>
                    ⏱ Pendiente hace {ageHours}h
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                <button
                  onClick={() => decide({ id: req.id, decision: 'rejected', note: '' })}
                  disabled={deciding}
                  style={{ background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8, padding: '7px 14px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600 }}>
                  ✗ Rechazar
                </button>
                <Button
                  size="sm"
                  onClick={() => decide({ id: req.id, decision: 'approved' })}
                  loading={deciding}>
                  ✅ Aprobar
                </Button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function ApprovalsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab]           = useState('pending')   // pending | workflows | stats
  const [selected, setSelected] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', entity_type: 'timesheet', is_default: false })

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['approval-workflows'],
    queryFn: () => approvalsApi.listWorkflows().then(r => r.data),
  })

  const { data: stats } = useQuery({
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then(r => r.data),
  })

  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: approvalsApi.createWorkflow,
    onSuccess: (res) => {
      qc.invalidateQueries(['approval-workflows'])
      setShowCreate(false)
      setSelected(res.data.id)
      toast.success('Flujo creado')
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: del } = useMutation({
    mutationFn: approvalsApi.deleteWorkflow,
    onSuccess: () => { qc.invalidateQueries(['approval-workflows']); toast.success('Flujo eliminado') },

    onError: e => toast.error(extractErr(e, 'Error'))
  })

  if (selected) return <WorkflowDetail workflowId={selected} onBack={() => setSelected(null)} />

  const tabStyle = (active) => ({
    padding: '7px 18px', borderRadius: 8, border: 'none', cursor: 'pointer',
    background: active ? 'var(--accent-glow)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-2)',
    fontSize: 13, fontFamily: 'inherit', fontWeight: active ? 700 : 400,
  })

  return (
    <div style={{ padding: 32 }}>
      <PageHeader icon={<CheckCircle size={18} />} title={t('approvals.title')} subtitle="Flujos multi-nivel configurables para timesheets, gastos, cambios y más" />

      {/* KPIs */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
          {[
            { label: 'Pendientes',  value: stats.pending,  color: 'var(--warning)' },
            { label: 'Aprobadas',   value: stats.approved, color: 'var(--success)' },
            { label: 'Rechazadas',  value: stats.rejected, color: 'var(--danger)' },
            { label: 'Flujos activos', value: workflows.filter(w => w.is_active).length, color: 'var(--accent)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: '14px 18px', textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 800, color: k.color, fontFamily: "'Space Mono', monospace" }}>{k.value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, background: 'var(--surface-1)', borderRadius: 10, padding: 4, marginBottom: 20, width: 'fit-content' }}>
        <button onClick={() => setTab('pending')}   style={tabStyle(tab === 'pending')}>
          Mis pendientes {stats?.pending > 0 && <span style={{ marginLeft: 5, fontSize: 10, padding: '1px 5px', borderRadius: 8, background: 'var(--warning-border)', color: 'var(--warning)' }}>{stats.pending}</span>}
        </button>
        <button onClick={() => setTab('workflows')} style={tabStyle(tab === 'workflows')}>Flujos configurados</button>
      </div>

      {/* Tab pendientes */}
      {tab === 'pending' && <MyPendingTab />}

      {/* Tab flujos */}
      {tab === 'workflows' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <Button onClick={() => setShowCreate(true)}>+ Nuevo flujo</Button>
          </div>

          {isLoading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-2)' }}>Cargando...</div>
          ) : workflows.length === 0 ? (
            <EmptyState icon="✅" title="Sin flujos configurados"
              description="Crea flujos de aprobación para timesheets, gastos, cambios y más" />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
              {Object.entries(ENTITY_LABELS).map(([entityType, cfg]) => {
                const entityFlows = workflows.filter(w => w.entity_type === entityType)
                if (entityFlows.length === 0 && tab === 'workflows') return null
                return entityFlows.map(wf => {
                  return (
                    <div key={wf.id}
                      onClick={() => setSelected(wf.id)}
                      style={{
                        background: 'var(--surface-2)', border: `1px solid ${wf.is_active ? cfg.color + '30' : 'var(--surface-4)'}`,
                        borderRadius: 12, padding: '16px 20px', cursor: 'pointer',
                        opacity: wf.is_active ? 1 : 0.6,
                        transition: 'border-color 0.15s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = cfg.color + '60'}
                      onMouseLeave={e => e.currentTarget.style.borderColor = wf.is_active ? cfg.color + '30' : 'var(--surface-4)'}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <span style={{ fontSize: 20 }}>{cfg.icon}</span>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 700 }}>{wf.name}</div>
                            <div style={{ fontSize: 11, color: cfg.color }}>{cfg.label}</div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 4 }}>
                          {wf.is_default && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)', fontWeight: 700 }}>DEFAULT</span>}
                          {!wf.is_active && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'var(--danger-bg)', color: 'var(--danger)' }}>OFF</span>}
                        </div>
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
                        {wf.step_count} paso{wf.step_count !== 1 ? 's' : ''} de aprobación
                        {wf.description && ` · ${wf.description}`}
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button onClick={e => { e.stopPropagation(); openConfirmGlobal({message:`¿Eliminar flujo "${wf.name}"?`,onConfirm:()=>del(wf.id),danger:true}) }}
                          style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>
                          🗑
                        </button>
                      </div>
                    </div>
                  )
                })
              })}
              {workflows.filter(w => !Object.keys(ENTITY_LABELS).includes(w.entity_type)).map(wf => (
                <div key={wf.id} onClick={() => setSelected(wf.id)}
                  style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '16px 20px', cursor: 'pointer' }}>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{wf.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{wf.entity_type} · {wf.step_count} pasos</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showCreate && (
        <Modal open title="Nuevo flujo de aprobación" onClose={() => setShowCreate(false)} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={lbl}>Nombre *</label>
              <input value={form.name} onChange={e => setForm(f=>({...f,name:e.target.value}))} style={inp} placeholder="Ej: Aprobación gastos &gt;1000€" />
            </div>
            <div>
              <label style={lbl}>Tipo de entidad</label>
              <select value={form.entity_type} onChange={e => setForm(f=>({...f,entity_type:e.target.value}))} style={inp}>
                {Object.entries(ENTITY_LABELS).map(([k,v]) => <option key={k} value={k}>{v.icon} {v.label}</option>)}
              </select>
            </div>
            <div>
              <label style={lbl}>Descripción</label>
              <input value={form.description} onChange={e => setForm(f=>({...f,description:e.target.value}))} style={inp} placeholder="Cuándo se activa este flujo..." />
            </div>
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', fontSize: 12, color: 'var(--text-1)' }}>
              <input type="checkbox" checked={form.is_default} onChange={e => setForm(f=>({...f,is_default:e.target.checked}))} style={{ accentColor: 'var(--accent)' }} />
              Flujo por defecto para este tipo de entidad
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowCreate(false)} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => create(form)} loading={creating} disabled={!form.name || creating}>Crear flujo</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
