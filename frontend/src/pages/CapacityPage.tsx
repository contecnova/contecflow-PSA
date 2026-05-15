/**
 * CapacityPage — Planificador visual de recursos con drag-and-drop
 *
 * Matriz: usuarios (filas) × semanas (columnas)
 * Permite arrastrar bloques de horas de un usuario/semana a otro.
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useInvalidate } from '../hooks/useInvalidate'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, usersApi, capacityApi, unwrapList } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp } from 'lucide-react'
import { Button, Modal, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

const assignPlanSchema = z.object({
  user_id: z.string().trim().min(1, 'La persona es obligatoria'),
  project_id: z.string().optional(),
  week_start: z.string().min(1, 'La semana es obligatoria'),
  planned_hours: z.coerce.number().min(1, 'Las horas planificadas deben ser al menos 1').max(80, 'Las horas planificadas no pueden superar 80'),
  notes: z.string().optional(),
})

const LOAD_COLOR = (pct) => pct > 100 ? 'var(--danger)' : pct > 85 ? 'var(--warning)' : pct > 60 ? 'var(--accent)' : 'var(--success)'

function monday(d) {
  const dt = new Date(d)
  const day = dt.getDay()
  dt.setDate(dt.getDate() - (day === 0 ? 6 : day - 1))
  return dt.toISOString().slice(0, 10)
}

function addWeeks(dateStr, n) {
  const d = new Date(dateStr)
  d.setDate(d.getDate() + n * 7)
  return d.toISOString().slice(0, 10)
}

function weekLabel(dateStr) {
  const d = new Date(dateStr)
  return `${d.getDate()}/${d.getMonth() + 1}`
}

// ── Modal de nueva asignación ─────────────────────────────────────────────────
function AssignModal({ prefill, onClose }) {
  const toast = useToast()
  const { _invalidate } = useInvalidate()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    user_id:       prefill?.user_id  || '',
    project_id:    prefill?.project_id || '',
    week_start:    prefill?.week_start || monday(new Date()),
    planned_hours: prefill?.hours || 8,
    notes:         '',
  })
  const validation = useFormValidation(assignPlanSchema)

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => unwrapList(r).filter(u => u.is_active)),
  })
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => unwrapList(r).filter(p => p.status === 'active')),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: d => capacityApi.createPlan(d),
    onSuccess: () => {
      qc.invalidateQueries(['capacity-board'])
      qc.invalidateQueries(['forecast-heatmap'])
      qc.invalidateQueries(['forecast-summary'])
      toast.success('Asignación creada')
      validation.setErrors({})
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const setField = (key) => (e) => {
    const value = key === 'planned_hours' ? +e.target.value : e.target.value
    setForm(current => ({ ...current, [key]: value }))
    validation.clearFieldError(key)
  }

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) {
      return
    }
    mutate(result.data)
  }

  return (
    <Modal open title="Nueva asignacion" onClose={onClose} width={460}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
        <div>
          <label style={ls}>Persona *</label>
          <select value={form.user_id} onChange={setField('user_id')} style={validation.inputStyle(fs, 'user_id')}>
            <option value="">Seleccionar...</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
          {validation.errors.user_id && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.user_id}</div>}
        </div>
        <div>
          <label style={ls}>Proyecto</label>
          <select value={form.project_id} onChange={setField('project_id')} style={fs}>
            <option value="">Sin proyecto (disponible)</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={ls}>Semana</label>
            <input type="date" value={form.week_start}
              onChange={e => {
                setForm(current => ({ ...current, week_start: monday(e.target.value) }))
                validation.clearFieldError('week_start')
              }} style={validation.inputStyle(fs, 'week_start')} />
            {validation.errors.week_start && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.week_start}</div>}
          </div>
          <div>
            <label style={ls}>Horas planificadas</label>
            <input type="number" value={form.planned_hours} min="1" max="80" step="0.5"
              onChange={setField('planned_hours')} style={validation.inputStyle(fs, 'planned_hours')} />
            {validation.errors.planned_hours && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.planned_hours}</div>}
          </div>
        </div>
        <div>
          <label style={ls}>Notas</label>
          <input value={form.notes} onChange={setField('notes')} style={fs} placeholder="Notas de la asignacion" aria-label="Notas de la asignacion" />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>Cancelar</button>
        <Button onClick={submit} loading={isPending} disabled={isPending}>
          Asignar
        </Button>
      </div>
    </Modal>
  )
}

// ── Celda de capacidad con drag & drop ────────────────────────────────────────
function CapCell({ userId, weekStart, plans, capacity, onDrop, onAdd }) {
  const toast = useToast()
  const [dragOver, setDragOver] = useState(false)
  const qc = useQueryClient()

  const committed = plans.reduce((s, p) => s + (p.planned_hours || 0), 0)
  const loadPct   = capacity > 0 ? Math.round((committed / capacity) * 100) : 0
  const color     = LOAD_COLOR(loadPct)

  const { mutate: deletePlan } = useMutation({
    mutationFn: id => capacityApi.deletePlan(id),
    onSuccess: () => { qc.invalidateQueries(['capacity-board']); qc.invalidateQueries(['forecast-heatmap']); qc.invalidateQueries(['forecast-summary']); toast.success('Asignación eliminada') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => {
        e.preventDefault()
        setDragOver(false)
        const data = JSON.parse(e.dataTransfer.getData('application/json') || '{}')
        if (data.planId) onDrop(data.planId, userId, weekStart)
      }}
      onClick={() => plans.length === 0 && onAdd({ user_id: userId, week_start: weekStart })}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && plans.length === 0) {
          e.preventDefault()
          onAdd({ user_id: userId, week_start: weekStart })
        }
      }}
      style={{
        minWidth: 72, minHeight: 60, borderRadius: 8, padding: '4px 6px',
        background: dragOver ? 'var(--accent-muted)' : committed > 0 ? 'var(--surface-2)' : 'var(--surface-0)',
        border: `1px solid ${dragOver ? 'var(--accent)' : committed > 0 ? color + '40' : 'var(--surface-4)'}`,
        cursor: plans.length === 0 ? 'pointer' : 'default',
        position: 'relative', overflow: 'hidden', transition: 'all 0.15s',
      }}
    >
      {/* Barra de fondo */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        height: `${Math.min(loadPct, 100)}%`, background: color + '20',
        transition: 'height 0.3s',
      }} />

      {/* Contenido */}
      <div style={{ position: 'relative', zIndex: 1 }}>
        {committed > 0 && (
          <div style={{ fontSize: "var(--text-xs)", fontWeight: 800, color, textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
            {loadPct}%
          </div>
        )}
        {plans.map(plan => (
          <div
            key={plan.id}
            draggable
            role="button"
            tabIndex={0}
            onDragStart={e => {
              e.stopPropagation()
              e.dataTransfer.setData('application/json', JSON.stringify({ planId: plan.id }))
            }}
            title={`${plan.project_name || 'Sin proyecto'} · ${plan.planned_hours}h`}
            style={{
              fontSize: "var(--text-3xs)", color: 'var(--text-1)', background: 'var(--surface-4)',
              borderRadius: 4, padding: '2px 4px', marginTop: 2,
              cursor: 'grab', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              border: '1px solid var(--surface-4)',
            }}
            onPointerEnter={() => {}}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 44 }}>
              {(plan.project_name || 'Libre').slice(0, 7)}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', marginLeft: 2, flexShrink: 0 }}>
              {plan.planned_hours}h
            </span>
            <button
              onClick={e => { e.stopPropagation(); openConfirmGlobal({ message: `¿Eliminar la planificación de ${plan.planned_hours}h en "${plan.project_name || 'Libre'}"? Esta acción no se puede deshacer.`, onConfirm: () => deletePlan(plan.id), danger: true }) }}
              style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-3xs)", padding: '0 1px', lineHeight: 1, flexShrink: 0 }}>
              ×
            </button>
          </div>
        ))}
        {committed === 0 && (
          <div style={{ textAlign: 'center', fontSize: "var(--text-lg)", color: 'var(--surface-4)' }}>+</div>
        )}
      </div>
    </div>
  )
}

export default function CapacityPage(): JSX.Element {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [weeksAhead, setWeeksAhead] = useState(8)
  const [showAssign, setShowAssign] = useState(false)
  const [assignPrefill, setAssignPrefill] = useState(null)
  const [deptFilter, setDeptFilter]       = useState('')

  const weekStarts = Array.from({ length: weeksAhead }, (_, i) =>
    addWeeks(monday(new Date()), i)
  )

  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => unwrapList(r).filter(u => u.is_active)),
  })

  const { data: board = [], isLoading } = useQuery({
    queryKey: ['capacity-board', weeksAhead],
    queryFn: () => capacityApi.board({
      week_from: weekStarts[0],
      week_to:   weekStarts[weekStarts.length - 1],
    }).then(r => r.data),
    staleTime: 30000,
  })

  const { mutate: movePlan } = useMutation({
    mutationFn: ({ id, user_id, week_start }) =>
      capacityApi.updatePlan(id, { user_id, week_start }),
    onSuccess: () => {
      qc.invalidateQueries(['capacity-board'])
      qc.invalidateQueries(['forecast-heatmap'])
      qc.invalidateQueries(['forecast-summary'])
      toast.success('Asignación movida')
    },
    onError: e => toast.error(extractErr(e, 'Error al mover')),
  })

  // Construir mapa de planes: { userId_weekStart: [plans] }
  const planMap = {}
  for (const plan of board) {
    const key = `${plan.user_id}_${plan.week_start}`
    if (!planMap[key]) planMap[key] = []
    planMap[key].push(plan)
  }

  const displayUsers = deptFilter
    ? users.filter(u => (u.department || '').toLowerCase().includes(deptFilter.toLowerCase()))
    : users

  const departments = [...new Set(users.map(u => u.department).filter(Boolean))]

  // Calcular KPIs de capacidad
  const totalAssignments = board.length
  const uniqueWeeksWithLoad = new Set(board.map(p => p.week_start)).size

  return (
    <PageShell>
      <PageHeader
        icon={<TrendingUp size={18} />}
        title={_t('capacity.title')}
        subtitle={_t('capacity.subtitle')}
      />

      {/* KPI bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Personas planificables', value: users.length,        color: 'var(--accent)' },
          { label: 'Departamentos',          value: departments.length,  color: 'var(--purple)' },
          { label: 'Asignaciones activas',   value: totalAssignments,    color: 'var(--success)' },
          { label: 'Semanas con carga',      value: uniqueWeeksWithLoad, color: 'var(--warning)' },
        ].map(k => (
          <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-2xl)", fontWeight: 800, fontFamily: 'var(--font-mono)', color: k.color, lineHeight: 1.1 }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Controles */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={weeksAhead} onChange={e => setWeeksAhead(+e.target.value)}
          style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', maxWidth: 160 }}>
          <option value={4}>4 semanas</option>
          <option value={8}>8 semanas</option>
          <option value={13}>13 semanas</option>
          <option value={26}>26 semanas</option>
        </select>
        <select value={deptFilter} onChange={e => setDeptFilter(e.target.value)}
          style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', maxWidth: 180 }}>
          <option value="">Todos los departamentos</option>
          {departments.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <Button onClick={() => { setAssignPrefill(null); setShowAssign(true) }}>+ Nueva asignación</Button>
        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginLeft: 'auto' }}>
          💡 Arrastra para mover · clic en + para añadir
        </div>
      </div>

      {/* Leyenda */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 16, flexWrap: 'wrap' }}>
        {[
          { label: 'Disponible (<60%)', color: 'var(--success)' },
          { label: 'Ocupado (60-85%)',  color: 'var(--accent)' },
          { label: 'Alto (85-100%)',    color: 'var(--warning)' },
          { label: 'Sobrecargado',      color: 'var(--danger)' },
        ].map(l => (
          <div key={l.label} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: l.color }} />
            {l.label}
          </div>
        ))}
      </div>

      {/* Tabla drag-and-drop */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-2)' }}>Cargando planificador...</div>
      ) : displayUsers.length === 0 ? (
        <EmptyState icon="👥" title="Sin personas disponibles" description="No hay recursos que coincidan con el filtro actual" />
      ) : (
        <div style={{ overflowX: 'auto', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: 16 }}>
          <table style={{ borderCollapse: 'separate', borderSpacing: '4px 4px', minWidth: '100%' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '6px 12px', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', position: 'sticky', left: 0, background: 'var(--surface-1)', zIndex: 2, minWidth: 150 }}>
                  Persona
                </th>
                <th style={{ textAlign: 'center', padding: '6px 8px', fontSize: "var(--text-xs)", color: 'var(--text-3)', minWidth: 44 }}>Cap.</th>
                {weekStarts.map(w => {
                  const isToday = w === monday(new Date())
                  return (
                    <th key={w} style={{ textAlign: 'center', padding: '6px 4px', fontSize: "var(--text-2xs)", color: isToday ? 'var(--accent)' : 'var(--text-3)', minWidth: 76, borderBottom: isToday ? '2px solid var(--accent)' : 'none' }}>
                      {weekLabel(w)}
                      {isToday && <div style={{ fontSize: "var(--text-8)", color: 'var(--accent)' }}>HOY</div>}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {displayUsers.map(u => (
                <tr key={u.id}>
                  <td style={{ padding: '4px 12px', position: 'sticky', left: 0, background: 'var(--surface-1)', zIndex: 1 }}>
                    <div style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap' }}>
                      {u.full_name.split(' ').slice(0, 2).join(' ')}
                    </div>
                    {u.department && (
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{u.department}</div>
                    )}
                  </td>
                  <td style={{ textAlign: 'center', padding: '4px 8px', fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
                    {u.weekly_capacity_hours || 40}h
                  </td>
                  {weekStarts.map(w => (
                    <td key={w} style={{ padding: '2px' }}>
                      <CapCell
                        userId={u.id}
                        weekStart={w}
                        plans={planMap[`${u.id}_${w}`] || []}
                        capacity={u.weekly_capacity_hours || 40}
                        onDrop={(planId, newUserId, newWeek) => movePlan({ id: planId, user_id: newUserId, week_start: newWeek })}
                        onAdd={(prefill) => { setAssignPrefill(prefill); setShowAssign(true) }}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAssign && (
        <AssignModal prefill={assignPrefill} onClose={() => setShowAssign(false)} />
      )}
    </PageShell>
  )
}
